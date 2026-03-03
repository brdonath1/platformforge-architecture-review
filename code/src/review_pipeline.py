"""
PlatformForge Orchestrator — Review Pipeline (review_pipeline.py)

D-188/D-194/D-195: 4-layer expert review with parallel L2/L3/L4
and diff-based correction synthesis.

Pipeline:
  Step 1: L1 compliance → correct → L1 re-check loop
  Step 2: L2 + L3 + L4 in parallel
  Step 3: Merge must-fix → ONE correction pass → L1 re-check
  Step 4: Should-improve → founder re-engagement → targeted update
  Step 5: Final L1 re-check

Decision Authority: D-188, D-194, D-195, D-196, D-197
Codex Spec Reference: Section 2.6 (Review Pipeline)
"""

from __future__ import annotations

import json
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .contracts import (
    MessageJob,
    PatchEntry,
    PatchResult,
    PhaseKey,
    ReviewFinding,
    ReviewPipelineResult,
    RoleName,
)
from .llm_gateway import AnthropicGateway
from .run_store import CostLedger, RunStore
from .settings import AppConfig

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_L1_RETRIES: int = 2
MAX_REENGAGEMENT_TOPICS: int = 8
MAX_REENGAGEMENT_EXCHANGES: int = 5
REENGAGEMENT_COMPLETE_MARKER: str = "[REENGAGEMENT_COMPLETE]"


# ---------------------------------------------------------------------------
# Persona loading — module-level functions
# ---------------------------------------------------------------------------

def load_review_personas(personas_dir: Path) -> dict[str, object]:
    """Load all persona files from the personas/ directory.

    Returns dict with keys: l2, l3, l4, config.
    l2 and l3 are dicts of {phase_key_value: persona_text}.
    l4 and config are raw strings.
    """
    result: dict[str, object] = {"l2": {}, "l3": {}, "l4": "", "config": ""}

    l2_path = personas_dir / "l2-domain-experts.md"
    if l2_path.exists():
        result["l2"] = _parse_persona_file(l2_path.read_text(encoding="utf-8"))
        l2_dict = result["l2"]
        if isinstance(l2_dict, dict):
            logger.info("L2 personas loaded: %d phases", len(l2_dict))

    l3_path = personas_dir / "l3-downstream-consumers.md"
    if l3_path.exists():
        result["l3"] = _parse_persona_file(l3_path.read_text(encoding="utf-8"))
        l3_dict = result["l3"]
        if isinstance(l3_dict, dict):
            logger.info("L3 personas loaded: %d phases", len(l3_dict))

    l4_path = personas_dir / "l4-founder-comprehension.md"
    if l4_path.exists():
        result["l4"] = l4_path.read_text(encoding="utf-8")
        logger.info("L4 persona loaded")

    config_path = personas_dir / "review-config.md"
    if config_path.exists():
        result["config"] = config_path.read_text(encoding="utf-8")

    return result


def _parse_persona_file(text: str) -> dict[str, str]:
    """Parse a persona markdown file into {phase_key_value: section_text}.

    Expects ``## Phase N`` headings. Keys are always strings matching
    PhaseKey values (``"1"``, ``"6a"``, etc.).
    """
    personas: dict[str, str] = {}
    current_phase: str | None = None
    current_lines: list[str] = []

    for line in text.split("\n"):
        phase_match = re.match(r"^## Phase (\w+)", line)
        if phase_match:
            if current_phase is not None:
                personas[current_phase] = "\n".join(current_lines).strip()
            phase_id = phase_match.group(1)
            # Keep as string (not int) to match PhaseKey.value
            current_phase = phase_id.lower() if not phase_id.isdigit() else phase_id
            current_lines = []
        elif current_phase is not None:
            current_lines.append(line)

    if current_phase is not None:
        personas[current_phase] = "\n".join(current_lines).strip()

    return personas


# ---------------------------------------------------------------------------
# Standalone helper functions
# ---------------------------------------------------------------------------

def parse_review_findings_xml(text: str, layer: int) -> list[ReviewFinding]:
    """Parse ``<finding>`` blocks from reviewer XML output."""
    if "<findings>NONE</findings>" in text or not text.strip():
        return []

    findings: list[ReviewFinding] = []
    pattern = re.compile(r"<finding>(.*?)</finding>", re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1)
        raw_cat = extract_xml_field(block, "category").strip().lower()
        if raw_cat not in ("must-fix", "should-improve", "consider"):
            raw_cat = "consider"
        findings.append(ReviewFinding(
            id=extract_xml_field(block, "id") or f"L{layer}-?",
            category=raw_cat,
            section=extract_xml_field(block, "section") or "unknown",
            issue=extract_xml_field(block, "issue"),
            evidence=extract_xml_field(block, "evidence"),
            recommendation=extract_xml_field(block, "recommendation"),
        ))

    return findings


def extract_xml_field(block: str, field: str) -> str:
    """Extract text between ``<field>`` and ``</field>`` tags."""
    match = re.search(rf"<{field}>(.*?)</{field}>", block, re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_correction_patches(xml_text: str) -> list[PatchEntry]:
    """Parse ``<patch>`` blocks from correction XML.

    Handles Haiku's tendency to close ``<new_text>`` with wrong tag.
    """
    patches: list[PatchEntry] = []
    patch_blocks = re.findall(
        r'<patch\s+id="([^"]*)">(.*?)</patch>', xml_text, re.DOTALL
    )

    for pid, block in patch_blocks:
        fields: dict[str, str] = {"id": pid}
        for field in ("action", "anchor", "search_text"):
            match = re.search(rf"<{field}>(.*?)</{field}>", block, re.DOTALL)
            fields[field] = match.group(1).strip() if match else ""
        # new_text: greedy capture, strip trailing wrong closing tag
        nt_match = re.search(r"<new_text>(.*)", block, re.DOTALL)
        if nt_match:
            content = nt_match.group(1).strip()
            content = re.sub(r"</\w+>\s*$", "", content).strip()
            fields["new_text"] = content
        else:
            fields["new_text"] = ""
        patches.append(PatchEntry(**fields))

    return patches


def apply_patches(
    deliverable: str, patches: list[PatchEntry]
) -> tuple[str, list[PatchResult]]:
    """Apply correction patches to deliverable.

    Returns ``(patched_deliverable, application_log)``.
    """
    result = deliverable
    log: list[PatchResult] = []

    for patch in patches:
        pid = patch.id
        action = patch.action
        search_text = patch.search_text
        new_text = patch.new_text
        anchor = patch.anchor

        # Verify anchor exists
        if anchor and anchor not in result:
            log.append(PatchResult(
                id=pid, action=action,
                status="skipped_anchor_not_found",
                detail=f"Anchor not found: {anchor[:80]}",
            ))
            continue

        if action == "replace":
            if not search_text:
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_no_search",
                    detail="No search_text provided",
                ))
                continue
            if not new_text:
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_empty_replacement",
                    detail=f"new_text empty — refusing to delete {len(search_text)} chars",
                ))
                continue

            count = result.count(search_text)
            if count == 0:
                # Fuzzy: normalize whitespace
                normalized_search = " ".join(search_text.split())
                normalized_result = " ".join(result.split())
                if normalized_search in normalized_result:
                    pattern = re.escape(search_text)
                    pattern = re.sub(r"\\ +", r"\\s+", pattern)
                    result, n = re.subn(pattern, new_text, result, count=1)
                    if n:
                        log.append(PatchResult(
                            id=pid, action=action,
                            status="applied_fuzzy",
                            detail="Applied with whitespace normalization",
                        ))
                        continue
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_not_found",
                    detail=f"search_text not found: {search_text[:80]}",
                ))
                continue
            elif count > 1:
                if anchor:
                    anchor_pos = result.find(anchor)
                    search_pos = result.find(
                        search_text, max(0, anchor_pos - 2000)
                    )
                    if search_pos != -1 and search_pos < anchor_pos + 5000:
                        result = (
                            result[:search_pos]
                            + new_text
                            + result[search_pos + len(search_text):]
                        )
                        log.append(PatchResult(
                            id=pid, action=action,
                            status="applied_anchored",
                            detail=f"Resolved ambiguity using anchor (found {count} matches)",
                        ))
                        continue
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_ambiguous",
                    detail=f"search_text appears {count} times",
                ))
                continue
            else:
                result = result.replace(search_text, new_text, 1)
                log.append(PatchResult(
                    id=pid, action=action,
                    status="applied",
                    detail=f"Replaced {len(search_text)} chars with {len(new_text)} chars",
                ))

        elif action == "insert_after":
            if search_text and search_text in result:
                pos = result.find(search_text) + len(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append(PatchResult(
                    id=pid, action=action,
                    status="applied",
                    detail=f"Inserted {len(new_text)} chars after search_text",
                ))
            else:
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_not_found",
                    detail="search_text not found for insert_after",
                ))

        elif action == "insert_before":
            if search_text and search_text in result:
                pos = result.find(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append(PatchResult(
                    id=pid, action=action,
                    status="applied",
                    detail=f"Inserted {len(new_text)} chars before search_text",
                ))
            elif anchor and anchor in result:
                pos = result.find(anchor)
                result = result[:pos] + new_text + "\n\n" + result[pos:]
                log.append(PatchResult(
                    id=pid, action=action,
                    status="applied_via_anchor",
                    detail="Inserted before anchor heading",
                ))
            else:
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_not_found",
                    detail="Neither search_text nor anchor found",
                ))

        elif action == "append_to_section":
            if anchor and anchor in result:
                anchor_pos = result.find(anchor)
                heading_level = len(anchor) - len(anchor.lstrip("#"))
                if heading_level < 1:
                    heading_level = 2
                heading_pattern = r"\n#{1," + str(heading_level) + r"} [^\n]+"
                next_heading = re.search(
                    heading_pattern, result[anchor_pos + len(anchor):]
                )
                if next_heading:
                    insert_pos = anchor_pos + len(anchor) + next_heading.start()
                else:
                    insert_pos = len(result)
                result = (
                    result[:insert_pos]
                    + "\n\n" + new_text + "\n"
                    + result[insert_pos:]
                )
                log.append(PatchResult(
                    id=pid, action=action,
                    status="applied",
                    detail=f"Appended {len(new_text)} chars to section",
                ))
            else:
                log.append(PatchResult(
                    id=pid, action=action,
                    status="skipped_anchor_not_found",
                    detail=f"Section anchor not found: {anchor[:80]}",
                ))

        else:
            log.append(PatchResult(
                id=pid, action=action,
                status="skipped_unknown_action",
                detail=f"Unknown action type: {action}",
            ))

    return result, log


def extract_role_from_persona(persona_text: str) -> str:
    """Extract ``**Role:**`` value from persona markdown."""
    match = re.search(r"\*\*Role:\*\*\s*(.+)", persona_text)
    return match.group(1).strip() if match else "Reviewer"


def _strip_synthesis_preamble(text: str) -> str:
    """Strip any preamble before the first markdown heading."""
    idx = text.find("\n#")
    if idx > 0:
        return text[idx + 1:]
    if text.startswith("#"):
        return text
    return text


# ---------------------------------------------------------------------------
# ReviewPipeline class
# ---------------------------------------------------------------------------

class ReviewPipeline:
    """D-188/D-194/D-195: 4-layer expert review with diff-based corrections.

    Pipeline:
      Step 1: L1 compliance -> correct -> L1 re-check loop
      Step 2: L2 + L3 + L4 in parallel
      Step 3: Merge must-fix -> ONE correction pass -> L1 re-check
      Step 4: Should-improve -> founder re-engagement -> targeted update
      Step 5: Final L1 re-check

    Does NOT own:
    - Phase execution (PhaseService)
    - Cross-phase orchestration (Step 7)
    - GitHub publishing (RunStore)
    """

    def __init__(
        self,
        gateway: AnthropicGateway,
        store: RunStore,
        ledger: CostLedger,
        config: AppConfig,
        persona: str,
        review_personas: dict[str, object],
    ) -> None:
        self._gateway = gateway
        self._store = store
        self._ledger = ledger
        self._config = config
        self._persona = persona
        self._review_personas = review_personas
        self._correction_count = 0

    # -------------------------------------------------------------------
    # Public: Main pipeline entry point
    # -------------------------------------------------------------------

    def run(
        self,
        phase: PhaseKey,
        deliverable: str,
        template_text: str,
        prior_deliverables: str,
    ) -> ReviewPipelineResult:
        """Run the full D-188 review pipeline on a deliverable."""
        pipeline_start = time.monotonic()
        current = deliverable
        reengagement_triggered = False

        # ── Step 1: L1 Compliance ──
        logger.info("Step 1: L1 Compliance Check — Phase %s", phase.value)

        l1_missing = self._run_l1_compliance(phase, current, template_text)
        l1_initial_missing = len(l1_missing)

        if l1_missing:
            l1_findings = [
                ReviewFinding(
                    id=f"L1-{i + 1}",
                    category="must-fix",
                    section=item.section,
                    issue=item.issue,
                    evidence="Required by phase template",
                    recommendation=f"Add missing element: {item.issue}",
                )
                for i, item in enumerate(l1_missing)
            ]
            current = self._run_correction_synthesis(
                phase, current, l1_findings
            )

            for retry in range(MAX_L1_RETRIES):
                l1_recheck = self._run_l1_compliance(
                    phase, current, template_text
                )
                if not l1_recheck:
                    break
                logger.warning(
                    "L1 re-check %d: still %d missing item(s)",
                    retry + 1, len(l1_recheck),
                )
                if retry < MAX_L1_RETRIES - 1:
                    recheck_findings = [
                        ReviewFinding(
                            id=f"L1-R{retry + 1}-{i + 1}",
                            category="must-fix",
                            section=item.section,
                            issue=item.issue,
                            evidence="Required by phase template",
                            recommendation=f"Add missing element: {item.issue}",
                        )
                        for i, item in enumerate(l1_recheck)
                    ]
                    current = self._run_correction_synthesis(
                        phase, current, recheck_findings
                    )

        # ── Step 2: Parallel L2+L3+L4 ──
        logger.info("Step 2: L2 + L3 + L4 Parallel Expert Review")

        l2_persona_dict = self._review_personas.get("l2", {})
        l3_persona_dict = self._review_personas.get("l3", {})
        l2_persona = (
            l2_persona_dict.get(phase.value, "Senior domain expert reviewer.")
            if isinstance(l2_persona_dict, dict) else "Senior domain expert reviewer."
        )
        l3_persona = (
            l3_persona_dict.get(phase.value, "Downstream phase consumer reviewer.")
            if isinstance(l3_persona_dict, dict) else "Downstream phase consumer reviewer."
        )
        l4_persona_raw = self._review_personas.get("l4", "")
        l4_persona = (
            l4_persona_raw
            if isinstance(l4_persona_raw, str) and l4_persona_raw
            else "Non-technical founder comprehension reviewer."
        )

        findings_l2: list[ReviewFinding] = []
        findings_l3: list[ReviewFinding] = []
        findings_l4: list[ReviewFinding] = []

        with ThreadPoolExecutor(
            max_workers=3, thread_name_prefix="review"
        ) as executor:
            futures = {
                executor.submit(
                    self._run_layer_review, phase, 2, current,
                    template_text, str(l2_persona), prior_deliverables,
                ): "L2",
                executor.submit(
                    self._run_layer_review, phase, 3, current,
                    template_text, str(l3_persona), prior_deliverables,
                ): "L3",
                executor.submit(
                    self._run_layer_review, phase, 4, current,
                    template_text, str(l4_persona), "",
                ): "L4",
            }

            for future in as_completed(futures):
                layer_label = futures[future]
                try:
                    layer_result = future.result()
                    if layer_label == "L2":
                        findings_l2 = layer_result
                    elif layer_label == "L3":
                        findings_l3 = layer_result
                    elif layer_label == "L4":
                        findings_l4 = layer_result
                except Exception as exc:
                    logger.error(
                        "%s review failed: %s: %s",
                        layer_label, type(exc).__name__, str(exc)[:200],
                    )

        # ── Step 3: Merged Correction Synthesis ──
        logger.info("Step 3: Merged Correction Synthesis")

        all_must_fix = (
            [f for f in findings_l2 if f.category == "must-fix"]
            + [f for f in findings_l3 if f.category == "must-fix"]
            + [f for f in findings_l4 if f.category == "must-fix"]
        )

        if all_must_fix:
            logger.info(
                "%d must-fix finding(s) across L2/L3/L4 — merging",
                len(all_must_fix),
            )
            all_findings = list(findings_l2) + list(findings_l3) + list(findings_l4)
            current = self._run_correction_synthesis(
                phase, current, all_findings
            )

            l1_post = self._run_l1_compliance(phase, current, template_text)
            if l1_post:
                logger.warning(
                    "L1 re-check post-review: %d item(s) — correcting",
                    len(l1_post),
                )
                post_findings = [
                    ReviewFinding(
                        id=f"L1-PR-{i + 1}",
                        category="must-fix",
                        section=item.section,
                        issue=item.issue,
                        evidence="Required by phase template",
                        recommendation=f"Restore missing element: {item.issue}",
                    )
                    for i, item in enumerate(l1_post)
                ]
                current = self._run_correction_synthesis(
                    phase, current, post_findings
                )
        else:
            logger.info("No must-fix findings across L2/L3/L4")

        # ── Step 4: Should-Improve Consolidation ──
        logger.info("Step 4: Should-Improve Consolidation")

        brief = self._build_interview_brief(
            phase, findings_l2, findings_l3, findings_l4
        )

        if brief:
            self._store.save_interview_brief(phase, brief)
            logger.info("Interview brief saved")

            responses = self._run_founder_reengagement(phase, brief)
            reengagement_triggered = True

            if responses:
                current = self._run_targeted_update(
                    phase, current, brief, responses
                )

                # ── Step 5: Final L1 Re-check ──
                logger.info("Step 5: Final L1 Re-check")
                l1_final = self._run_l1_compliance(
                    phase, current, template_text
                )
                if l1_final:
                    logger.warning(
                        "Final L1: %d item(s) — correcting", len(l1_final)
                    )
                    final_findings = [
                        ReviewFinding(
                            id=f"L1-FINAL-{i + 1}",
                            category="must-fix",
                            section=item.section,
                            issue=item.issue,
                            evidence="Required by phase template",
                            recommendation=f"Restore missing element: {item.issue}",
                        )
                        for i, item in enumerate(l1_final)
                    ]
                    current = self._run_correction_synthesis(
                        phase, current, final_findings
                    )
        else:
            logger.info("No should-improve items — skipping re-engagement")

        # ── Build review notes ──
        review_notes = self._build_review_notes(
            findings_l2, findings_l3, findings_l4, phase
        )

        # ── Pipeline summary ──
        elapsed = time.monotonic() - pipeline_start
        total_must = len(all_must_fix) + l1_initial_missing
        total_si = sum(
            1 for f in findings_l2 + findings_l3 + findings_l4
            if f.category == "should-improve"
        )
        total_consider = sum(
            1 for f in findings_l2 + findings_l3 + findings_l4
            if f.category == "consider"
        )

        logger.info(
            "Phase %s review pipeline complete (%.1f min). "
            "Findings: %d must-fix, %d should-improve, %d consider",
            phase.value, elapsed / 60,
            total_must, total_si, total_consider,
        )

        # Save pipeline summary
        summary = {
            "phase": phase.value,
            "pipeline_elapsed_seconds": round(elapsed),
            "l1_initial_missing": l1_initial_missing,
            "l2_findings": self._summarize_findings(findings_l2),
            "l3_findings": self._summarize_findings(findings_l3),
            "l4_findings": self._summarize_findings(findings_l4),
            "reengagement_triggered": reengagement_triggered,
            "deliverable_delta_chars": len(current) - len(deliverable),
        }
        self._store.save_review_pipeline_summary(
            phase, json.dumps(summary, indent=2)
        )

        return ReviewPipelineResult(
            deliverable_text=current,
            review_notes=review_notes,
            l1_initial_missing=l1_initial_missing,
            l2_findings=findings_l2,
            l3_findings=findings_l3,
            l4_findings=findings_l4,
            total_must_fix=total_must,
            total_should_improve=total_si,
            total_consider=total_consider,
            reengagement_triggered=reengagement_triggered,
            pipeline_elapsed_seconds=elapsed,
        )

    # -------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------

    @staticmethod
    def _summarize_findings(
        findings: list[ReviewFinding],
    ) -> dict[str, int]:
        """Summarize findings by category for JSON output."""
        return {
            "must_fix": sum(1 for f in findings if f.category == "must-fix"),
            "should_improve": sum(
                1 for f in findings if f.category == "should-improve"
            ),
            "consider": sum(
                1 for f in findings if f.category == "consider"
            ),
        }

    def _run_l1_compliance(
        self,
        phase: PhaseKey,
        deliverable: str,
        template_text: str,
    ) -> list[ReviewFinding]:
        """Binary checklist audit. Returns list of missing items."""
        logger.info("L1 Compliance check — Phase %s", phase.value)

        l1_prompt = (
            f"You are a specification compliance checker for a Phase {phase.value} deliverable.\n"
            "Your task is a binary audit: for each required element in the template, "
            "determine if it EXISTS in the deliverable. You have NO opinions about quality.\n\n"
            "RULES:\n"
            "1. Read the template to identify ALL required sections, subsections, fields, "
            "   and structural elements (manifests, appendices, cross-references, EOF sentinels).\n"
            "2. For each required element, check if it is PRESENT in the deliverable.\n"
            "3. A section is PRESENT if it has a heading AND substantive content (not just a heading).\n"
            "4. A field is PRESENT if it contains actual data (not placeholder text like 'TBD').\n"
            "5. Do NOT evaluate quality, accuracy, or completeness of content — only presence.\n\n"
            "Output as JSON ONLY (no markdown, no preamble):\n"
            '{"pass": true/false, "missing_items": [\n'
            '  {"section": "section name", "detail": "what is missing"}\n'
            "]}\n\n"
            "If all required elements are present, set pass=true and missing_items=[].\n\n"
            f"<phase_template>\n{template_text}\n</phase_template>\n\n"
            f"<deliverable>\n{deliverable}\n</deliverable>"
        )

        job = MessageJob(
            role=RoleName.L1,
            phase=phase,
            label=f"P{phase.value} L1 compliance",
            system_prompt=(
                "You are a specification compliance checker. "
                "Output ONLY valid JSON, no preamble or markdown."
            ),
            messages=[{"role": "user", "content": l1_prompt}],
            tools=[],
            thinking_budget=0,
        )

        result = self._gateway.run(job)
        if result.usage:
            self._ledger.record(phase, result.usage)

        text = result.text.strip()
        try:
            clean = text.replace("```json", "").replace("```", "").strip()
            parsed = json.loads(clean)
        except json.JSONDecodeError:
            logger.warning("L1 response not valid JSON — treating as fail")
            return [ReviewFinding(
                id="L1-PARSE",
                category="must-fix",
                section="PARSE_ERROR",
                issue="L1 response was not valid JSON",
            )]

        if parsed.get("pass", False):
            logger.info("L1 Compliance: PASS")
            return []

        missing = parsed.get("missing_items", [])
        logger.info("L1 Compliance: %d missing item(s)", len(missing))
        return [
            ReviewFinding(
                id=f"L1-{i + 1}",
                category="must-fix",
                section=item.get("section", "unknown"),
                issue=item.get("detail", "Missing required element"),
            )
            for i, item in enumerate(missing)
        ]

    def _run_layer_review(
        self,
        phase: PhaseKey,
        layer: int,
        deliverable: str,
        template_text: str,
        persona_text: str,
        prior_deliverables: str,
    ) -> list[ReviewFinding]:
        """Generic reviewer for L2, L3, L4."""
        layer_names = {
            2: "Domain Expert",
            3: "Downstream Consumer",
            4: "Founder Comprehension",
        }
        layer_name = layer_names.get(layer, f"Layer {layer}")
        role_map = {2: RoleName.L2, 3: RoleName.L3, 4: RoleName.L4}
        role = role_map.get(layer, RoleName.L2)

        logger.info("L%d %s review — Phase %s", layer, layer_name, phase.value)

        classification_rules = (
            "CLASSIFICATION DECISION TREE (apply in order, first 'yes' wins):\n"
            "1. Is this factually wrong? (incorrect data, contradicts prior deliverable) -> must-fix\n"
            "2. Is a required element missing or empty? (template requires X, deliverable lacks X) -> must-fix\n"
            "3. Would this block the next phase's work? (downstream team cannot proceed) -> must-fix\n"
            "4. Is this thin/vague where founder's knowledge would produce better content? -> should-improve\n"
            "5. Is a technical concept unexplained for non-technical reader? -> should-improve\n"
            "6. Everything else (suggestions, alternatives, nice-to-haves) -> consider\n\n"
            "BOUNDARY RULES:\n"
            "- 'Thin but not wrong' -> should-improve (not must-fix)\n"
            "- Missing subsection -> must-fix ONLY if template lists it as required\n"
            "- 'Could be better' -> consider\n"
            "- Wrong framework choice -> must-fix ONLY if contradicts founder decision; else should-improve\n"
            "- Inconsistency within deliverable -> must-fix\n"
            "- Inconsistency with prior deliverable -> must-fix\n"
        )

        if layer == 4:
            system_prompt = (
                "You are a non-technical founder reviewing a deliverable for comprehensibility. "
                "You understand business concepts but not technical implementation details. "
                "Evaluate whether this document is understandable to someone who will pay for "
                "the build but has no software engineering background."
            )
        else:
            use_text = (
                "USE this deliverable in their domain work"
                if layer == 2
                else "CONSUME this deliverable as input for the next phase"
            )
            system_prompt = (
                f"You are a {layer_name} reviewer. You evaluate deliverables from the perspective "
                f"of a senior professional who would {use_text}. "
                "Your review is independent — you have not seen any other reviewer's findings."
            )

        user_prompt = (
            f"<your_persona>\n{persona_text}\n</your_persona>\n\n"
            f"<phase_template>\n{template_text}\n</phase_template>\n\n"
            f"<deliverable_to_review>\n{deliverable}\n</deliverable_to_review>\n\n"
        )

        if prior_deliverables and layer in (2, 3):
            user_prompt += (
                f"<prior_deliverables>\n{prior_deliverables}\n</prior_deliverables>\n\n"
            )

        user_prompt += (
            f"{classification_rules}\n"
            f"Review this Phase {phase.value} deliverable as described in your persona. "
            "For EVERY finding, use this EXACT XML format:\n\n"
            "<finding>\n"
            f"  <id>L{layer}-N</id>\n"
            "  <category>must-fix | should-improve | consider</category>\n"
            "  <section>section name</section>\n"
            "  <issue>one sentence: what is wrong or missing</issue>\n"
            "  <evidence>quote or reference from deliverable OR template</evidence>\n"
            "  <recommendation>one sentence: specific action to resolve</recommendation>\n"
            "</finding>\n\n"
            "If you find no issues, output:\n<findings>NONE</findings>\n\n"
            "Output ALL findings wrapped in a <findings> tag. No preamble or commentary outside the tags."
        )

        job = MessageJob(
            role=role,
            phase=phase,
            label=f"P{phase.value} L{layer} {layer_name}",
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[],
        )

        result = self._gateway.run(job)
        if result.usage:
            self._ledger.record(phase, result.usage)

        review_text = result.text.strip()

        if not review_text:
            logger.warning("L%d %s: empty response — skipping", layer, layer_name)
            return []

        findings = parse_review_findings_xml(review_text, layer)

        must_fix = [f for f in findings if f.category == "must-fix"]
        should_improve = [f for f in findings if f.category == "should-improve"]
        consider = [f for f in findings if f.category == "consider"]

        logger.info(
            "L%d %s: %d must-fix, %d should-improve, %d consider",
            layer, layer_name, len(must_fix), len(should_improve), len(consider),
        )

        # Save review findings
        review_report = {
            "layer": layer,
            "layer_name": layer_name,
            "phase": phase.value,
            "findings": [f.model_dump() for f in findings],
            "summary": {
                "must_fix": len(must_fix),
                "should_improve": len(should_improve),
                "consider": len(consider),
                "total": len(findings),
            },
        }
        self._store.save_review_findings(
            phase, layer, json.dumps(review_report, indent=2)
        )

        return findings

    def _run_correction_synthesis(
        self,
        phase: PhaseKey,
        deliverable: str,
        findings: list[ReviewFinding],
    ) -> str:
        """D-195: Diff-based correction synthesis."""
        must_fix = [f for f in findings if f.category == "must-fix"]
        if not must_fix:
            return deliverable

        logger.info(
            "Correction synthesis (diff-based) — %d must-fix item(s)",
            len(must_fix),
        )

        findings_xml = ""
        for f in must_fix:
            findings_xml += (
                "<finding>\n"
                f"  <id>{f.id}</id>\n"
                f"  <section>{f.section}</section>\n"
                f"  <issue>{f.issue}</issue>\n"
                f"  <evidence>{f.evidence}</evidence>\n"
                f"  <recommendation>{f.recommendation}</recommendation>\n"
                "</finding>\n"
            )

        correction_prompt = (
            "<correction_request>\n"
            f"  <deliverable>\n{deliverable}\n  </deliverable>\n"
            f"  <findings>\n{findings_xml}  </findings>\n"
            "  <instruction>\n"
            "    For each finding, output ONE patch in the <corrections> block.\n"
            "    Do NOT output the full document. Output ONLY the corrections XML.\n"
            "  </instruction>\n"
            "</correction_request>"
        )

        system_prompt = (
            "You are a precise document patch generator. For each finding, output a "
            "targeted correction patch. Do NOT output the full document. Output ONLY "
            "the <corrections> XML block with patches for each must-fix finding.\n\n"
            "RULES:\n"
            "1. Each patch targets ONE specific location in the document.\n"
            "2. <anchor> must be an EXACT markdown heading from the document (e.g., '## 1.3 Target Audience').\n"
            "3. <search_text> must be a UNIQUE phrase (10-50 words) that appears EXACTLY once "
            "   in the document near the anchor. Copy it character-for-character.\n"
            "4. <new_text> is the replacement content. Include surrounding context if needed "
            "   for the replacement to read naturally.\n"
            "5. For missing sections/content, use action='append_to_section' or 'insert_after'.\n"
            "6. For incorrect content, use action='replace'.\n"
            "7. Keep patches minimal — change only what the finding requires.\n"
            "8. If a finding requires adding a NEW section that doesn't exist, use "
            "   action='insert_before' with the anchor set to the heading AFTER where "
            "   the new section should appear.\n\n"
            "OUTPUT FORMAT:\n"
            "<corrections>\n"
            '  <patch id="FINDING-ID">\n'
            "    <action>replace|insert_after|insert_before|append_to_section</action>\n"
            "    <anchor>## Exact Heading</anchor>\n"
            "    <search_text>exact phrase from document</search_text>\n"
            "    <new_text>replacement or inserted content</new_text>\n"
            "  </patch>\n"
            "</corrections>"
        )

        job = MessageJob(
            role=RoleName.CORRECTION,
            phase=phase,
            label=f"P{phase.value} correction synthesis",
            system_prompt=system_prompt,
            messages=[{"role": "user", "content": correction_prompt}],
            tools=[],
        )

        result = self._gateway.run(job)
        if result.usage:
            self._ledger.record(phase, result.usage)

        raw_output = result.text.strip()

        # Save raw correction XML for debugging
        self._correction_count += 1
        self._store.save_correction_debug(
            phase, self._correction_count, raw_output
        )

        if not raw_output:
            logger.warning("Correction synthesis returned empty — keeping original")
            return deliverable

        patches = parse_correction_patches(raw_output)
        if not patches:
            logger.warning(
                "No patches parsed from correction output (%d chars) — keeping original",
                len(raw_output),
            )
            return deliverable

        corrected, log = apply_patches(deliverable, patches)

        applied_count = sum(1 for e in log if "applied" in e.status)
        skipped_count = sum(1 for e in log if "skipped" in e.status)

        logger.info(
            "Patches: %d applied, %d skipped (of %d total)",
            applied_count, skipped_count, len(patches),
        )
        for entry in log:
            symbol = "+" if "applied" in entry.status else "-"
            logger.debug(
                "  %s %s: %s — %s",
                symbol, entry.id, entry.status, entry.detail[:80],
            )

        if applied_count == 0 and len(patches) > 0:
            logger.warning("No patches could be applied — keeping original")
            return deliverable

        return corrected

    def _build_interview_brief(
        self,
        phase: PhaseKey,
        l2_findings: list[ReviewFinding],
        l3_findings: list[ReviewFinding],
        l4_findings: list[ReviewFinding],
    ) -> str:
        """Consolidate should-improve items into XML interview brief."""
        si_l2 = [f for f in l2_findings if f.category == "should-improve"]
        si_l3 = [f for f in l3_findings if f.category == "should-improve"]
        si_l4 = [f for f in l4_findings if f.category == "should-improve"]

        total = len(si_l2) + len(si_l3) + len(si_l4)
        if total == 0:
            return ""

        remaining = MAX_REENGAGEMENT_TOPICS
        selected_l2 = si_l2[:remaining]
        remaining -= len(selected_l2)
        selected_l3 = si_l3[:remaining] if remaining > 0 else []
        remaining -= len(selected_l3)
        selected_l4 = si_l4[:remaining] if remaining > 0 else []

        deferred = total - len(selected_l2) - len(selected_l3) - len(selected_l4)
        if deferred > 0:
            logger.info(
                "%d should-improve item(s) deferred (cap: %d)",
                deferred, MAX_REENGAGEMENT_TOPICS,
            )

        l2_persona_dict = self._review_personas.get("l2", {})
        l3_persona_dict = self._review_personas.get("l3", {})
        l2_persona_text = (
            l2_persona_dict.get(phase.value, "")
            if isinstance(l2_persona_dict, dict) else ""
        )
        l3_persona_text = (
            l3_persona_dict.get(phase.value, "")
            if isinstance(l3_persona_dict, dict) else ""
        )
        l2_role = extract_role_from_persona(str(l2_persona_text))
        l3_role = extract_role_from_persona(str(l3_persona_text))

        brief = f'<interview_brief phase="{phase.value}">\n'
        brief += (
            f"  <summary>{total} should-improve items found across "
            f"L2 ({len(si_l2)}), L3 ({len(si_l3)}), L4 ({len(si_l4)}) "
            f"for Phase {phase.value} deliverable.</summary>\n\n"
        )

        if selected_l2:
            brief += f'  <topic_group source="L2 -- Domain Expert ({l2_role})">\n'
            for i, f in enumerate(selected_l2, 1):
                brief += (
                    f'    <topic id="SI-{phase.value}-L2-{i}">\n'
                    f"      <context>{f.evidence}</context>\n"
                    f"      <gap>{f.issue}</gap>\n"
                    f"      <question>{f.recommendation}</question>\n"
                    f"    </topic>\n"
                )
            brief += "  </topic_group>\n\n"

        if selected_l3:
            brief += f'  <topic_group source="L3 -- Downstream Consumer ({l3_role})">\n'
            for i, f in enumerate(selected_l3, 1):
                brief += (
                    f'    <topic id="SI-{phase.value}-L3-{i}">\n'
                    f"      <context>{f.evidence}</context>\n"
                    f"      <gap>{f.issue}</gap>\n"
                    f"      <question>{f.recommendation}</question>\n"
                    f"    </topic>\n"
                )
            brief += "  </topic_group>\n\n"

        if selected_l4:
            brief += '  <topic_group source="L4 -- Founder Comprehension">\n'
            for i, f in enumerate(selected_l4, 1):
                brief += (
                    f'    <topic id="SI-{phase.value}-L4-{i}">\n'
                    f"      <context>{f.evidence}</context>\n"
                    f"      <gap>{f.issue}</gap>\n"
                    f"      <question>{f.recommendation}</question>\n"
                    f"    </topic>\n"
                )
            brief += "  </topic_group>\n\n"

        brief += "</interview_brief>"
        return brief

    def _run_founder_reengagement(
        self,
        phase: PhaseKey,
        brief: str,
    ) -> list[dict[str, str]]:
        """Guide re-engages founder using interview brief."""
        logger.info("Founder re-engagement — Phase %s", phase.value)

        guide_system = (
            "You are the PlatformForge Guide conducting a focused follow-up conversation "
            f"with the founder about their Phase {phase.value} deliverable.\n\n"
            "You have an interview brief with specific topics that need the founder's input. "
            "Your job is to:\n"
            "1. Weave ALL topics into ONE natural conversation (not separate interviews).\n"
            "2. Cover L2 (technical) topics FIRST, L4 (comprehension) topics LAST.\n"
            "3. Ask open questions — do NOT lead the founder to specific answers.\n"
            "4. Capture the founder's answers VERBATIM. Do not summarize or editorialize.\n"
            f"5. After all topics are covered, end with {REENGAGEMENT_COMPLETE_MARKER}.\n\n"
            f"<interview_brief>\n{brief}\n</interview_brief>"
        )

        founder_system = self._persona
        founder_memory = self._store.load_founder_memory()
        if founder_memory:
            founder_system += (
                "\n\n---\n\n<founder_memory>\n"
                "The following is a summary of decisions YOU (the founder) made in prior phases. "
                "Stay consistent with these decisions. Reference them naturally when relevant.\n\n"
                + founder_memory
                + "\n</founder_memory>"
            )
        founder_system += (
            "\n\n---\n\n<reengagement_context>\n"
            f"The PlatformForge Guide is following up on your Phase {phase.value} deliverable. "
            "They have some clarifying questions based on expert review. Answer directly "
            "and specifically — give clear, decisive answers. Your answers will be used to "
            "improve the deliverable.\n"
            "</reengagement_context>"
        )

        guide_messages: list[dict[str, object]] = []
        founder_messages: list[dict[str, object]] = []
        transcript: list[dict[str, str]] = []

        # Guide opens
        guide_messages.append({
            "role": "user",
            "content": "Please begin the follow-up conversation with the founder.",
        })

        guide_job = MessageJob(
            role=RoleName.L2,
            phase=phase,
            label=f"P{phase.value} reengagement-guide",
            system_prompt=guide_system,
            messages=list(guide_messages),
        )
        guide_result = self._gateway.run(guide_job)
        if guide_result.usage:
            self._ledger.record(phase, guide_result.usage)

        guide_text = guide_result.text
        guide_messages.append({"role": "assistant", "content": guide_text})
        transcript.append({
            "role": "guide", "speaker": "Guide", "text": guide_text,
        })

        # Exchange loop
        for exchange in range(MAX_REENGAGEMENT_EXCHANGES):
            if REENGAGEMENT_COMPLETE_MARKER in guide_text:
                logger.info(
                    "Re-engagement complete after %d exchange(s)", exchange
                )
                break

            # Founder responds
            founder_messages.append({"role": "user", "content": guide_text})
            founder_job = MessageJob(
                role=RoleName.FOUNDER,
                phase=phase,
                label=f"P{phase.value} reengagement-founder",
                system_prompt=founder_system,
                messages=list(founder_messages),
                thinking_budget=0,
            )
            founder_result = self._gateway.run(founder_job)
            if founder_result.usage:
                self._ledger.record(phase, founder_result.usage)

            founder_text = founder_result.text
            founder_messages.append({
                "role": "assistant", "content": founder_text,
            })
            transcript.append({
                "role": "founder", "speaker": "Founder", "text": founder_text,
            })

            # Guide follows up
            guide_messages.append({"role": "user", "content": founder_text})
            guide_job = MessageJob(
                role=RoleName.L2,
                phase=phase,
                label=f"P{phase.value} reengagement-guide",
                system_prompt=guide_system,
                messages=list(guide_messages),
            )
            guide_result = self._gateway.run(guide_job)
            if guide_result.usage:
                self._ledger.record(phase, guide_result.usage)

            guide_text = guide_result.text
            guide_messages.append({
                "role": "assistant", "content": guide_text,
            })
            transcript.append({
                "role": "guide", "speaker": "Guide", "text": guide_text,
            })

        # Save transcript
        self._store.save_reengagement_transcript(
            phase, json.dumps(transcript, indent=2, ensure_ascii=False)
        )

        # Extract founder responses
        responses: list[dict[str, str]] = []
        for entry in transcript:
            if entry["role"] == "founder":
                responses.append({
                    "topic_id": "combined", "response": entry["text"],
                })

        return responses

    def _run_targeted_update(
        self,
        phase: PhaseKey,
        deliverable: str,
        brief: str,
        responses: list[dict[str, str]],
    ) -> str:
        """Apply founder responses to deliverable sections."""
        logger.info("Targeted update — incorporating founder responses")

        responses_xml = ""
        for r in responses:
            responses_xml += (
                f'<response topic_id="{r["topic_id"]}">\n'
                f'{r["response"]}\n</response>\n'
            )

        update_prompt = (
            "<founder_update_request>\n"
            f"  <deliverable>\n{deliverable}\n  </deliverable>\n"
            f"  <interview_brief>\n{brief}\n  </interview_brief>\n"
            f"  <founder_responses>\n{responses_xml}  </founder_responses>\n"
            "  <instruction>\n"
            "    For each founder response, update the deliverable section\n"
            "    identified in the corresponding interview brief topic.\n"
            "    Incorporate the founder's answer as authoritative content —\n"
            "    do not paraphrase, soften, or editorialize. The founder's\n"
            "    words represent ground truth about their business.\n"
            "    Do not modify any section not referenced by a topic ID.\n"
            "    Output the complete updated deliverable.\n"
            "  </instruction>\n"
            "</founder_update_request>"
        )

        job = MessageJob(
            role=RoleName.CORRECTION,
            phase=phase,
            label=f"P{phase.value} targeted-update",
            system_prompt=(
                "You are a precise document editor. Incorporate founder responses into the "
                "deliverable sections identified in the interview brief. Preserve all other "
                "content exactly as-is. Output as complete markdown starting with level-1 heading."
            ),
            messages=[{"role": "user", "content": update_prompt}],
        )

        result = self._gateway.run(job)
        if result.usage:
            self._ledger.record(phase, result.usage)

        updated = result.text.strip()
        updated = _strip_synthesis_preamble(updated)

        # Handle truncation with one continuation
        if result.stop_reason == "max_tokens":
            logger.warning("Targeted update truncated — requesting continuation")
            cont_job = MessageJob(
                role=RoleName.CORRECTION,
                phase=phase,
                label=f"P{phase.value} targeted-update-cont",
                system_prompt="Continue outputting the deliverable exactly where you left off.",
                messages=[
                    {"role": "user", "content": update_prompt},
                    {"role": "assistant", "content": updated},
                    {"role": "user", "content": "Continue exactly where you left off. Do not repeat any content."},
                ],
                thinking_budget=0,
            )
            cont_result = self._gateway.run(cont_job)
            if cont_result.usage:
                self._ledger.record(phase, cont_result.usage)
            updated += "\n" + cont_result.text.strip()

        # Safety check
        if len(updated) < len(deliverable) * 0.5:
            logger.warning(
                "Updated deliverable <50%% of original — keeping original"
            )
            return deliverable

        logger.info(
            "Targeted update: %d -> %d chars (%+d)",
            len(deliverable), len(updated), len(updated) - len(deliverable),
        )
        return updated

    @staticmethod
    def _build_review_notes(
        l2_findings: list[ReviewFinding],
        l3_findings: list[ReviewFinding],
        l4_findings: list[ReviewFinding],
        phase: PhaseKey,
    ) -> str:
        """Build companion review notes document from consider items."""
        consider_items = (
            [f for f in l2_findings if f.category == "consider"]
            + [f for f in l3_findings if f.category == "consider"]
            + [f for f in l4_findings if f.category == "consider"]
        )

        if not consider_items:
            return ""

        notes = f"# Phase {phase.value} — Review Notes (Consider Items)\n\n"
        notes += (
            f"> {len(consider_items)} suggestions from expert review. "
            "These are not errors — the deliverable is correct without them.\n\n"
        )

        for f in consider_items:
            notes += f"### {f.id}: {f.section}\n"
            notes += f"- **Issue:** {f.issue}\n"
            notes += f"- **Evidence:** {f.evidence}\n"
            notes += f"- **Suggestion:** {f.recommendation}\n\n"

        return notes
