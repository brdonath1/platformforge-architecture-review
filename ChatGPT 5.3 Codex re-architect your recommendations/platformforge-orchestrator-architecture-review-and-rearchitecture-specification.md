# PlatformForge Orchestrator — Architecture Review & Re-Architecture Specification

**Reviewing Model:** GPT-5 Codex
**Date:** 2026-03-03
**Files Analyzed:** `ANALYSIS-BRIEF.md`; `code/main.py`; `code/CLAUDE.md`; `architecture/d188-review-architecture.md`; `architecture/module-architecture.md`; `architecture/compliance-checklist.md`; `templates/phase-1-synthesis.md`; `templates/phase-2-users.md`; `personas/review-config.md`; `personas/l2-domain-experts.md`; `personas/l3-downstream-consumers.md`; `personas/l4-founder-comprehension.md`; `scenario/persona.md`; `evidence/metrics/cross-phase-consistency.json`; `evidence/metrics/cost-report.json`; `evidence/metrics/timing-waterfall.json`; `evidence/metrics/phase-{1,2,3,4,5,6a,6b,6c,7,8,9,10}-metrics.json`; `evidence/review-pipelines/phase-{1,2,3,4,5,6a,6b,6c,7,8,9,10}-review-pipeline.json`; `evidence/expert-reviews/phase-6a-l2-review.json`; `evidence/expert-reviews/phase-8-l3-review.json`; `evidence/expert-reviews/phase-10-l4-review.json`; `evidence/interview-briefs/phase-6a-interview-brief.xml`; `evidence/corrections-sample/phase-6a-correction-9-raw.txt`; `deliverables-sample/phase-1-deliverable.md`; `deliverables-sample/phase-6a-deliverable.md`; `deliverables-sample/phase-8-deliverable.md`; `deliverables-sample/founder-memory.md`

---

## PHASE 1: ARCHITECTURE REVIEW

### 1.1 System Comprehension Summary
The orchestrator is a single-file control plane centered on `run_phase()` and `main()` in `code/main.py` (lines 3820-4273). `main()` resolves config, loads prompt/persona assets, initializes the run, and iterates `PHASE_ORDER`; `run_phase()` then performs one full phase by loading template(s), concatenating prior deliverables, running the Guide/Founder conversation, generating the phase deliverable, running the D-188 review pipeline, updating founder memory, writing metrics, and pushing outputs to GitHub. The entire platform lifecycle, from Anthropic transport details to GitHub publishing, is implemented in one file.

The conversation layer lives in `run_conversation()` (1142-1383) and depends on `call_api()` / `_execute_stream()` (401-790) plus `call_guide_with_research()` (2305-2407). The Guide prompt is built from the master prompt plus the phase template and prior deliverables; the Founder prompt is the scenario persona plus generated founder memory from prior outputs (`generate_founder_memory()`, 1724-1789). Research can be server-side Anthropic `web_search` or client-side Perplexity/Grok adapters. Conversation output is persisted as transcript JSON/Markdown and later used as synthesis input.

The synthesis layer is `run_synthesis()` (1395-1564). It builds a single large system prompt from the synthesis preamble, master prompt, and synthesis template, then passes prior deliverables and the full transcript as one user message. For Phase 1 it uses the dedicated synthesis template; for Phases 2-10 `get_synthesis_template()` (1571-1581) returns the entire combined template file unchanged. Although `validate_deliverable()` exists (2427-2521), it is not called from `run_phase()`, so structural quality is not enforced before review.

The review/publishing side is `run_review_pipeline()` (3587-3817), `run_correction_synthesis()` / `apply_patches()` (2974-3224), `run_founder_reengagement()` / `run_targeted_update()` (3320-3555), and `run_cross_phase_consistency_check()` (3970-4078). The current design does L1 compliance first, then parallel L2/L3/L4 review, then one merged correction pass, then founder re-engagement for should-improve items, then final L1. Cross-phase state is handled by `load_prior_deliverables()` (2528-2612) and append-only founder memory (`update_founder_memory_after_synthesis()`, 1792-1843), not by typed shared state. Publishing is immediate via `git_push_output()` (265-354), which pushes every output file to GitHub after each phase.

### 1.2 Architectural Problems

**Problem 1: Template mode boundaries are implicit and ignored by synthesis**
- **Location:** `run_synthesis()` (1395-1564), `get_synthesis_template()` (1571-1581), `validate_deliverable()` (2427-2521)
- **What happens:** For Phases 2-10 the system passes the entire combined template into synthesis, including conversation-only instructions that appear before `<!-- SYNTHESIS_START -->`. The code never parses that marker, never builds a section checklist, and never calls the structural validator.
- **Why it is a problem:** The architecture treats prompt text as an executable contract without converting it into structured generation requirements. That makes section completeness probabilistic and shifts mechanical template compliance into the review pipeline instead of the synthesis pipeline.
- **Evidence:** `templates/phase-2-users.md` contains a conversation section and a `<!-- SYNTHESIS_START -->` boundary, but `get_synthesis_template()` returns the whole file unchanged. The run still accumulated 158 initial L1 misses across 12 phase units, including 65 in Phase 6a, 30 in Phase 5, 27 in Phase 6c, 21 in Phase 8, and 10 in Phase 1 (`evidence/review-pipelines/phase-6a-review-pipeline.json`, `phase-5-review-pipeline.json`, `phase-6c-review-pipeline.json`, `phase-8-review-pipeline.json`, `phase-1-review-pipeline.json`).

**Problem 2: Cross-phase state is unmanaged prose instead of canonical facts**
- **Location:** `generate_founder_memory()` (1724-1789), `update_founder_memory_after_synthesis()` (1792-1843), `load_prior_deliverables()` (2528-2612), `run_cross_phase_consistency_check()` (3970-4078)
- **What happens:** Prior outputs are injected as concatenated markdown; founder memory is appended phase by phase; Haiku runs truncate older prior deliverables to fit a character budget; consistency is checked only after all phases finish.
- **Why it is a problem:** There is no canonical registry for shared facts such as pricing, counts, permissions, service inventory, or standards. When later phases refine a fact, the system has no durable supersession mechanism, so old values remain alive in prior artifacts and founder memory.
- **Evidence:** `evidence/metrics/cross-phase-consistency.json` reports `consistency_score: 72` and `total_issues: 14`, including contradictions in course/property counts, Stripe fee rate, infrastructure cost, service-fee tiers, permissions, WCAG target, RLS syntax, and service count. `deliverables-sample/founder-memory.md` contains three separate and conflicting “Phase 1” summaries with incompatible business-model and scaling decisions.

**Problem 3: The review pipeline is compensating for synthesis, not reviewing it**
- **Location:** `run_l1_compliance()` (2709-2772), `run_review_pipeline()` (3587-3817), `build_interview_brief()` (3227-3311)
- **What happens:** The review pipeline routinely adds large amounts of content, triggers founder re-engagement in every phase, and spends more wall time than synthesis itself.
- **Why it is a problem:** Review is supposed to verify a mostly-correct draft. Here it is functioning as a second authoring stage because the upstream generation architecture does not produce stable, structurally complete, fact-consistent outputs.
- **Evidence:** All 12 review-pipeline summaries show `reengagement_triggered: true`. Review added 26,856 to 148,880 characters per phase, reaching 72.8% of final size in Phase 6a, 61.9% in Phase 8, 60.9% in Phase 10, 56.4% in Phase 9, and 53.0% in Phase 5 (`evidence/review-pipelines/*.json`, `evidence/metrics/phase-*-metrics.json`). Average review time was 979 seconds, versus 225 seconds for synthesis and 468 seconds for conversation (`evidence/metrics/phase-*-metrics.json`).

**Problem 4: Correction and re-engagement lack stable identifiers, so edits are lossy**
- **Location:** `parse_correction_patches()` (2948-2971), `apply_patches()` (2974-3095), `run_correction_synthesis()` (3098-3224), `build_interview_brief()` (3227-3311), `run_founder_reengagement()` (3457-3463), `run_targeted_update()` (3467-3555)
- **What happens:** Must-fix corrections are targeted with literal headings and `search_text` snippets plus fuzzy matching. Interview topics have IDs, but founder responses are collapsed to `topic_id="combined"`. Targeted update then regenerates the complete deliverable instead of patching specific sections.
- **Why it is a problem:** The architecture has no section identity layer. Without stable section IDs and finding-to-section bindings, the system cannot guarantee that a correction touches only the intended content or that founder answers map back to the exact issue that triggered them.
- **Evidence:** `evidence/corrections-sample/phase-6a-correction-9-raw.txt` shows a large raw XML patch that inserts placeholder-heavy sections; `deliverables-sample/phase-6a-deliverable.md` contains duplicated headings and malformed joins (`"EXECUTED ...### 0.0"`), indicating correction damage; `evidence/interview-briefs/phase-6a-interview-brief.xml` contains topic IDs such as `SI-6a-L2-1`, but code later converts all founder replies to `"combined"`.

**Problem 5: Cross-phase consistency is post-hoc and non-blocking**
- **Location:** `run_phase()` (3883-3908), `run_cross_phase_consistency_check()` (3970-4078)
- **What happens:** Each phase publishes immediately after local review. The only global consistency pass runs after the run is already complete and explicitly “does NOT block.”
- **Why it is a problem:** Once later phases consume stale or contradictory facts, the defect propagates into more artifacts. A final report can observe those contradictions, but the architecture provides no closed-loop mechanism to repair upstream sources and reflow downstream outputs.
- **Evidence:** `evidence/metrics/cross-phase-consistency.json` repeatedly states that Phase 9 identified or corrected issues but the earlier deliverable body text still contains the old values, including the 14-vs-15 course count, 11-vs-12 property count, outdated pricing tiers, outdated Stripe fee assumptions, and the D2/D5/D7 permission mismatch.

**Problem 6: Cost and timing governance are not durable across resumed runs**
- **Location:** `CostTracker.save_report()` (1110-1135), `main()` (4182-4252)
- **What happens:** Cost totals and timing waterfall are built from in-memory counters for the current process and then written to “latest” files at the end of that process.
- **Why it is a problem:** Long-running orchestration with resume support needs persistent budget state. Without it, the $200 ceiling, run-level observability, and performance analysis become inaccurate as soon as the run is restarted.
- **Evidence:** `evidence/metrics/cost-report.json` and `evidence/metrics/timing-waterfall.json` contain only Phase 10 data, while `evidence/metrics/phase-{1,2,3,4,5,6a,6b,6c,7,8,9,10}-metrics.json` proves that metrics exist for all 12 phase units.

### 1.3 Root Cause Analysis

**Root Cause A: Prompt text is being used as the system’s primary interface contract**
- **Problems it causes:** 1, 3, 4
- **Architectural mechanism:** Templates, findings, and corrections are all represented as free-form markdown/XML generated by the model, not as parsed section graphs or typed change objects. Because the system never transforms templates into explicit generation units, synthesis, review, and correction all operate on opaque text blobs.
- **Evidence chain:** `get_synthesis_template()` passes raw combined templates into `run_synthesis()`; `validate_deliverable()` is not in the phase path; L1 then reports 158 initial structural misses; review/correction subsequently adds massive deltas and malformed section insertions (`evidence/review-pipelines/*.json`, `deliverables-sample/phase-6a-deliverable.md`).

**Root Cause B: There is no canonical cross-phase state registry with supersession rules**
- **Problems it causes:** 2, 5, 6
- **Architectural mechanism:** Shared facts live only inside markdown deliverables and append-only founder memory. Later phases can mention newer values, but no central mechanism marks the older value superseded, updates dependents, or persists run-wide budget/fact state across resumes.
- **Evidence chain:** `load_prior_deliverables()` concatenates prose and truncates it for Haiku; `update_founder_memory_after_synthesis()` only appends; `run_cross_phase_consistency_check()` discovers 14 unresolved contradictions after the run; `cost-report.json` and `timing-waterfall.json` reset to only the last resumed process.

**Root Cause C: Quality control is placed after full-document generation instead of inside generation**
- **Problems it causes:** 1, 3, 5
- **Architectural mechanism:** The system generates a complete deliverable first, then asks L1/L2/L3/L4 to discover omissions and contradictions. Because there is no section-by-section validation gate and no fact registry check during generation, the review pipeline is forced to backfill missing content and re-resolve old decisions.
- **Evidence chain:** Review time averages 979s versus 225s for synthesis; every phase triggers re-engagement; correction deltas are frequently 30-70% of final deliverable size; cross-phase contradictions remain unresolved even after late review.

**Root Cause D: Change application is based on brittle textual locality instead of structural identity**
- **Problems it causes:** 4
- **Architectural mechanism:** Corrections target headings and verbatim snippets, and founder re-engagement loses topic identity before the update step. The system therefore cannot perform safe, minimal edits to named sections or fact records.
- **Evidence chain:** `apply_patches()` relies on `search_text` occurrence counts and fuzzy whitespace normalization; `run_founder_reengagement()` emits `"combined"` responses; Phase 6a’s correction sample and resulting deliverable show duplicated/misaligned section content.

### 1.4 Fragility Map (Top 10)

**Rank 1: `load_prior_deliverables` (2528-2612)**
- **Why it is fragile:** It silently switches from “all prior context” to “truncate oldest prose” based on model tier.
- **Blast radius:** Any phase can lose foundational decisions, causing downstream drift in pricing, counts, permissions, and architecture.
- **Recommended fix:** Replace prose loading with a typed registry slice keyed by fact domains and required sections.

**Rank 2: `run_correction_synthesis` + `apply_patches` (2974-3224)**
- **Why it is fragile:** It depends on exact headings/snippets remaining stable across model rewrites.
- **Blast radius:** A small formatting change can cause skipped patches, duplicate sections, or structural corruption.
- **Recommended fix:** Patch by section IDs and content hashes, not free-text anchors.

**Rank 3: `run_targeted_update` (3467-3555)**
- **Why it is fragile:** It performs full-document regeneration after founder follow-up.
- **Blast radius:** A localized clarification can rewrite unrelated sections and invalidate earlier review work.
- **Recommended fix:** Regenerate only explicitly targeted sections and reassemble the document deterministically.

**Rank 4: `run_review_pipeline` (3587-3817)**
- **Why it is fragile:** It is carrying structural QA, technical review, comprehension review, correction orchestration, and founder re-engagement in one control path.
- **Blast radius:** Any step-numbering, retry, or finding-shape change affects the whole phase lifecycle.
- **Recommended fix:** Split into explicit review, merge, correction, and revalidation stages over typed DTOs.

**Rank 5: `run_synthesis` + `get_synthesis_template` (1395-1581)**
- **Why it is fragile:** Synthesis behavior depends on prompt composition rather than parsed template semantics.
- **Blast radius:** Template edits or marker placement changes can degrade every downstream deliverable.
- **Recommended fix:** Parse templates into section specs, required outputs, and bounded generation batches.

**Rank 6: `update_founder_memory_after_synthesis` (1792-1843)**
- **Why it is fragile:** It only appends new narrative summaries and never resolves superseded facts.
- **Blast radius:** Founder simulation drifts, and inconsistent founder answers contaminate later phases.
- **Recommended fix:** Generate founder memory from the active fact registry, not by accumulating prose deltas.

**Rank 7: `_execute_stream` (401-605)**
- **Why it is fragile:** It mixes vendor-specific streaming semantics, progress UI, usage accounting, and fallback parsing.
- **Blast radius:** Small SDK/event-format changes can break all API calls or corrupt replayable content blocks.
- **Recommended fix:** Isolate transport parsing behind a narrow gateway with contract tests using recorded events.

**Rank 8: `serialize_for_replay` + `call_guide_with_research` (878-953, 2305-2407)**
- **Why it is fragile:** Tool continuation correctness depends on preserving opaque content-block details exactly.
- **Blast radius:** Research-enabled Guide turns can fail or diverge unpredictably when replay semantics change.
- **Recommended fix:** Treat tool continuations as first-class message objects with validated schemas and replay tests.

**Rank 9: `run_cross_phase_consistency_check` (3970-4078)**
- **Why it is fragile:** It attempts one giant end-of-run audit over full deliverable prose.
- **Blast radius:** It can detect issues late but cannot drive targeted remediation or prevent propagation.
- **Recommended fix:** Move consistency checks into per-phase state commits and section promotion gates.

**Rank 10: `CostTracker.save_report` + run waterfall write path (1110-1135, 4240-4252)**
- **Why it is fragile:** Run totals exist only in process memory and are overwritten on resume.
- **Blast radius:** Budget enforcement, benchmarking, and comparison across runs become misleading.
- **Recommended fix:** Persist reserved and actual cost/timing state transactionally after each step.

### 1.5 Cross-Phase Consistency Analysis
- Current consistency score and number of issues found: `evidence/metrics/cross-phase-consistency.json` records `consistency_score: 72` and `total_issues: 14`.
- Categories of drift:
  Pricing/cost drift: Stripe effective fee, Day Zero infrastructure cost, service-fee tier changes.
  Counts/entity drift: course count, property count, course-contact parent entity, trip-history count.
  Permissions drift: D2/D5/D7 referral-partner permissions differ.
  Service inventory drift: 8-vs-9 service count and missing 1Password propagation.
  Standards/schema drift: WCAG 2.1 vs 2.2, bad JWT path in RLS examples, wrong cross-reference label.
- Architectural cause of each drift category:
  Pricing/cost drift: monetary assumptions are copied into prose tables instead of referenced from a shared financial fact set.
  Counts/entity drift: entity names and counts are refined in later phases, but prior artifacts are never superseded structurally.
  Permissions drift: permission rules are authored independently in user, API, and build docs without a single permission contract.
  Service inventory drift: external services are tracked in multiple checklists/manifests rather than a typed service registry.
  Standards/schema drift: standards and implementation snippets are duplicated manually across deliverables instead of imported from one canonical spec.
- Which phases are most affected and why:
  Phase 9 is the most visible correction surface because it discovers and documents contradictions, but it cannot repair the original source artifacts.
  Phases 7 and 8 are heavily affected because build/operations artifacts refine pricing, service sequencing, and infrastructure choices after earlier documents have already frozen those facts.
  Phases 1, 2, 4, and 5 are the main contradiction sources because they introduce foundational facts about counts, pricing, permissions, schema, and standards that later phases must reuse exactly.
  In practical terms, the architecture has no “fact promotion” step, so any late refinement creates a dual-truth condition rather than a clean update.

### 1.6 Review Pipeline Effectiveness
- L1 initial miss counts per phase: Phase 1 = 10, Phase 2 = 0, Phase 3 = 0, Phase 4 = 0, Phase 5 = 30, Phase 6a = 65, Phase 6b = 0, Phase 6c = 27, Phase 7 = 0, Phase 8 = 21, Phase 9 = 5, Phase 10 = 0 (`evidence/review-pipelines/phase-*-review-pipeline.json`).
- Correction deltas per phase: Phase 1 = +26,856 chars, Phase 2 = +53,687, Phase 3 = +36,508, Phase 4 = +55,715, Phase 5 = +106,221, Phase 6a = +140,370, Phase 6b = +49,783, Phase 6c = +83,526, Phase 7 = +34,079, Phase 8 = +148,880, Phase 9 = +61,882, Phase 10 = +31,797 (`evidence/review-pipelines/*.json`).
- Whether the pipeline is doing review work or authorship work: It is doing both, but the deltas and timings show it is primarily compensatory authorship. A true review layer should not routinely add 30-70% of the final document after synthesis.
- Expert review finding quality: Mixed.
  `evidence/expert-reviews/phase-8-l3-review.json` contains strong downstream findings, including duplicated C8/C9 credential timing and a still-unresolved hosting-provider placeholder.
  `evidence/expert-reviews/phase-10-l4-review.json` identifies real founder-comprehension gaps around credentials and build-card jargon.
  `evidence/expert-reviews/phase-6a-l2-review.json` spends multiple must-fix findings on research execution timestamp/provenance details, which is document traceability work more than design-quality review.
- Re-engagement effectiveness: Weak relative to design intent.
  The brief says re-engagement should ask open questions, but `build_interview_brief()` copies recommendations directly into `<question>` fields; the sample in `evidence/interview-briefs/phase-6a-interview-brief.xml` contains imperative prompts like “Add:” and “Clarify:” rather than founder-discovery questions.
  The cap of 8 topics discards large parts of the should-improve set; Phase 6a had 25 should-improve findings but only 8 topics survived into the interview brief.
  Topic ID preservation fails in code because `run_founder_reengagement()` stores all founder answers under `"combined"`.
- Net assessment: The pipeline catches genuine problems, but it is not achieving its stated design intent as a clean layered QA system. It is expensive, late, lossy, and authorial. The architecture preserves the idea of L1/L2/L3/L4, but the implementation uses those layers to rescue unstable drafts rather than certify stable ones.

---

## PHASE 2: RE-ARCHITECTURE SPECIFICATION

### 2.1 Module Map

**Module: `contracts.py`**
- **Responsibility:** Define all shared types, enums, Pydantic models, and protocols used across the orchestrator.
- **Imports from:** []
- **Public API:**
  ```python
  def phase_key(value: str | int) -> PhaseKey: ...
  def role_name(value: str) -> RoleName: ...
  def fact_key(namespace: str, subject: str, attribute: str) -> str: ...
  ```

**Module: `settings.py`**
- **Responsibility:** Load runtime configuration, resolve the active model tier, and compute role-level execution policy.
- **Imports from:** `contracts.py`
- **Public API:**
  ```python
  def load_app_config(path: Path | None = None) -> AppConfig: ...
  def resolve_role_policy(config: AppConfig, role: RoleName) -> RoleExecutionPolicy: ...
  def estimate_reserved_cost(config: AppConfig, jobs: Sequence[MessageJob]) -> Decimal: ...
  ```

**Module: `template_parser.py`**
- **Responsibility:** Parse phase templates into explicit conversation/synthesis sections, required elements, and section dependency graphs.
- **Imports from:** `contracts.py`
- **Public API:**
  ```python
  def load_phase_template(template_root: Path, phase: PhaseKey) -> RawTemplateBundle: ...
  def parse_phase_template(bundle: RawTemplateBundle) -> PhaseTemplateSpec: ...
  def build_required_element_index(spec: PhaseTemplateSpec) -> list[RequiredElement]: ...
  ```

**Module: `llm_gateway.py`**
- **Responsibility:** Provide the only interface to Anthropic Messages API, Anthropic `web_search`, Perplexity, and Grok, including retry, thinking normalization, parallel dispatch, and cost estimation.
- **Imports from:** `contracts.py`, `settings.py`
- **Public API:**
  ```python
  class AnthropicGateway:
      def run(self, job: MessageJob) -> MessageResult: ...
      def run_parallel(self, jobs: Sequence[MessageJob]) -> list[MessageResult]: ...
      def estimate_cost(self, job: MessageJob) -> Decimal: ...
  ```

**Module: `run_store.py`**
- **Responsibility:** Persist durable run state: cross-phase registry, artifacts, metrics, reserved budget, and GitHub publishing state.
- **Imports from:** `contracts.py`, `settings.py`
- **Public API:**
  ```python
  def open_run_store(config: AppConfig) -> RunStore: ...

  class RunStore:
      def load_registry(self) -> StateRegistry: ...
      def save_registry(self, registry: StateRegistry) -> None: ...
      def reserve_budget(self, jobs: Sequence[MessageJob]) -> None: ...
      def reconcile_budget(self, actual_calls: Sequence[CallUsage]) -> None: ...
      def load_phase_inputs(self, phase: PhaseKey) -> PhaseInputs: ...
      def commit_phase_result(self, result: PhaseResult) -> None: ...
      def publish_phase(self, phase: PhaseKey) -> PublishResult: ...
  ```

**Module: `phase_service.py`**
- **Responsibility:** Execute one phase end-to-end: context preparation, conversation, section-batch synthesis, validation, review pipeline, correction, re-engagement, and artifact assembly.
- **Imports from:** `contracts.py`, `llm_gateway.py`, `template_parser.py`
- **Public API:**
  ```python
  class PhaseService:
      def prepare_phase_context(self, phase: PhaseKey, inputs: PhaseInputs) -> PhaseContext: ...
      def run_conversation(self, context: PhaseContext) -> ConversationResult: ...
      def run_synthesis(self, context: PhaseContext, conversation: ConversationResult) -> DeliverableArtifact: ...
      def run_review_pipeline(self, context: PhaseContext, deliverable: DeliverableArtifact) -> ReviewPipelineResult: ...
      def execute_phase(self, phase: PhaseKey, store: RunStore) -> PhaseResult: ...
  ```

**Module: `orchestrator.py`**
- **Responsibility:** Compose the run, sequence phases, enforce the hard cost ceiling, support resume, and run cross-phase audit on the canonical registry.
- **Imports from:** `settings.py`, `run_store.py`, `phase_service.py`
- **Public API:**
  ```python
  def build_orchestrator(config_path: Path | None = None) -> Orchestrator: ...

  class Orchestrator:
      def run(self, start_phase: PhaseKey | None = None, max_phases: int | None = None) -> RunResult: ...
      def resume(self, run_id: str, start_phase: PhaseKey) -> RunResult: ...
      def audit_cross_phase_consistency(self) -> ConsistencyReport: ...
  ```

**Data Flow Diagram:**
```text
settings.py
   -> orchestrator.py
      -> run_store.py.load_phase_inputs()
      -> template_parser.py.parse_phase_template()
      -> phase_service.py.execute_phase()
         -> llm_gateway.py.run()                [conversation batches]
         -> llm_gateway.py.run()                [section synthesis batches]
         -> phase-local L1 validation
         -> llm_gateway.py.run_parallel()       [L2/L3/L4]
         -> llm_gateway.py.run()                [targeted corrections]
         -> llm_gateway.py.run()                [founder re-engagement]
      -> run_store.py.commit_phase_result()
      -> run_store.py.publish_phase()
      -> orchestrator.py.audit_cross_phase_consistency()
         -> run_store.py.load_registry()
```

### 2.2 Data Contracts

**2.2.1 Core Types**
```python
from datetime import datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Protocol, Sequence

from pydantic import BaseModel, Field


class PhaseKey(str, Enum):
    P1 = "1"
    P2 = "2"
    P3 = "3"
    P4 = "4"
    P5 = "5"
    P6A = "6a"
    P6B = "6b"
    P6C = "6c"
    P7 = "7"
    P8 = "8"
    P9 = "9"
    P10 = "10"


class RoleName(str, Enum):
    GUIDE = "guide"
    FOUNDER = "founder"
    SYNTHESIS = "synthesis"
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    L4 = "l4"
    CORRECTION = "correction"
    CONSISTENCY = "consistency"


class ArtifactKind(str, Enum):
    CONVERSATION = "conversation"
    DELIVERABLE = "deliverable"
    REVIEW_NOTES = "review_notes"
    INTERVIEW_BRIEF = "interview_brief"
    FOUNDER_MEMORY = "founder_memory"
    METRICS = "metrics"


class SectionSpec(BaseModel):
    section_id: str
    heading: str
    level: int
    required: bool
    depends_on_section_ids: list[str] = Field(default_factory=list)
    depends_on_fact_keys: list[str] = Field(default_factory=list)
    reviewer_layers: set[Literal["L1", "L2", "L3", "L4"]] = Field(default_factory=set)


class RequiredElement(BaseModel):
    element_id: str
    section_id: str
    description: str
    kind: Literal["section", "subsection", "field", "appendix", "manifest", "sentinel"]


class PhaseTemplateSpec(BaseModel):
    phase: PhaseKey
    conversation_instructions: str
    synthesis_instructions: str
    required_elements: list[RequiredElement]
    sections: list[SectionSpec]
    output_artifacts: list[str]


class ConversationTurn(BaseModel):
    turn_id: str
    role: Literal["guide", "founder"]
    text: str
    citations: list[str] = Field(default_factory=list)
    tool_events: list[str] = Field(default_factory=list)


class ConversationResult(BaseModel):
    phase: PhaseKey
    turns: list[ConversationTurn]
    transcript_markdown: str
    founder_memory_snapshot: str


class DeliverableArtifact(BaseModel):
    phase: PhaseKey
    artifact_id: str
    kind: ArtifactKind
    title: str
    markdown: str
    section_order: list[str]
    section_hashes: dict[str, str]
    fact_keys: list[str]
    version: int


class PhaseContext(BaseModel):
    phase: PhaseKey
    template: PhaseTemplateSpec
    founder_memory: str
    active_fact_keys: list[str]
    prior_artifacts: list[str]


class CallUsage(BaseModel):
    role: RoleName
    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal


class PhaseMetrics(BaseModel):
    phase: PhaseKey
    conversation_seconds: int
    synthesis_seconds: int
    review_seconds: int
    total_seconds: int
    deliverable_chars: int
    reserved_cost_usd: Decimal
    actual_cost_usd: Decimal


class PhaseResult(BaseModel):
    phase: PhaseKey
    conversation: ConversationResult
    deliverable: DeliverableArtifact
    review_notes: str = ""
    metrics: PhaseMetrics
```

**2.2.2 Cross-Phase State Registry Schema**
```python
class FactSource(BaseModel):
    phase: PhaseKey
    artifact_id: str
    section_id: str
    captured_at: datetime
    evidence_excerpt: str


class CanonicalFact(BaseModel):
    fact_id: str
    key: str
    namespace: Literal[
        "pricing",
        "counts",
        "permissions",
        "services",
        "architecture",
        "timeline",
        "compliance",
        "naming",
    ]
    subject: str
    attribute: str
    value: Any
    units: str | None = None
    confidence: Literal["founder_confirmed", "documented", "inferred"]
    status: Literal["active", "superseded", "conflicted", "deprecated"]
    source: FactSource
    supersedes: list[str] = Field(default_factory=list)
    superseded_by: str | None = None
    downstream_bind_phases: list[PhaseKey] = Field(default_factory=list)


class FactConflict(BaseModel):
    key: str
    active_fact_ids: list[str]
    conflicting_values: list[str]
    resolution_required_by: PhaseKey


class StateRegistry(BaseModel):
    run_id: str
    platform_name: str
    active_index: dict[str, str]
    facts: dict[str, CanonicalFact]
    conflicts: list[FactConflict] = Field(default_factory=list)
```

**2.2.3 Patch/Correction Types**
```python
class FindingRef(BaseModel):
    finding_id: str
    layer: Literal["L1", "L2", "L3", "L4"]


class CorrectionPatch(BaseModel):
    patch_id: str
    finding_refs: list[FindingRef]
    target_section_ids: list[str]
    operation: Literal["replace_block", "append_block", "regenerate_section", "set_fact"]
    precondition_hash: str
    content_markdown: str | None = None
    fact_updates: list[CanonicalFact] = Field(default_factory=list)


class AppliedPatch(BaseModel):
    patch_id: str
    status: Literal["applied", "skipped_precondition", "skipped_conflict"]
    changed_section_ids: list[str]
    old_hashes: dict[str, str]
    new_hashes: dict[str, str]


class CorrectionResult(BaseModel):
    phase: PhaseKey
    strategy: Literal["structural", "must_fix", "reengagement"]
    patches: list[AppliedPatch]
    changed_section_ids: list[str]
    updated_fact_ids: list[str]
```

**2.2.4 Review Types**
```python
class ReviewFinding(BaseModel):
    finding_id: str
    layer: Literal["L1", "L2", "L3", "L4"]
    category: Literal["must_fix", "should_improve", "consider"]
    phase: PhaseKey
    artifact_id: str
    section_id: str
    fact_keys: list[str] = Field(default_factory=list)
    issue: str
    evidence: str
    recommendation: str
    source_persona: str | None = None


class ReviewResult(BaseModel):
    layer: Literal["L1", "L2", "L3", "L4"]
    reviewed_section_ids: list[str]
    findings: list[ReviewFinding]
    elapsed_seconds: float


class FindingMergeResult(BaseModel):
    canonical_findings: list[ReviewFinding]
    duplicate_map: dict[str, list[str]]
    grouped_by_section: dict[str, list[str]]
    grouped_by_fact_key: dict[str, list[str]]


class ReengagementTopic(BaseModel):
    topic_id: str
    source_finding_ids: list[str]
    section_id: str
    question: str
    question_style: Literal["open", "clarify", "confirm"]
    expected_fact_keys: list[str] = Field(default_factory=list)


class ReengagementPlan(BaseModel):
    phase: PhaseKey
    topics: list[ReengagementTopic]
    deferred_finding_ids: list[str] = Field(default_factory=list)


class ReviewPipelineResult(BaseModel):
    l1: ReviewResult
    l2: ReviewResult
    l3: ReviewResult
    l4: ReviewResult
    merge: FindingMergeResult
    reengagement: ReengagementPlan | None = None
```

### 2.3 Synthesis Redesign
- Template parsing: every template is parsed once into a `PhaseTemplateSpec`. For Phase 1, `conversation` and `synthesis` templates remain separate files. For Phases 2-10, the parser splits on `<!-- SYNTHESIS_START -->`, strips conversation-only instructions from synthesis mode, extracts required headings/fields/appendices, and assigns each section a stable `section_id`.
- Generation flow: use bounded section groups, not full-document generation. The service first produces a section plan, then generates 1-3 related sections per batch, then validates that batch before moving on. Suggested grouping:
  `intro/context` batch,
  `core content` batches,
  `appendices/manifests` batch.
- Validation gates: `validate_deliverable()` is replaced by two gates.
  `validate_batch()` runs after each synthesis batch and blocks promotion of that batch if required elements or referenced fact keys are missing.
  `validate_document()` runs after assembly and before expert review. L1 is no longer the first place structural defects are discovered.
- State registry interaction: each batch receives only the active facts relevant to its `depends_on_fact_keys`. After a batch passes validation, fact extraction writes newly asserted facts into the registry and supersedes older values before the next batch runs.
- **Trade-off noted:** chosen approach is bounded group generation.
  State what you chose, what you rejected, and why.
  Chosen: 1-3 section batches with immediate validation.
  Rejected: whole-document synthesis because it is the source of large review deltas and correction collateral damage.
  Rejected: pure single-section synthesis because it over-fragments long narrative sections and increases glue-code complexity.

### 2.4 Review Pipeline Redesign
- Execution model: hybrid.
  L1 remains sequential and mechanical.
  L2, L3, and L4 run in parallel, but only after the document has passed section and document validation.
  Corrections are then applied only to affected sections, followed by targeted revalidation and targeted re-review of impacted sections, not a full rerun by default.
- Finding merge and deduplication logic: normalize findings by `(section_id, fact_keys, issue_stem)`. If multiple layers report the same underlying issue, keep one canonical finding with provenance from all source layers. Layer precedence for severity is L1 structural > L2/L3 cross-phase/technical > L4 comprehension.
- Correction application method: hybrid.
  Use deterministic block replacement/appends for local changes where the section identity is stable.
  Use section regeneration only when the change is semantic, cross-paragraph, or exceeds a configured diff threshold.
  Never use raw `search_text` matching against whole-document prose.
- Topic ID preservation through founder re-engagement: each `ReengagementTopic` carries `topic_id`, `source_finding_ids`, `section_id`, and expected fact keys. Founder answers are persisted keyed by `topic_id`; updates target only the sections named by those topics.
- Revalidation trigger logic: changed sections always get L1 revalidation. If a patch changes fact keys used by other sections, the dependency graph marks those sections as impacted and reruns only the relevant reviewer layers for those sections. Full-document rereview is reserved for graph-wide conflicts or manifest drift.
- **Trade-off noted:** chosen approach is hybrid parallel review plus targeted rereview.
  State what you chose, what you rejected, and why.
  Chosen: L2/L3/L4 parallel on a stable draft, then targeted correction/rereview on changed sections.
  Rejected: fully sequential corrected-per-layer flow because evidence shows it becomes authorial and too slow.
  Rejected: one-shot parallel review plus no rereview because changed sections need a structural and provenance check before publication.

### 2.5 Configuration & Model Support
```python
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ModelTier(str, Enum):
    HAIKU_45 = "haiku_4_5"
    SONNET_45 = "sonnet_4_5"
    SONNET_46_STD = "sonnet_4_6_std"
    SONNET_46_HIGH = "sonnet_4_6_high"


class ModelProfile(BaseModel):
    model_id: str
    context_window_tokens: int
    output_ceiling_tokens: int
    supports_thinking: bool
    default_thinking: Literal["disabled", "standard", "high"]


class RoleExecutionPolicy(BaseModel):
    input_budget_tokens: int
    output_budget_tokens: int
    thinking: Literal["disabled", "standard", "high"]
    max_parallel_jobs: int = 1


class TierBundle(BaseModel):
    model: ModelProfile
    role_policies: dict[RoleName, RoleExecutionPolicy]


class RuntimePolicy(BaseModel):
    active_tier: ModelTier
    hard_cost_ceiling_usd: Decimal
    publish_after_each_phase: bool = True


class ResearchProviderConfig(BaseModel):
    anthropic_web_search: bool = True
    perplexity_enabled: bool
    grok_enabled: bool


class AppConfig(BaseModel):
    runtime: RuntimePolicy
    tiers: dict[ModelTier, TierBundle]
    research: ResearchProviderConfig
```

- How 4 model tiers are defined:
  `haiku_4_5` -> `claude-haiku-4-5-20251001`
  `sonnet_4_5` -> `claude-sonnet-4-5-20241022`
  `sonnet_4_6_std` -> `claude-sonnet-4-6` with standard thinking
  `sonnet_4_6_high` -> `claude-sonnet-4-6` with high thinking
- How a single config change switches all roles: set `runtime.active_tier`. Every role policy is then resolved from `tiers[active_tier].role_policies[role]`. No per-role hardcoded model constants remain in code.
- Token budget table per role per model tier:

| Role | Haiku 4.5 | Sonnet 4.5 | Sonnet 4.6 std | Sonnet 4.6 high |
|---|---|---|---|---|
| Guide conversation | `110k / 12k / disabled` | `180k / 16k / standard` | `220k / 18k / standard` | `220k / 20k / high` |
| Founder simulation | `24k / 4k / disabled` | `32k / 4k / disabled` | `32k / 4k / disabled` | `32k / 4k / disabled` |
| Synthesis batch | `120k / 16k / disabled` | `180k / 20k / standard` | `220k / 24k / standard` | `220k / 24k / high` |
| L1 compliance | `80k / 4k / disabled` | `120k / 6k / disabled` | `140k / 6k / disabled` | `140k / 6k / disabled` |
| L2/L3 expert review | `100k / 12k / disabled` | `160k / 18k / standard` | `200k / 20k / standard` | `200k / 20k / high` |
| L4 comprehension review | `90k / 8k / disabled` | `120k / 10k / standard` | `140k / 12k / standard` | `140k / 12k / high` |
| Correction / targeted update | `90k / 12k / disabled` | `140k / 18k / standard` | `180k / 20k / standard` | `180k / 20k / high` |
| Cross-phase audit | `100k / 12k / disabled` and batched by namespace | `180k / 18k / standard` | `220k / 20k / standard` | `220k / 20k / high` |

- Thinking mode toggle logic:
  If `supports_thinking` is false, thinking is forced to `disabled` regardless of role request.
  If `active_tier` is `haiku_4_5`, all roles run with thinking disabled.
  If `active_tier` is `sonnet_4_6_high`, roles that request `standard` may still use `standard`; only roles configured for `high` use high reasoning.
- Cost ceiling enforcement mechanism:
  Before dispatch, the orchestrator reserves worst-case cost for the queued mandatory jobs using `estimate_reserved_cost()`.
  Reservations and actual usage are persisted in `run_store.py`, so restarts cannot lose budget state.
  If reserved mandatory work would cross `$200`, the phase does not start.
  Optional work is dropped in this order before hard stop: review notes generation, cross-phase audit, non-blocking refresh research.
  If mandatory work alone exceeds remaining budget, the orchestrator halts with a durable checkpoint.

### 2.6 Migration Order

**Step 1: Extract contracts and runtime settings**
- **Source:** Extract from main.py lines [84-159] / Write fresh
- **Validation:** Unit-test tier resolution, role-policy lookup, and cost reservation math.
- **Dependencies:** None
- **Estimated complexity:** Medium

**Step 2: Build the LLM gateway**
- **Source:** Extract from main.py lines [401-953] and [2016-2407] / Write fresh
- **Validation:** Recorded-response contract tests for streaming parse, retries, tool dispatch, and Haiku thinking disablement.
- **Dependencies:** Step 1
- **Estimated complexity:** Large

**Step 3: Build the template parser**
- **Source:** Write fresh
- **Validation:** Parse all unchanged templates and assert stable `section_id`s, `SYNTHESIS_START` splitting, and required-element extraction.
- **Dependencies:** Step 1
- **Estimated complexity:** Large

**Step 4: Build durable run store and canonical state registry**
- **Source:** Extract from main.py lines [258-385], [1110-1135], [3936-3953], [4073-4075], [4240-4252] / Write fresh
- **Validation:** Restart/resume tests prove budget totals, timing, facts, and artifacts survive process restart without loss.
- **Dependencies:** Step 1
- **Estimated complexity:** Large

**Step 5: Move conversation flow into `phase_service.py`**
- **Source:** Extract from main.py lines [1142-1383] and [1724-1843]
- **Validation:** Replay saved transcripts and verify conversation persistence, founder-memory snapshots, and research result capture.
- **Dependencies:** Steps 2-4
- **Estimated complexity:** Medium

**Step 6: Rewrite synthesis as section-batch generation with validation**
- **Source:** Replace main.py lines [1395-1581] and [2427-2521] / Write fresh
- **Validation:** Phase 1 and Phase 2 dry runs produce section-complete deliverables that pass batch validation before any expert review.
- **Dependencies:** Steps 2-5
- **Estimated complexity:** Large

**Step 7: Rewrite review, correction, and re-engagement on stable section IDs**
- **Source:** Reuse prompt intent from main.py lines [2630-3817] / Write fresh
- **Validation:** Reproduce evidence-heavy cases (Phases 6a, 8, 10) and confirm:
  section-local corrections only,
  no duplicate headings,
  topic IDs preserved end-to-end,
  targeted rereview only on changed sections.
- **Dependencies:** Steps 2-6
- **Estimated complexity:** Very Large

**Step 8: Replace top-level orchestrator**
- **Source:** Extract sequencing intent from main.py lines [3820-4273] / Write fresh
- **Validation:** Full Ocean Golf run, resume-after-failure run, GitHub publish parity, and cross-phase registry audit.
- **Dependencies:** Steps 1-7
- **Estimated complexity:** Large

**Main.py retirement criteria:** The old file can be deleted only when the new orchestrator completes all 12 phase units with unchanged templates/personas, persists cost and timing across resume, publishes after each phase, produces no structural corruption in correction paths, and demonstrates that cross-phase contradictions are represented as registry supersessions rather than late prose-only warnings.

**First end-to-end test possible after:** Step 7

---

## SUMMARY

### Top 3 Highest-Impact Changes
1. Replace prose-only cross-phase memory with a canonical fact registry that supports supersession, conflict detection, and section-scoped context loading.
2. Replace whole-document synthesis with section-batch generation plus immediate validation so L1 stops being the first structural gate.
3. Replace string-based correction/re-engagement with section-ID-based patches and topic-ID-preserving founder updates.

### Estimated Total Migration Complexity
Very Large — the methodology, templates, personas, and external integrations stay fixed, but the execution core must be re-platformed from a prompt-driven monolith into a typed, stateful pipeline with durable resume and section-local correction semantics.

### Risks and Open Questions
- The brief says the methodology produces 23 deliverables, while several repository artifacts and evidence files refer to a 20-deliverable package; that artifact inventory needs one authoritative count before implementation.
- The exact production model identifiers for “Sonnet 4.6 standard” and “Sonnet 4.6 high reasoning” should be confirmed before wiring configuration.
- Canonical fact extraction from markdown must be precise enough to distinguish intentional refinement from contradiction; that extractor will need targeted tests on pricing, counts, permissions, and service inventory.
- Some founder-memory and sample deliverable artifacts already contain contradictory history; migration should treat those as evidence to normalize, not as trusted source of truth.
