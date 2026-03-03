"""
PlatformForge Orchestrator — Template Parser (template_parser.py)

Parse phase templates into explicit conversation/synthesis sections,
required elements, and section lists. Read-only — never modifies
template files.

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.1 (Module Map), 2.3 (Synthesis Redesign),
    2.6 Step 3
Fragility Fixes: Problem 1 (implicit template boundaries),
    Rank 5 (synthesis depends on prompt not structure)
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from .contracts import (
    PhaseKey,
    PhaseTemplateSpec,
    RawTemplateBundle,
    RequiredElement,
    SectionSpec,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SYNTHESIS_START_MARKER = "<!-- SYNTHESIS_START"
CONVERSATION_END_MARKER = "<!-- CONVERSATION_END"

# Phase key -> template filename(s)
TEMPLATE_FILE_MAP: dict[str, list[str]] = {
    "1": ["phase-1-conversation.md", "phase-1-synthesis.md"],
    "2": ["phase-2-users.md"],
    "3": ["phase-3-features.md"],
    "4": ["phase-4-data.md"],
    "5": ["phase-5-technical-architecture.md"],
    "6a": ["phase-6a-design-foundation.md"],
    "6b": ["phase-6b-page-architecture.md"],
    "6c": ["phase-6c-interaction-synthesis.md"],
    "7": ["phase-7-build-planning.md"],
    "8": ["phase-8-lifecycle-operations.md"],
    "9": ["phase-9-review-validation.md"],
    "10": ["phase-10-github-push-handoff.md"],
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_phase_template(
    template_root: Path, phase: PhaseKey
) -> RawTemplateBundle:
    """Load template file(s) for a phase from disk.

    For Phase 1: loads two separate files (conversation + synthesis).
    For Phases 2-10: loads one combined file, splits on SYNTHESIS_START.

    Raises FileNotFoundError if any expected template file is missing.
    """
    phase_val = phase.value
    if phase_val not in TEMPLATE_FILE_MAP:
        raise ValueError(
            f"No template mapping for phase '{phase_val}'. "
            f"Valid phases: {list(TEMPLATE_FILE_MAP.keys())}"
        )

    filenames = TEMPLATE_FILE_MAP[phase_val]
    source_paths: list[str] = []

    if phase_val == "1":
        # Phase 1: separate files
        conv_path = template_root / filenames[0]
        synth_path = template_root / filenames[1]

        if not conv_path.exists():
            raise FileNotFoundError(
                f"Phase 1 conversation template not found: {conv_path}"
            )
        if not synth_path.exists():
            raise FileNotFoundError(
                f"Phase 1 synthesis template not found: {synth_path}"
            )

        conversation_raw = conv_path.read_text(encoding="utf-8")
        synthesis_raw = synth_path.read_text(encoding="utf-8")
        source_paths = [str(conv_path), str(synth_path)]
    else:
        # Phases 2-10: single combined file
        combined_path = template_root / filenames[0]
        if not combined_path.exists():
            raise FileNotFoundError(
                f"Template not found for phase {phase_val}: {combined_path}"
            )

        raw = combined_path.read_text(encoding="utf-8")
        conversation_raw, synthesis_raw = _split_on_synthesis_start(
            raw, phase_val
        )
        source_paths = [str(combined_path)]

    return RawTemplateBundle(
        phase=phase,
        conversation_raw=conversation_raw,
        synthesis_raw=synthesis_raw,
        source_paths=source_paths,
    )


def parse_phase_template(
    bundle: RawTemplateBundle,
) -> PhaseTemplateSpec:
    """Parse a RawTemplateBundle into a structured PhaseTemplateSpec.

    Extracts: title, completion gate, output sections, required elements.
    Defensive: missing tags produce empty lists, not errors.
    """
    phase = bundle.phase
    phase_val = phase.value

    # Use synthesis_raw as primary source for structured content.
    # For Phase 1, synthesis_raw IS the synthesis file.
    # For Phases 2-10, synthesis_raw is everything after SYNTHESIS_START.
    primary = bundle.synthesis_raw or bundle.conversation_raw

    # 1. Extract phase title from the first '# ' line in either source
    title = _extract_title(bundle.conversation_raw or bundle.synthesis_raw)

    # 2. Extract completion gate items
    # Some sub-phases (6a, 6b) use <sub_phase_completion_gate>
    gate_text = _extract_tag_content(primary, "phase_completion_gate")
    if not gate_text:
        gate_text = _extract_tag_content(primary, "sub_phase_completion_gate")
    if not gate_text:
        # Also check conversation_raw (some phases have gate before synthesis)
        gate_text = _extract_tag_content(
            bundle.conversation_raw, "phase_completion_gate"
        )
        if not gate_text:
            gate_text = _extract_tag_content(
                bundle.conversation_raw, "sub_phase_completion_gate"
            )
    gate_items = _parse_completion_gate(gate_text)

    # 3. Extract output sections
    outputs_text = _extract_tag_content(primary, "phase_outputs")
    sections, artifact_names = _parse_output_sections(outputs_text, phase)

    # 4. Build required elements
    required_elements = _build_required_elements(gate_items, sections, phase)

    # 5. Build template paths string
    template_path = "; ".join(bundle.source_paths)

    return PhaseTemplateSpec(
        phase=phase,
        deliverable_name=title,
        conversation_instructions=bundle.conversation_raw,
        synthesis_instructions=bundle.synthesis_raw,
        completion_gate=gate_items,
        sections=sections,
        required_elements=required_elements,
        output_artifacts=artifact_names,
        template_path=template_path,
    )


def build_required_element_index(
    spec: PhaseTemplateSpec,
) -> list[RequiredElement]:
    """Return the required elements from a PhaseTemplateSpec.

    Convenience accessor matching the Codex spec public API signature.
    """
    return list(spec.required_elements)


# ---------------------------------------------------------------------------
# Internal: splitting
# ---------------------------------------------------------------------------

def _split_on_synthesis_start(
    raw: str, phase_val: str
) -> tuple[str, str]:
    """Split a combined template on the SYNTHESIS_START marker.

    Returns (conversation_raw, synthesis_raw).
    If marker is missing, entire content goes to synthesis_raw with a warning.
    """
    # Find the marker line
    idx = raw.find(SYNTHESIS_START_MARKER)
    if idx == -1:
        logger.warning(
            "Phase %s: SYNTHESIS_START marker not found. "
            "Entire template treated as synthesis content.",
            phase_val,
        )
        return ("", raw)

    # Also strip CONVERSATION_END if it immediately precedes
    conv_end = raw.rfind(CONVERSATION_END_MARKER, 0, idx)
    if conv_end != -1:
        conversation_raw = raw[:conv_end].rstrip()
    else:
        conversation_raw = raw[:idx].rstrip()

    # Find the end of the SYNTHESIS_START line
    line_end = raw.find("\n", idx)
    if line_end == -1:
        synthesis_raw = ""
    else:
        synthesis_raw = raw[line_end + 1:].lstrip("\n")

    return (conversation_raw, synthesis_raw)


# ---------------------------------------------------------------------------
# Internal: tag extraction
# ---------------------------------------------------------------------------

def _extract_tag_content(text: str, tag_name: str) -> str:
    """Extract content between <tag_name> and </tag_name>.

    Returns the content (stripped), or empty string if not found.
    Only extracts the FIRST occurrence.
    """
    open_tag = f"<{tag_name}>"
    close_tag = f"</{tag_name}>"

    start = text.find(open_tag)
    if start == -1:
        return ""

    start += len(open_tag)
    end = text.find(close_tag, start)
    if end == -1:
        # Open tag found but no close tag — take everything after open
        return text[start:].strip()

    return text[start:end].strip()


def _extract_title(text: str) -> str:
    """Extract the phase title from the first '# ' line.

    Returns the title text after '# ', stripped.
    If no title found, returns 'Untitled Phase'.
    """
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped[2:].strip()
            # Remove 'PlatformForge — ' prefix if present
            prefix = "PlatformForge — "
            if title.startswith(prefix):
                title = title[len(prefix):]
            # Also handle em-dash variant
            prefix_alt = "PlatformForge - "
            if title.startswith(prefix_alt):
                title = title[len(prefix_alt):]
            return title
    return "Untitled Phase"


# ---------------------------------------------------------------------------
# Internal: completion gate parsing
# ---------------------------------------------------------------------------

def _parse_completion_gate(gate_text: str) -> list[str]:
    """Parse completion gate checklist items.

    Each item starts with '- [ ] '. Returns cleaned text for each item.
    """
    if not gate_text:
        return []

    items: list[str] = []
    current_item: list[str] = []

    for line in gate_text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- [ ] "):
            # Save previous item if any
            if current_item:
                items.append(" ".join(current_item))
            # Start new item — strip the checkbox marker and bold markers
            text = stripped[6:].strip()
            text = _strip_bold_prefix(text)
            current_item = [text]
        elif current_item and stripped and not stripped.startswith("-"):
            # Continuation of current item
            current_item.append(stripped)

    # Save last item
    if current_item:
        items.append(" ".join(current_item))

    return items


def _strip_bold_prefix(text: str) -> str:
    """Remove leading **...** bold wrapper if present."""
    if text.startswith("**") and "**" in text[2:]:
        # Find the closing **
        end = text.index("**", 2)
        inner = text[2:end]
        rest = text[end + 2:].strip()
        if rest:
            return f"{inner} {rest}"
        return inner
    return text


# ---------------------------------------------------------------------------
# Internal: output section parsing
# ---------------------------------------------------------------------------

def _parse_output_sections(
    outputs_text: str, phase: PhaseKey
) -> tuple[list[SectionSpec], list[str]]:
    """Parse <phase_outputs> content into SectionSpec list and artifact names.

    Handles multiple patterns found across templates:
    - '**N. Title**'           (Phases 2-5)
    - '**Deliverable N: Title**' (Phases 6c, 7, 8)
    - '**Section N — Title**'  (Phases 6c, 7 — sub-sections within a deliverable)
    - '**Title**' (no number)  (Phases 9, 10 — single deliverables)

    For phases with Deliverable + Section format, the Deliverable line is
    the primary artifact and Sections are the SectionSpecs within it.

    Returns (sections, artifact_names).
    """
    phase_val = phase.value

    if not outputs_text:
        # Fallback: single whole-document section
        return (
            [SectionSpec(
                section_id=f"{phase_val}-s0",
                title="Complete Deliverable",
                required_elements=[],
            )],
            [],
        )

    sections: list[SectionSpec] = []
    artifact_names: list[str] = []
    section_count = 0

    # Pattern 1: **N. Title** (with optional closing **)
    pat_numbered = re.compile(
        r"^\*\*(\d+)\.\s+(.+?)(?:\*\*)?$"
    )
    # Pattern 2: **Deliverable N: Title**
    pat_deliverable = re.compile(
        r"^\*\*Deliverable\s+(\d+):\s+(.+?)(?:\*\*)?$"
    )
    # Pattern 3: **Section N — Title** or **Section N - Title**
    pat_section = re.compile(
        r"^\*\*Section\s+(\d+)\s*[—–\-]+\s*(.+?)(?:\*\*)?$"
    )
    # Pattern 4: ## Section N: Title or ## N. Title
    pat_heading = re.compile(
        r"^##\s+(?:Section\s+)?(\d+)[.:]\s+(.+)$"
    )
    # Pattern 5: Standalone bold title (no number) — e.g. **Validation Report**
    # Only used as fallback if no numbered patterns match
    pat_bold_title = re.compile(
        r"^\*\*([A-Z][^*]+?)(?:\*\*)?$"
    )

    # Strip fenced code blocks to avoid false pattern matches
    stripped_text = _strip_code_blocks(outputs_text)

    has_deliverable_pattern = False
    has_section_pattern = False

    # First pass: detect which patterns are present
    for line in stripped_text.split("\n"):
        stripped = line.strip()
        if pat_deliverable.match(stripped):
            has_deliverable_pattern = True
        if pat_section.match(stripped):
            has_section_pattern = True

    # Second pass: extract sections
    # Strategy: if Deliverable+Section format, Sections become SectionSpecs
    # and Deliverables become artifact names.
    # If only numbered (**N. Title**), those are the sections.
    # If only bold titles, those become single sections.

    for line in stripped_text.split("\n"):
        stripped = line.strip()

        # Try Deliverable pattern (artifact name, not a section)
        m_deliv = pat_deliverable.match(stripped)
        if m_deliv:
            title = m_deliv.group(2).strip().rstrip("*").strip()
            artifact_names.append(title)
            # If no section sub-patterns, the deliverable IS the section
            if not has_section_pattern:
                section_count += 1
                sections.append(SectionSpec(
                    section_id=f"{phase_val}-s{section_count}",
                    title=title,
                    required_elements=[],
                ))
            continue

        # Try Section pattern (within a deliverable)
        m_sec = pat_section.match(stripped)
        if m_sec:
            section_count += 1
            title = m_sec.group(2).strip().rstrip("*").strip()
            sections.append(SectionSpec(
                section_id=f"{phase_val}-s{section_count}",
                title=title,
                required_elements=[],
            ))
            continue

        # Try numbered pattern (**N. Title**)
        m_num = pat_numbered.match(stripped)
        if m_num and not has_deliverable_pattern:
            section_count += 1
            title = m_num.group(2).strip().rstrip("*").strip()
            sections.append(SectionSpec(
                section_id=f"{phase_val}-s{section_count}",
                title=title,
                required_elements=[],
            ))
            artifact_names.append(title)
            continue

        # Try heading pattern
        m_head = pat_heading.match(stripped)
        if m_head:
            section_count += 1
            title = m_head.group(2).strip()
            sections.append(SectionSpec(
                section_id=f"{phase_val}-s{section_count}",
                title=title,
                required_elements=[],
            ))
            artifact_names.append(title)
            continue

    # If no structured sections found, try standalone bold titles
    if not sections:
        for line in stripped_text.split("\n"):
            stripped = line.strip()
            m_bold = pat_bold_title.match(stripped)
            if m_bold:
                title = m_bold.group(1).strip().rstrip("*").strip()
                # Skip lines that look like instructions, not titles
                if len(title) > 80 or title.endswith(":"):
                    continue
                section_count += 1
                sections.append(SectionSpec(
                    section_id=f"{phase_val}-s{section_count}",
                    title=title,
                    required_elements=[],
                ))
                artifact_names.append(title)

    if not sections:
        # Ultimate fallback
        sections.append(SectionSpec(
            section_id=f"{phase_val}-s0",
            title="Complete Deliverable",
            required_elements=[],
        ))

    return (sections, artifact_names)


# ---------------------------------------------------------------------------
# Internal: required elements
# ---------------------------------------------------------------------------

def _build_required_elements(
    gate_items: list[str],
    sections: list[SectionSpec],
    phase: PhaseKey,
) -> list[RequiredElement]:
    """Build RequiredElement list from gate items and sections."""
    phase_val = phase.value
    elements: list[RequiredElement] = []

    # From completion gate items
    for idx, item in enumerate(gate_items):
        # Extract the first sentence as the name
        name = _first_sentence(item)
        elements.append(RequiredElement(
            name=name,
            description=item,
            validation_rule="",
        ))

    # From sections — each section is a required element
    for sec in sections:
        elements.append(RequiredElement(
            name=f"Section: {sec.title}",
            description=f"Deliverable must contain section '{sec.title}' "
            f"(id: {sec.section_id}).",
            validation_rule="",
        ))

    return elements


def _first_sentence(text: str) -> str:
    """Extract the first sentence from text (up to first period + space or end)."""
    # Find first sentence boundary
    for i, ch in enumerate(text):
        if ch == "." and i + 1 < len(text) and text[i + 1] == " ":
            return text[: i + 1]
    # No period found — use first 100 chars
    if len(text) > 100:
        return text[:100] + "..."
    return text


def _strip_code_blocks(text: str) -> str:
    """Remove fenced code blocks (``` ... ```) to avoid false pattern matches."""
    lines = text.split("\n")
    result: list[str] = []
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            result.append(line)

    return "\n".join(result)
