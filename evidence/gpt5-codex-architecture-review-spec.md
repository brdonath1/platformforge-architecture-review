# PlatformForge Orchestrator — Architecture Review & Re-Architecture Specification

**Reviewing Model:** GPT-5 Codex
**Date:** March 3, 2026
**Files Analyzed:** `ANALYSIS-BRIEF.md`; `code/main.py`; `code/CLAUDE.md`; `architecture/d188-review-architecture.md`; `architecture/module-architecture.md`; `templates/phase-1-synthesis.md`; `templates/phase-2-users.md`; `personas/review-config.md`; `personas/l2-domain-experts.md`; `personas/l3-downstream-consumers.md`; `personas/l4-founder-comprehension.md`; all 12 files in `evidence/review-pipelines/`; all 12 files in `evidence/critic-reports/`; all 36 files in `evidence/expert-reviews/`; all 12 files in `evidence/interview-briefs/`; `evidence/metrics/cross-phase-consistency.json`; `evidence/metrics/cost-report.json`; all 12 files in `evidence/metrics/phase-*-metrics.json`; `evidence/metrics/timing-waterfall.json`; all 4 files in `evidence/corrections-sample/`.

---

## PHASE 1: ARCHITECTURE REVIEW

### 1.1 System Comprehension Summary
The orchestrator is a phase runner wrapped around one large global state file. `main()` ([code/main.py](./code/main.py) lines 4085-4273) loads prompts, personas, and environment configuration, then iterates through `PHASE_ORDER`. For each phase, `run_phase()` (3820-3958) loads the template, concatenates all prior deliverables via `load_prior_deliverables()` (2528-2612), runs a dual-model conversation through `run_conversation()` (1142-1383), synthesizes a deliverable through `run_synthesis()` (1395-1564), runs the D-188 review pipeline through `run_review_pipeline()` (3587-3817), writes metrics, updates founder memory, and pushes the `output/` tree to GitHub with `git_push_output()` (265-355).

The conversation layer is prompt-heavy and text-centric. `run_conversation()` builds guide and founder system prompts from the master prompt, phase template, founder persona, prior deliverables, and generated founder memory (1724-1843). Live research is handled through `call_guide_with_research()` (2305-2407), which mixes Anthropic `web_search`, Perplexity, and Grok results into the transcript as raw text. The API layer is concentrated in `_execute_stream()` (401-605), `call_api()` (608-790), and `serialize_for_replay()` (878-955), which together manage streaming, retries, tool continuation, thinking blocks, and model-specific beta-header behavior.

The synthesis and review layers both operate on whole-document blobs rather than typed section or fact objects. `run_synthesis()` injects the raw conversation transcript, research snippets, full prior deliverables, and full synthesis template into one prompt and asks for the entire deliverable at once. The review pipeline starts with L1 template compliance, then parallel L2/L3/L4 full-document reviews, then full-document correction synthesis, then founder re-engagement, then a full-document targeted update. Cross-phase state is not represented canonically; instead, the system relies on prior markdown deliverables for in-run context and only runs `run_cross_phase_consistency_check()` (3970-4078) after the run. Publishing is also embedded in the runtime path, so artifact generation, validation, GitHub writes, and cost tracking all share the same execution spine.

### 1.2 Architectural Problems
**Problem 1: Whole-document strings are the system’s primary interface**
- **Location:** `run_synthesis()` (1395-1564), `run_layer_review()` (2775-2909), `run_correction_synthesis()` (3098-3224), `run_targeted_update()` (3467-3555)
- **What happens:** Each major stage passes full transcripts, full templates, full prior deliverables, and full deliverables as raw strings into the next LLM call. Section identity, fact identity, and dependency structure are not materialized as program objects.
- **Why it is a problem:** The architecture has no stable unit smaller than “the whole document,” so every stage must rediscover structure from scratch. That makes correction churn, over-generation, and contextual drift normal behavior rather than edge cases.
- **Evidence:** Review pipeline summaries show `deliverable_delta_chars` totaling 829,304 across 12 phases; the largest deltas are Phase 8 `+148,880`, Phase 6a `+140,370`, and Phase 5 `+106,221` (`evidence/review-pipelines/`). Final deliverables still average 154,011 chars (`evidence/metrics/phase-*-metrics.json`), which means the review pipeline is rewriting a large fraction of already-large artifacts.

**Problem 2: Cross-phase consistency is handled as post-hoc document memory, not canonical state**
- **Location:** `load_prior_deliverables()` (2528-2612), `run_cross_phase_consistency_check()` (3970-4078), `main()` (4231-4238)
- **What happens:** Prior phases are loaded as concatenated markdown, sometimes truncated for Haiku, and used as soft context. A consistency audit runs only after the run and is explicitly non-blocking.
- **Why it is a problem:** Narrative documents are being used as the source of truth for mutable facts like pricing, counts, permissions, and service inventories. Because there is no canonical registry with supersession rules, later phase changes do not propagate reliably and earlier artifacts remain stale.
- **Evidence:** `evidence/metrics/cross-phase-consistency.json` reports a consistency score of 72 with 14 issues: 5 naming conflicts, 3 technology contradictions, and 6 other inconsistencies. The examples are exactly the kinds of facts that need canonical ownership: course/property counts, Stripe processing rate, service-fee tiers, referral-partner permissions, WCAG target level, RLS syntax, and service counts.

**Problem 3: Structural validation is late, probabilistic, and partially orphaned**
- **Location:** `validate_deliverable()` (2427-2521), `run_phase()` (3882-3909), `run_review_pipeline()` (3616-3653)
- **What happens:** A structural validator exists, but it is never called. Structural completeness is first enforced inside the review pipeline through L1, which is itself another full-template LLM call rather than a deterministic parser/checker.
- **Why it is a problem:** The system allows synthesis to produce structurally invalid drafts, then spends review budget backfilling objective template requirements. Because L1 is still interpretive rather than deterministic, mechanical checks are more expensive and less reliable than they need to be.
- **Evidence:** `rg` shows `validate_deliverable()` is defined once and never called. Review-pipeline summaries show 158 initial L1 misses across 12 phases, including Phase 6a `65`, Phase 5 `30`, Phase 6c `27`, Phase 8 `21`, and Phase 1 `10` (`evidence/review-pipelines/`). This is objective missing-structure work reaching the review layer.

**Problem 4: Review, correction, and founder re-engagement lose semantic provenance**
- **Location:** `apply_patches()` (2974-3095), `run_correction_synthesis()` (3098-3224), `build_interview_brief()` (3227-3310), `run_founder_reengagement()` (3457-3463), `run_targeted_update()` (3467-3555)
- **What happens:** Corrections are anchored by fuzzy text search and markdown headings; skipped or ambiguous patches are tolerated. Interview briefs create stable topic IDs, but founder responses are collapsed to `topic_id="combined"` before targeted update.
- **Why it is a problem:** The architecture cannot reliably answer “which finding changed which section because of which founder answer.” That makes precise revalidation, bounded edits, and downstream traceability impossible.
- **Evidence:** All 12 interview briefs contain exactly 8 topics (`evidence/interview-briefs/`), while expert reviews show should-improve totals between 16 and 39 per phase (`evidence/expert-reviews/`). Phase 8 alone had 25 should-improve findings but only 8 interview topics. The correction samples are also very large for a “surgical” patch system: 25,340 chars, 69,325 chars, 93,175 chars, and 43,241 chars (`evidence/corrections-sample/`).

**Problem 5: The review pipeline is doing authorship work, not bounded QA**
- **Location:** `run_review_pipeline()` (3587-3817), `run_layer_review()` (2775-2909), `run_founder_reengagement()` (3320-3464)
- **What happens:** L2/L3/L4 generate very large finding sets, the pipeline triggers large correction passes and founder re-engagement in every phase, and the re-engagement cap silently defers excess should-improve items.
- **Why it is a problem:** A review architecture should expose defects in a bounded draft; here it is acting as a second-stage content generation system. That makes runtime, cost, and output quality depend on reviewer verbosity rather than strong upstream contracts.
- **Evidence:** The expert-review corpus contains 701 findings total: 312 must-fix, 287 should-improve, 102 consider (`evidence/expert-reviews/`). Review time averages 979 seconds per phase (`evidence/review-pipelines/`). In the phase metrics, review dominates synthesis in high-churn phases: Phase 1 `1312s review vs 330s synthesis`, Phase 5 `1432s vs 248s`, Phase 6a `1512s vs 140s` (`evidence/metrics/phase-*-metrics.json`). After all of that, the Phase 8 critic report still records 1 critical issue, 4 contradictions, and 6 warnings (`evidence/critic-reports/phase-8-critic-report.json`).

**Problem 6: Runtime policy, I/O side effects, and orchestration are fused into one mutable control plane**
- **Location:** global config/constants (84-181), API stack (401-955), publishing (`git_push_output()` 265-355), `run_phase()` (3820-3958), `main()` (4186-4258)
- **What happens:** Model tier selection, token budgets, retry policy, context management, founder-memory behavior, template fetching, cost tracking, GitHub publishing, and phase orchestration all live in one file and share process-wide globals.
- **Why it is a problem:** Every operational change becomes an architectural edit. The system cannot independently test model policy, document generation, review flow, or publishing without booting the whole runtime shape.
- **Evidence:** `code/CLAUDE.md` documents repeated in-place architectural rewrites to the same file for D-188, D-194, and D-185 because runtime behavior and architecture are inseparable. It also records the prior state where Phase 1 review took 45 minutes out of a 54.5-minute phase and projected the full run to 12+ hours. Current code still retains model-specific branching in `call_api()`, `build_guide_tools()`, and `load_prior_deliverables()`.

### 1.3 Root Cause Analysis
**Root Cause A: No typed intermediate representation for sections, facts, or findings**
- **Problems it causes:** 1, 3, 4, 5
- **Architectural mechanism:** The system treats prompts, transcripts, templates, findings, and deliverables as opaque text blobs. Because there is no typed section graph or fact graph, synthesis, compliance, expert review, correction, and targeted update all operate by re-reading and re-inferring structure from long text.
- **Evidence chain:** Full-document synthesis in `run_synthesis()` feeds full-document reviews in `run_layer_review()`, which feed text-anchor patching in `run_correction_synthesis()` and `apply_patches()`. The result is 829,304 review-added chars plus 158 initial L1 misses and 701 expert findings.

**Root Cause B: Narrative deliverables are being used as mutable system state**
- **Problems it causes:** 2, 4, 5
- **Architectural mechanism:** Facts live inside markdown outputs instead of a registry with ownership and supersession rules. Later phases can contradict or refine earlier phases, but there is no mechanism to atomically update the canonical value and propagate that change to dependent artifacts.
- **Evidence chain:** `load_prior_deliverables()` concatenates older deliverables and truncates them for Haiku; `run_cross_phase_consistency_check()` audits only after the fact and does not block. The observed failures are registry-shaped failures: pricing, permissions, counts, accessibility level, RLS syntax, and service inventory drift in `cross-phase-consistency.json`.

**Root Cause C: Mechanical checks and subjective review are both delegated to LLMs**
- **Problems it causes:** 3, 5, 6
- **Architectural mechanism:** L1 compliance, expert review, correction generation, founder re-engagement, and targeted update are all LLM calls. Even tasks that should be deterministic, like section presence and manifest structure, are implemented as prompt-based interpretation.
- **Evidence chain:** `validate_deliverable()` exists but is unused, while L1 is still an LLM reviewer. Review pipeline summaries show large objective-missing counts, and phase metrics show review dominating synthesis in the most unstable phases.

**Root Cause D: The monolith has no explicit control-plane/data-plane boundary**
- **Problems it causes:** 1, 2, 6
- **Architectural mechanism:** Configuration, model policy, external I/O, state loading, generation, review, and publishing are all direct function calls in the same file with shared globals. There is no module contract forcing boundaries between data preparation, LLM execution, deterministic validation, and artifact publication.
- **Evidence chain:** The same file owns retry behavior, model-tier compatibility, filesystem layout, GitHub writes, and phase flow. `code/CLAUDE.md` reads as a change log of architectural fixes landing as tactical edits inside one control plane.

### 1.4 Fragility Map (Top 10)
**Rank 1: `run_review_pipeline` (3587-3817)**
- **Why it is fragile:** It coordinates the highest number of implicit contracts: L1 findings, parallel reviewer outputs, correction synthesis, re-engagement, final L1, metrics, and note generation.
- **Blast radius:** Breakage here affects quality control, timing metrics, review notes, founder follow-up, and final deliverable persistence.
- **Recommended fix:** Replace it with a phase review coordinator operating on typed `ReviewFinding`, `SectionRevision`, and `InterviewBrief` objects.

**Rank 2: `run_correction_synthesis` + `apply_patches` (2974-3224)**
- **Why it is fragile:** It depends on exact or fuzzy string matches inside large markdown documents and silently tolerates skipped or ambiguous patches.
- **Blast radius:** A small formatting change can cause must-fix findings to remain unresolved or apply to the wrong section.
- **Recommended fix:** Move to section-scoped revisions with checksum guards and AST-level document assembly.

**Rank 3: `load_prior_deliverables` (2528-2612)**
- **Why it is fragile:** It multiplexes context strategy, recency policy, model-tier budgeting, and cross-phase memory in one concatenation function.
- **Blast radius:** Any change in model tier or document size changes what downstream phases can “remember,” which changes synthesis and review behavior.
- **Recommended fix:** Replace prior-deliverable loading with a registry query API plus section-level dependency loads.

**Rank 4: `run_targeted_update` (3467-3555)**
- **Why it is fragile:** It takes combined founder responses and asks for a whole updated document with weak guarantees about which sections changed.
- **Blast radius:** Founder clarification can accidentally rewrite unrelated content or undo prior corrections.
- **Recommended fix:** Apply founder responses only to explicitly mapped `section_id`s and rerender the final document from section objects.

**Rank 5: `_execute_stream` / `call_api` / `serialize_for_replay` (401-955)**
- **Why it is fragile:** Streaming parsing, thinking-block replay, beta headers, retry logic, and metrics are tightly coupled and model-sensitive.
- **Blast radius:** API compatibility failures affect every Guide, Founder, Synthesis, Review, and Correction call.
- **Recommended fix:** Isolate a single `model_gateway` module with typed request/response objects and per-tier policy resolution.

**Rank 6: `run_synthesis` (1395-1564)**
- **Why it is fragile:** It relies on one high-context generation call to produce a fully compliant deliverable from raw transcript text.
- **Blast radius:** Any synthesis miss propagates directly into L1, L2, L3, L4, correction, and cross-phase drift.
- **Recommended fix:** Generate section-by-section from a parsed `PhaseSpec` and registry-backed fact set.

**Rank 7: `run_layer_review` + `_parse_review_findings` (2775-2937)**
- **Why it is fragile:** Reviewer quality depends on prompt interpretation, and malformed XML quietly degrades into incomplete finding sets.
- **Blast radius:** Bad reviewer output corrupts correction planning, re-engagement topics, and review metrics.
- **Recommended fix:** Require structured JSON findings tied to `section_id` and `fact_id`, validated before merge.

**Rank 8: `run_cross_phase_consistency_check` (3970-4078)**
- **Why it is fragile:** It is a late, full-corpus LLM audit with no blocking authority and no canonical registry to reconcile against.
- **Blast radius:** Contradictions are detected only after downstream artifacts are already published.
- **Recommended fix:** Run registry-based consistency checks incrementally at each phase boundary and block publication on critical drift.

**Rank 9: `run_phase` (3820-3958)**
- **Why it is fragile:** It mixes template loading, conversation, synthesis, review, persistence, founder-memory updates, metrics, and publishing in one flow.
- **Blast radius:** Any failure mid-phase leaves partially updated artifacts and complicates resume semantics.
- **Recommended fix:** Convert `run_phase` into a thin coordinator over modular services with explicit checkpoints and resumable state.

**Rank 10: Global config/constants block (84-181)**
- **Why it is fragile:** Model tiers, token ceilings, retries, phase maps, cost ceiling, and context-management rules are scattered in process-wide globals.
- **Blast radius:** Changing one tier or budget can unintentionally alter unrelated roles and context policies.
- **Recommended fix:** Replace globals with a single typed config object that resolves per-role settings from an active model tier.

### 1.5 Cross-Phase Consistency Analysis
The current consistency score is 72 with 14 issues found in `evidence/metrics/cross-phase-consistency.json`. The issue mix is 5 naming conflicts, 3 technology contradictions, and 6 other inconsistencies. That is not random drift; it is concentrated in high-value, implementation-shaping facts.

The drift categories are:
- Pricing and unit economics drift: Stripe effective rate changes from roughly `4.5-5%` to `5.5-6.0%` to `5.6%`; service-fee pricing changes from `"$75-$125"` to `"$150/$125/$100"`; Day Zero infrastructure cost changes from `$0/mo` to `$68.50/mo`.
- Counts and inventory drift: course count `14 -> 15`, property count `11 -> 12`, service count `8 -> 9`.
- Permission drift: Phase 2 grants Team Members edit access to referral partners while Phases 5 and 7 restrict create actions to Operator/Senior Concierge.
- Standards and policy drift: WCAG target changes from 2.1 AA to 2.2 AA; RLS syntax changes from shorthand to app-metadata paths.
- Cross-reference drift: document manifests and labels point to stale or wrong upstream deliverables.

The architectural cause is the same across categories: facts are authored inside prose, later phases refine them locally, and no registry enforces authoritative ownership or supersession. `load_prior_deliverables()` only replays old text; it does not tell the system which prior fact has been superseded. `run_cross_phase_consistency_check()` only reports contradictions after all phases finish, and it does not write back canonical replacements.

The most affected phases are:
- Phase 1, because strategic pricing and business-model assumptions become stale once operational realities are known.
- Phases 2, 4, and 5, because permissions, schema syntax, and technical contracts get refined later without back-propagating to the original source documents.
- Phases 7, 8, 9, and 10, because they operationalize earlier decisions and expose contradictions in counts, service inventories, pricing, and compliance status.

Late-phase operational documents are especially destabilizing because they surface real-world costs and process requirements that earlier phases only estimated. Without a state registry, those refinements remain local edits instead of becoming canonical facts.

### 1.6 Review Pipeline Effectiveness
L1 initial miss counts per phase are: Phase 1 `10`, Phase 2 `0`, Phase 3 `0`, Phase 4 `0`, Phase 5 `30`, Phase 6a `65`, Phase 6b `0`, Phase 6c `27`, Phase 7 `0`, Phase 8 `21`, Phase 9 `5`, Phase 10 `0` (`evidence/review-pipelines/`). The aggregate is 158 missing structural items before deeper review even begins. That means the pipeline is still absorbing compliance work that should have been prevented during synthesis.

Correction deltas per phase are: Phase 1 `+26,856`, Phase 2 `+53,687`, Phase 3 `+36,508`, Phase 4 `+55,715`, Phase 5 `+106,221`, Phase 6a `+140,370`, Phase 6b `+49,783`, Phase 6c `+83,526`, Phase 7 `+34,079`, Phase 8 `+148,880`, Phase 9 `+61,882`, Phase 10 `+31,797`. This is authorship-scale change, not bounded QA. Parallelizing L2/L3/L4 improved wall-clock review for the reviewer calls themselves, but the expensive work moved to correction synthesis, re-engagement, and final L1, so the architecture still depends on large second-pass rewrites.

Expert review finding quality is mixed but genuinely informative in places. Strong examples include Phase 8 L3 findings that catch placeholder text, sequencing contradictions, and “implementation-ready” labels on artifacts still blocked by founder or legal decisions (`evidence/expert-reviews/phase-8-l3-review.json`). Phase 1 L4 findings also correctly call out conflicting TAM ranges and ambiguous operational triggers (`evidence/expert-reviews/phase-1-l4-review.json`). The weaker side is visible in Phase 6a L2, where many must-fix findings are really “prove you executed live research with timestamps and screenshots” rather than “this design foundation fails downstream consumption” (`evidence/expert-reviews/phase-6a-l2-review.json`). That indicates the reviewers are partly auditing process ceremony instead of just document utility.

Re-engagement effectiveness is capped by architecture, not by founder signal. Every interview brief contains exactly 8 topics, but every phase had more than 8 should-improve findings; the totals range from 16 to 39 per phase (`evidence/interview-briefs/`, `evidence/expert-reviews/`). Then `run_founder_reengagement()` discards topic IDs and returns only `topic_id="combined"`, so the targeted update step cannot preserve per-topic provenance. This means the pipeline collects more nuanced feedback than it can actually carry through to a traceable correction path.

Net assessment: the review pipeline does catch real defects, and the move to parallel L2/L3/L4 was directionally correct for latency. But the pipeline is not achieving its design intent efficiently. It is compensating for weak synthesis contracts, performing large-scale authorship, and still leaving measurable cross-phase contradictions behind.

---

## PHASE 2: RE-ARCHITECTURE SPECIFICATION

### 2.1 Module Map
**Module: `config.py`**
- **Responsibility:** Load one typed run configuration and resolve per-role model/tokens/cost policy from a single active tier.
- **Imports from:** `contracts.py`
- **Public API:**
  ```python
  def load_run_config(config_path: str | None = None) -> RunConfig: ...
  def resolve_role_settings(config: RunConfig, role: LlmRole) -> RoleExecutionConfig: ...
  def assert_cost_headroom(config: RunConfig, cost_state: CostState, role: LlmRole) -> None: ...
  ```

**Module: `contracts.py`**
- **Responsibility:** Define the shared typed contracts used between every module.
- **Imports from:** []
- **Public API:**
  ```python
  def compute_checksum(markdown: str) -> str: ...
  def stable_finding_fingerprint(finding: ReviewFinding) -> str: ...
  def build_fact_id(namespace: str, subject: str, attribute: str) -> str: ...
  ```

**Module: `phase_catalog.py`**
- **Responsibility:** Hold immutable phase order, template mapping, deliverable identities, and fact-ownership rules.
- **Imports from:** `contracts.py`
- **Public API:**
  ```python
  def ordered_phases() -> list[PhaseKey]: ...
  def get_phase_definition(phase: PhaseKey) -> PhaseDefinition: ...
  def get_fact_authority_rules() -> list[FactAuthorityRule]: ...
  ```

**Module: `artifact_store.py`**
- **Responsibility:** Load templates/personas/artifacts and persist phase outputs, metrics, and snapshots.
- **Imports from:** `contracts.py`, `phase_catalog.py`
- **Public API:**
  ```python
  def load_phase_bundle(phase: PhaseKey) -> PhaseInputBundle: ...
  def load_prior_artifacts(before_phase: PhaseKey) -> PriorArtifactBundle: ...
  def save_phase_result(result: PhaseExecutionResult) -> SavedPhaseArtifacts: ...
  ```

**Module: `template_parser.py`**
- **Responsibility:** Parse unchanged markdown templates into section, requirement, manifest, and dependency checklists.
- **Imports from:** `contracts.py`, `phase_catalog.py`
- **Public API:**
  ```python
  def parse_phase_spec(phase: PhaseKey, raw_template: str) -> PhaseSpec: ...
  def extract_required_manifest_fields(phase_spec: PhaseSpec) -> list[str]: ...
  def build_section_order(phase_spec: PhaseSpec) -> list[str]: ...
  ```

**Module: `model_gateway.py`**
- **Responsibility:** Encapsulate Anthropic Messages API calls, retry policy, streaming, response validation, and usage accounting.
- **Imports from:** `config.py`, `contracts.py`
- **Public API:**
  ```python
  def complete_text(request: CompletionRequest) -> CompletionResponse: ...
  def complete_json(request: StructuredCompletionRequest) -> StructuredCompletionResponse: ...
  def complete_xml(request: StructuredCompletionRequest) -> CompletionResponse: ...
  ```

**Module: `research_gateway.py`**
- **Responsibility:** Provide a unified research interface over Anthropic web search, Perplexity, and Grok with freshness metadata.
- **Imports from:** `config.py`, `contracts.py`, `model_gateway.py`
- **Public API:**
  ```python
  def run_research_plan(plan: ResearchPlan) -> list[ResearchFinding]: ...
  def refresh_stale_facts(registry: CrossPhaseRegistry, phase: PhaseKey) -> list[ResearchFinding]: ...
  def summarize_research_findings(findings: list[ResearchFinding]) -> str: ...
  ```

**Module: `state_registry.py`**
- **Responsibility:** Maintain canonical cross-phase facts, supersession history, and founder-memory projections.
- **Imports from:** `contracts.py`, `phase_catalog.py`
- **Public API:**
  ```python
  def bootstrap_registry(prior_bundle: PriorArtifactBundle) -> CrossPhaseRegistry: ...
  def commit_phase_snapshot(registry: CrossPhaseRegistry, snapshot: PhaseStateSnapshot) -> CrossPhaseRegistry: ...
  def materialize_founder_memory(registry: CrossPhaseRegistry, phase: PhaseKey) -> FounderMemory: ...
  ```

**Module: `conversation_runner.py`**
- **Responsibility:** Run the guide/founder conversation, attach research evidence, and emit transcript plus fact candidates.
- **Imports from:** `contracts.py`, `model_gateway.py`, `research_gateway.py`
- **Public API:**
  ```python
  def run_conversation(request: ConversationRequest) -> ConversationResult: ...
  def extract_fact_candidates(result: ConversationResult, phase_spec: PhaseSpec) -> list[FactRecord]: ...
  def detect_completion(result: ConversationResult, phase_spec: PhaseSpec) -> CompletionStatus: ...
  ```

**Module: `document_engine.py`**
- **Responsibility:** Plan section generation, generate bounded section drafts, run deterministic L1 validation, and assemble the final deliverable.
- **Imports from:** `contracts.py`, `model_gateway.py`, `state_registry.py`
- **Public API:**
  ```python
  def plan_sections(phase_spec: PhaseSpec, transcript: list[ConversationTurn], registry: CrossPhaseRegistry) -> SectionPlan: ...
  def generate_sections(request: SectionGenerationRequest) -> list[SectionDraft]: ...
  def validate_structure(document: DeliverableDocument, phase_spec: PhaseSpec) -> ComplianceResult: ...
  def apply_section_revisions(document: DeliverableDocument, revisions: list[SectionRevision]) -> DeliverableDocument: ...
  ```

**Module: `review_orchestrator.py`**
- **Responsibility:** Run L2/L3/L4 reviews in parallel on section-aware inputs, merge/deduplicate findings, and create re-engagement briefs.
- **Imports from:** `contracts.py`, `model_gateway.py`, `state_registry.py`
- **Public API:**
  ```python
  def run_expert_reviews(request: ReviewRequest) -> ReviewBatchResult: ...
  def merge_findings(batch: ReviewBatchResult) -> MergedFindingSet: ...
  def build_interview_brief(findings: MergedFindingSet, max_topics: int) -> InterviewBrief | None: ...
  ```

**Module: `consistency_auditor.py`**
- **Responsibility:** Enforce registry-based and document-based cross-phase consistency checks before publication.
- **Imports from:** `contracts.py`, `phase_catalog.py`, `state_registry.py`
- **Public API:**
  ```python
  def audit_registry(registry: CrossPhaseRegistry) -> ConsistencyReport: ...
  def audit_document(document: DeliverableDocument, registry: CrossPhaseRegistry) -> ConsistencyReport: ...
  def assert_publishable(report: ConsistencyReport) -> None: ...
  ```

**Module: `publisher.py`**
- **Responsibility:** Render review notes, write export artifacts, and publish approved outputs to GitHub.
- **Imports from:** `artifact_store.py`, `contracts.py`
- **Public API:**
  ```python
  def render_review_notes(findings: list[ReviewFinding]) -> str: ...
  def publish_phase(result: PhaseExecutionResult, target: PublishTarget) -> PublishResult: ...
  def publish_run_summary(summary: RunSummary, target: PublishTarget) -> PublishResult: ...
  ```

**Module: `phase_engine.py`**
- **Responsibility:** Execute one phase end-to-end using typed inputs, registry-backed state, section generation, and section-aware review.
- **Imports from:** `conversation_runner.py`, `document_engine.py`, `review_orchestrator.py`
- **Public API:**
  ```python
  def run_phase(context: PhaseExecutionContext) -> PhaseExecutionResult: ...
  def rerun_affected_sections(result: PhaseExecutionResult, section_ids: list[str]) -> PhaseExecutionResult: ...
  def validate_phase_exit(result: PhaseExecutionResult) -> None: ...
  ```

**Module: `workflow.py`**
- **Responsibility:** Orchestrate the full multi-phase run, checkpointing, consistency gating, and resumability.
- **Imports from:** `consistency_auditor.py`, `phase_engine.py`, `publisher.py`
- **Public API:**
  ```python
  def run_workflow(request: WorkflowRequest) -> WorkflowResult: ...
  def resume_workflow(request: WorkflowRequest, start_phase: PhaseKey) -> WorkflowResult: ...
  def collect_run_summary(results: list[PhaseExecutionResult]) -> RunSummary: ...
  ```

**Module: `cli.py`**
- **Responsibility:** Parse CLI arguments and invoke the workflow entry point.
- **Imports from:** `config.py`, `workflow.py`
- **Public API:**
  ```python
  def parse_args(argv: list[str]) -> CliArgs: ...
  def main(argv: list[str] | None = None) -> int: ...
  ```

**Data Flow Diagram:**
```text
cli.py
  -> config.py
  -> workflow.py
       -> artifact_store.py
       -> phase_catalog.py
       -> template_parser.py
       -> state_registry.py
       -> phase_engine.py
            -> conversation_runner.py
                 -> research_gateway.py
                      -> model_gateway.py
            -> document_engine.py
                 -> model_gateway.py
                 -> state_registry.py
            -> review_orchestrator.py
                 -> model_gateway.py
                 -> state_registry.py
       -> consistency_auditor.py
       -> publisher.py
            -> artifact_store.py
```

### 2.2 Data Contracts
**2.2.1 Core Types**
```python
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

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


class LlmRole(str, Enum):
    GUIDE = "guide"
    FOUNDER = "founder"
    SYNTHESIS = "synthesis"
    REVIEW_L2 = "review_l2"
    REVIEW_L3 = "review_l3"
    REVIEW_L4 = "review_l4"
    REENGAGEMENT = "reengagement"
    CONSISTENCY = "consistency"
    MEMORY = "memory"


class ReviewLayer(str, Enum):
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    L4 = "l4"


class FindingCategory(str, Enum):
    MUST_FIX = "must-fix"
    SHOULD_IMPROVE = "should-improve"
    CONSIDER = "consider"


class ModelTier(str, Enum):
    HAIKU_45 = "haiku_4_5"
    SONNET_45 = "sonnet_4_5"
    SONNET_46_STD = "sonnet_4_6_standard"
    SONNET_46_HIGH = "sonnet_4_6_high"


class ThinkingMode(str, Enum):
    OFF = "off"
    STANDARD = "standard"
    HIGH = "high"


class ArtifactRef(BaseModel):
    path: str
    sha256: str
    generated_at: datetime


class ConversationTurn(BaseModel):
    turn_id: str
    phase: PhaseKey
    speaker: Literal["guide", "founder"]
    text: str
    research_refs: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ResearchFinding(BaseModel):
    finding_id: str
    source: Literal["anthropic_web_search", "perplexity", "grok"]
    query: str
    summary: str
    citations: list[str] = Field(default_factory=list)
    observed_at: datetime
    freshness_days: int


class RequirementSpec(BaseModel):
    requirement_id: str
    kind: Literal["section", "subsection", "manifest_field", "cross_reference", "appendix"]
    description: str
    required: bool = True


class SectionSpec(BaseModel):
    section_id: str
    phase: PhaseKey
    heading: str
    ordinal: str
    purpose: str
    output_mode: Literal["narrative", "table", "list", "manifest", "appendix"]
    required_requirements: list[RequirementSpec] = Field(default_factory=list)
    upstream_fact_ids: list[str] = Field(default_factory=list)
    dependent_section_ids: list[str] = Field(default_factory=list)


class PhaseSpec(BaseModel):
    phase: PhaseKey
    template_path: str
    conversation_template_text: str
    synthesis_template_text: str
    sections: list[SectionSpec]
    required_manifest_fields: list[str] = Field(default_factory=list)


class SectionDraft(BaseModel):
    phase: PhaseKey
    section_id: str
    version: int
    markdown: str
    source_turn_ids: list[str] = Field(default_factory=list)
    asserted_fact_ids: list[str] = Field(default_factory=list)
    checksum: str


class DeliverableDocument(BaseModel):
    phase: PhaseKey
    version: int
    title: str
    sections: list[SectionDraft]
    assembled_markdown: str
    review_notes_markdown: str | None = None
    manifest: dict[str, Any]
    checksum: str


class CostState(BaseModel):
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    by_role_cost_usd: dict[LlmRole, float] = Field(default_factory=dict)


class PhaseExecutionResult(BaseModel):
    phase: PhaseKey
    transcript: list[ConversationTurn]
    document: DeliverableDocument
    registry_snapshot_id: str
    review_result_id: str
    metrics: dict[str, Any]
```

**2.2.2 Cross-Phase State Registry Schema**
```python
class FactStatus(str, Enum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    RETIRED = "retired"


class FactSource(BaseModel):
    phase: PhaseKey
    section_id: str | None = None
    turn_ids: list[str] = Field(default_factory=list)
    research_finding_ids: list[str] = Field(default_factory=list)
    reviewer_layers: list[ReviewLayer] = Field(default_factory=list)


class FactRecord(BaseModel):
    fact_id: str
    namespace: str
    subject: str
    attribute: str
    value: Any
    value_type: Literal["string", "int", "decimal", "bool", "json", "list"]
    status: FactStatus
    authoritative_phase: PhaseKey
    effective_version: int
    source: FactSource
    requires_founder_confirmation: bool = False
    supersedes_fact_id: str | None = None
    superseded_by_fact_id: str | None = None


class FactAuthorityRule(BaseModel):
    namespace: str
    owner_phase: PhaseKey
    allowed_superseding_phases: list[PhaseKey]
    merge_strategy: Literal["replace", "append", "versioned"]
    require_founder_confirmation: bool = False


class PhaseStateSnapshot(BaseModel):
    snapshot_id: str
    phase: PhaseKey
    approved_fact_ids: list[str]
    open_fact_ids: list[str]
    changed_fact_ids: list[str]
    document_checksum: str


class CrossPhaseRegistry(BaseModel):
    facts: dict[str, FactRecord]
    authority_rules: list[FactAuthorityRule]
    aliases: dict[str, list[str]] = Field(default_factory=dict)
    snapshots: list[PhaseStateSnapshot] = Field(default_factory=list)

    def current(self, fact_id: str) -> FactRecord | None: ...
    def current_by_namespace(self, namespace: str) -> list[FactRecord]: ...
```

**2.2.3 Patch/Correction Types**
```python
class PatchOperation(str, Enum):
    REPLACE_SECTION = "replace_section"
    APPEND_WITHIN_SECTION = "append_within_section"
    INSERT_SECTION_BEFORE = "insert_section_before"
    INSERT_SECTION_AFTER = "insert_section_after"


class SectionRevision(BaseModel):
    revision_id: str
    phase: PhaseKey
    section_id: str
    operation: PatchOperation
    based_on_checksum: str
    new_markdown: str
    finding_ids: list[str]
    reason: str


class CorrectionPlan(BaseModel):
    phase: PhaseKey
    must_fix_finding_ids: list[str]
    section_revisions: list[SectionRevision]
    fallback_regeneration_sections: list[str] = Field(default_factory=list)


class CorrectionResult(BaseModel):
    phase: PhaseKey
    updated_document: DeliverableDocument
    applied_revision_ids: list[str]
    skipped_revision_ids: list[str]
    requires_revalidation_sections: list[str]
```

**2.2.4 Review Types**
```python
class ReviewFinding(BaseModel):
    finding_id: str
    phase: PhaseKey
    layer: ReviewLayer
    section_id: str
    category: FindingCategory
    issue: str
    evidence: str
    recommendation: str
    related_fact_ids: list[str] = Field(default_factory=list)
    fingerprint: str
    source_persona_path: str


class ReviewPass(BaseModel):
    phase: PhaseKey
    layer: ReviewLayer
    findings: list[ReviewFinding]
    wall_seconds: int
    model: str


class MergedFindingSet(BaseModel):
    phase: PhaseKey
    must_fix: list[ReviewFinding]
    should_improve: list[ReviewFinding]
    consider: list[ReviewFinding]
    duplicates_collapsed: dict[str, list[str]]
    changed_sections: list[str]


class InterviewTopic(BaseModel):
    topic_id: str
    source_layer: ReviewLayer
    section_id: str
    finding_ids: list[str]
    prompt: str
    context: str


class InterviewBrief(BaseModel):
    phase: PhaseKey
    topics: list[InterviewTopic]
    deferred_finding_ids: list[str] = Field(default_factory=list)


class FounderResponse(BaseModel):
    topic_id: str
    response_text: str
    captured_at: datetime


class ReviewResult(BaseModel):
    phase: PhaseKey
    passes: list[ReviewPass]
    merged: MergedFindingSet
    interview_brief: InterviewBrief | None = None
    revalidated_layers: list[ReviewLayer] = Field(default_factory=list)
```

### 2.3 Synthesis Redesign
- Template parsing: `template_parser.py` must parse the unchanged markdown templates into `PhaseSpec.sections` and `RequirementSpec` objects. For Phase 1, the parser loads the separate synthesis file directly. For Phases 2-10, it treats the template as a combined source, isolates synthesis-relevant sections from the `<!-- SYNTHESIS_START -->` marker onward when present, and extracts headings, required subsections, manifest requirements, and explicit “must include / must contain / produce / generate” directives into a checklist.
- Generation flow: use bounded section generation, not whole-document generation. The document engine creates a `SectionPlan`, then generates sections in dependency order. Small sections can be batched in groups of 2-3 when they share the same inputs; large sections remain one-call-per-section. The final markdown is assembled from validated `SectionDraft` objects.
- Validation gates: `validate_structure()` becomes deterministic and runs before any expert review. No phase enters L2/L3/L4 until every required section, subsection, and manifest field exists. After corrections, only touched sections and their dependents are revalidated first; a final whole-document structure pass happens before publication.
- State registry interaction: section generation reads only the fact namespaces declared in `SectionSpec.upstream_fact_ids` plus direct transcript excerpts tied to those facts. When a section draft is accepted, its asserted facts are written into the registry snapshot. If a section attempts to supersede a fact owned by an earlier phase, the registry requires explicit supersession metadata and founder confirmation where the authority rule says so.
- **Trade-off noted:** I chose section-by-section generation with optional small batching. I rejected full-document generation because the current evidence shows it pushes too much structural and factual reconciliation into review. I also rejected one-call-per-subsection because it would over-fragment the run and increase orchestration overhead without materially improving control.

### 2.4 Review Pipeline Redesign
- Execution model: hybrid. L1 structure validation is sequential and deterministic. L2/L3/L4 then run in parallel on the same L1-clean document, but each review receives section-scoped packets plus registry facts instead of the full document blob. Corrections are merged and applied once per review round.
- Finding merge and deduplication logic: every finding carries `section_id`, `related_fact_ids`, and a stable `fingerprint`. Merge rules collapse duplicates when `section_id + issue fingerprint + fact_ids` match. If L2 and L3 disagree on category, the stricter category wins (`must-fix > should-improve > consider`) and both source layers remain attached to the merged finding.
- Correction application method: hybrid, but bounded. First choice is `SectionRevision` against an existing `section_id` with checksum guard. If the finding introduces a missing required section, the engine inserts that section by `section_id`/ordinal, not by fuzzy string anchor. Full-section regeneration is allowed only for the touched section, never for the whole document.
- Topic ID preservation through founder re-engagement: `build_interview_brief()` emits stable `topic_id`s that are carried into `FounderResponse`. The workflow may only accept responses that map to known topics. `map_responses_to_updates()` resolves each topic back to exactly one `section_id` and one or more `finding_id`s.
- Revalidation trigger logic: any structural correction reruns L1 on touched sections and the final assembler. Any must-fix correction that changes a fact reruns the originating review layer plus any downstream layer that declared that fact in `related_fact_ids`. Founder-informed updates rerun L1 and any affected L2/L3/L4 passes for those sections only. One additional targeted review cycle is allowed; after that, unresolved findings are blocked for human review rather than looping.
- **Trade-off noted:** I chose parallel L2/L3/L4 with one merged correction pass. I rejected the older sequential per-layer correction model because the code and evidence show it spent too much time re-authoring the document three times. I also rejected “one giant merged full-document rewrite” because it destroys provenance and makes revalidation impossible to scope.

### 2.5 Configuration & Model Support
```python
class ModelTierConfig(BaseModel):
    tier: ModelTier
    model_id: str
    max_context_tokens: int
    max_output_tokens: int
    thinking_supported: bool
    default_thinking: ThinkingMode
    beta_headers: list[str] = Field(default_factory=list)


class RoleExecutionConfig(BaseModel):
    input_budget_tokens: int
    output_budget_tokens: int
    thinking_mode: ThinkingMode
    max_parallel_calls: int = 1


class RunConfig(BaseModel):
    active_tier: ModelTier
    max_run_cost_usd: float = 200.0
    research_backends: list[str]
    tiers: dict[ModelTier, ModelTierConfig]
    role_budgets: dict[LlmRole, dict[ModelTier, RoleExecutionConfig]]
```

- 4 model tiers are defined as:
  - `haiku_4_5 -> claude-haiku-4-5-20251001`
  - `sonnet_4_5 -> claude-sonnet-4-5-20241022`
  - `sonnet_4_6_standard -> claude-sonnet-4-6`
  - `sonnet_4_6_high -> claude-sonnet-4-6`
- A single config change switches all roles: `RunConfig.active_tier`. No role-level model IDs are set directly; every role resolves from the active tier.
- Thinking mode toggle logic:
  - Haiku 4.5: always `OFF`, regardless of requested setting.
  - Sonnet 4.5 and Sonnet 4.6 standard: `OFF`, `STANDARD`, or `HIGH` allowed per role budget.
  - Sonnet 4.6 high: same model as standard tier, but the config sets review/synthesis roles to `HIGH` by default.
- Cost ceiling enforcement mechanism:
  - Before every model call, `assert_cost_headroom()` reserves the worst-case cost for that role’s configured input/output budget under the active tier.
  - If `spent + reserved > max_run_cost_usd`, the phase aborts before the call.
  - After the response, the reservation is settled against actual usage and released.

Token budget table per role per model tier:

| Role | Haiku 4.5 | Sonnet 4.5 | Sonnet 4.6 std | Sonnet 4.6 high |
|---|---|---|---|---|
| Guide | 120k in / 8k out / off | 180k / 12k / standard | 220k / 12k / standard | 220k / 12k / high |
| Founder | 48k / 4k / off | 64k / 4k / off | 64k / 4k / off | 64k / 4k / off |
| Synthesis | 80k / 10k / off | 120k / 14k / standard | 140k / 14k / standard | 140k / 16k / high |
| Review L2 | 90k / 8k / off | 140k / 12k / standard | 140k / 12k / standard | 140k / 12k / high |
| Review L3 | 90k / 8k / off | 140k / 12k / standard | 140k / 12k / standard | 140k / 12k / high |
| Review L4 | 70k / 6k / off | 100k / 8k / standard | 100k / 8k / standard | 100k / 8k / high |
| Re-engagement | 70k / 6k / off | 100k / 8k / standard | 100k / 8k / standard | 100k / 8k / high |
| Consistency | 110k / 8k / off | 160k / 12k / standard | 180k / 12k / standard | 180k / 12k / high |

### 2.6 Migration Order
**Step 1: Extract configuration, contracts, and artifact loading**
- **Source:** Extract from `main.py` lines 84-181, 258-388, 1007-1135
- **Validation:** Unit tests for config resolution, phase order, artifact path loading, and cost-state serialization
- **Dependencies:** None
- **Estimated complexity:** Medium

**Step 2: Build the template parser and deterministic L1 checker**
- **Source:** Write fresh; borrow requirement-extraction intent from `main.py` lines 2427-2466 and 2709-2772
- **Validation:** Parser tests on `phase-1-synthesis.md` and `phase-2-users.md`; fixture tests that intentionally remove sections from sample deliverables and verify exact L1 failures
- **Dependencies:** Step 1
- **Estimated complexity:** Large

**Step 3: Extract the model gateway and research gateway**
- **Source:** Extract from `main.py` lines 401-955 and 2016-2407
- **Validation:** Mocked API tests for retries, empty-response rejection, Haiku thinking suppression, and structured-response parsing
- **Dependencies:** Step 1
- **Estimated complexity:** Medium

**Step 4: Build the cross-phase state registry and founder-memory projection**
- **Source:** Write fresh; reuse conceptual intent from `main.py` lines 1588-1665 and 1724-1843
- **Validation:** Load sample deliverables and reproduce the known count/pricing/permission facts from `cross-phase-consistency.json` as registry entries with ownership and supersession metadata
- **Dependencies:** Steps 1-2
- **Estimated complexity:** Large

**Step 5: Build the conversation runner on top of the new gateway contracts**
- **Source:** Extract from `main.py` lines 1142-1383 and 1961-2002
- **Validation:** Transcript fixtures, tool-loop tests, and fact-candidate extraction tests on the Ocean Golf scenario
- **Dependencies:** Steps 1, 3, 4
- **Estimated complexity:** Large

**Step 6: Build the section-aware document engine**
- **Source:** Extract prompt fragments from `main.py` lines 1395-1564; write fresh section planning, assembly, and deterministic validation
- **Validation:** Generate Phase 1 and Phase 2 section bundles from recorded transcripts; verify that final assembly passes deterministic L1 without entering expert review for missing sections
- **Dependencies:** Steps 2-5
- **Estimated complexity:** Large

**Step 7: Build the section-aware review orchestrator**
- **Source:** Extract persona loading and classification logic from `main.py` lines 2630-2937; write fresh merge/dedupe and topic-preserving interview-brief logic
- **Validation:** Replay sample expert-review fixtures, verify merged finding counts, ensure duplicate findings collapse correctly, and confirm `topic_id -> section_id` survives the brief/response/update loop
- **Dependencies:** Steps 1-6
- **Estimated complexity:** Large

**Step 8: Build the phase engine and workflow runner**
- **Source:** Extract orchestration intent from `main.py` lines 3820-4273; write fresh checkpointed execution around the new modules
- **Validation:** First end-to-end single-phase run using Phase 1 only; then a two-phase run proving the registry carries canonical facts from Phase 1 to Phase 2
- **Dependencies:** Steps 1-7
- **Estimated complexity:** Medium

**Step 9: Build the consistency auditor and publication gate**
- **Source:** Rewrite `main.py` lines 3970-4078 to be registry-first and blocking
- **Validation:** Reproduce the 14 known issues from `cross-phase-consistency.json`, then verify that unresolved critical drift blocks publication
- **Dependencies:** Steps 4 and 8
- **Estimated complexity:** Medium

**Main.py retirement criteria:** The old file can be deleted only when the new CLI runs all 12 phase units, deterministic L1 replaces prompt-based structure checking, cross-phase consistency is registry-backed and blocking, topic IDs survive founder re-engagement end-to-end, GitHub publication is invoked only after consistency/policy gates pass, and CI verifies that no module imports from more than 3 other project modules.

**First end-to-end test possible after:** Step 8

---

## SUMMARY

### Top 3 Highest-Impact Changes
- 1. Replace prior-deliverable concatenation with a canonical cross-phase fact registry so pricing, counts, permissions, and service inventories stop drifting silently.
- 2. Replace whole-document synthesis with section-aware generation plus deterministic L1 validation so review stops doing structural repair work.
- 3. Replace fuzzy patching and combined founder responses with section-scoped revisions and topic-preserving re-engagement so every correction stays traceable and revalidatable.

### Estimated Total Migration Complexity
Very Large — this is not a refactor of one function or one subsystem. The current architecture’s core abstraction is “long text plus prompt,” and the proposed design replaces that with typed state, section-aware generation, deterministic validation, and a new control-plane boundary. The evidence suggests that incremental cleanup inside `main.py` will keep paying review-time tax without eliminating the root causes.

### Risks and Open Questions
- The hardest technical risk is template parsing fidelity. The templates must remain unchanged, so the parser needs strong fixture coverage across Phase 1’s split template and Phases 2-10’s combined template style.
- Fact-ownership rules need deliberate product judgment. Some late-phase documents legitimately refine earlier assumptions, and the authority map must encode where supersession is allowed versus where it should block for founder approval.
- The review personas are worth preserving, but the prompt contract should be narrowed. Otherwise the system will keep generating process-audit findings like the noisy Phase 6a research-proof requests.
- Founder memory should become a registry projection, not another summarization artifact. That is a cleaner design, but it changes the semantics of what the “founder remembers” from prose to canonical decisions.
