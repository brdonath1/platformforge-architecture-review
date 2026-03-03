# PlatformForge Orchestrator — Architecture Review & Re-Architecture Specification

## What This Repository Contains

This is a complete review package for the PlatformForge orchestrator — a Python-based AI conversation system that guides non-technical founders through a structured 10-phase methodology to produce comprehensive technical specifications for software platforms.

The orchestrator runs automated conversations between two AI instances (Guide and Founder), synthesizes deliverables from those conversations, reviews them through a 4-layer expert pipeline, corrects issues, and publishes results to GitHub. It currently exists as a single ~190KB Python file (~4,200 lines).

## Repository Structure

```
code/
  main.py              — The orchestrator (~190KB, ~4,200 lines). THE PRIMARY ANALYSIS TARGET.
  CLAUDE.md            — Implementation specs and recent decision addenda (~30KB)

templates/             — 14 phase template files (~720KB total) that drive conversation and synthesis
  master-system-prompt.md    — Core system prompt for the Guide AI
  phase-1-conversation.md    — Phase 1 conversation template
  phase-1-synthesis.md       — Phase 1 synthesis template (separate from conversation)
  phase-2-users.md           — Phases 2-10 use combined conversation+synthesis templates
  phase-3-features.md
  phase-4-data.md
  phase-5-technical-architecture.md
  phase-6a-design-foundation.md
  phase-6b-page-architecture.md
  phase-6c-interaction-synthesis.md
  phase-7-build-planning.md
  phase-8-lifecycle-operations.md
  phase-9-review-validation.md
  phase-10-github-push-handoff.md

personas/              — Review persona definitions for the 4-layer expert review pipeline
  l2-domain-experts.md       — Domain expert personas (per-phase specialists)
  l3-downstream-consumers.md — Downstream consumer personas (developers, designers, etc.)
  l4-founder-comprehension.md — Founder comprehension reviewer
  review-config.md           — Review pipeline configuration and rules

scenario/
  persona.md           — "Ocean Golf" test founder scenario (~12KB). Used for all test runs.

architecture/          — Existing design documents
  d188-review-architecture.md  — Full spec for the 4-layer review architecture (~30KB)
  compliance-checklist.md      — Template compliance assertions (~16KB, ~120 assertions)
  module-architecture.md       — Current module breakdown documentation

evidence/              — Output from a complete 10-phase Haiku 4.5 test run
  review-pipelines/    — 12 phase review pipeline summary JSONs (timing, deltas, pass/fail)
  critic-reports/      — 12 phase critic evaluation reports
  expert-reviews/      — 36 files: L2, L3, L4 review JSONs for all 12 phases
  interview-briefs/    — 12 XML files showing re-engagement topic generation
  metrics/             — Phase metrics, cost reports, cross-phase consistency analysis, timing
  corrections-sample/  — 4 representative correction files (raw XML patches)

deliverables-sample/   — 3 representative deliverables + founder memory
  phase-1-deliverable.md      — Phase 1 output (~155KB)
  phase-6a-deliverable.md     — Phase 6a output (~194KB) — high correction delta
  phase-8-deliverable.md      — Phase 8 output (~244KB) — highest correction delta
  founder-memory.md           — Append-only founder memory artifact
```

## What We Want You To Do

### Phase 1: Architecture Review

Analyze the orchestrator codebase and all supporting materials to identify:

1. **Architectural Problems** — Structural issues in the system design, not just bugs. Trace each to specific code locations (line ranges) and evidence from the test run data.

2. **Root Cause Analysis** — For each major problem, identify why it exists architecturally. Not "the code has a bug" but "the architecture makes this class of bug inevitable."

3. **Fragility Map** — The top 10 most fragile points in the codebase. Where would a small change cause distant breakage? Where are contracts implicit rather than explicit?

4. **Cross-Phase Consistency Analysis** — The system produces 12 deliverables across 10 phases. These deliverables reference each other (pricing, counts, permissions, services). How does the architecture handle (or fail to handle) cross-phase consistency? Reference `evidence/metrics/cross-phase-consistency.json` for concrete data.

5. **Review Pipeline Effectiveness** — The 4-layer review pipeline (L1 compliance, L2 domain expert, L3 downstream consumer, L4 founder comprehension) is a major architectural investment. Analyze whether it's achieving its goals. Look at the correction deltas in review-pipeline JSONs, expert review findings, and how corrections flow through the system.

### Phase 2: Re-Architecture Specification

Based on your analysis, produce a complete implementation specification for a re-architected orchestrator. This spec will be handed to an AI coding agent (Claude Code) for implementation, so it must be precise enough that another AI can implement without ambiguity.

The specification must cover:

1. **MODULE MAP**
   - Final module list with single-responsibility descriptions
   - Public API for each module (function signatures with type hints)
   - Data flow between modules (which calls which, what gets passed)
   - No module should import from more than 3 other project modules

2. **DATA CONTRACTS**
   - Pydantic models or typed dataclasses for every inter-module object
   - The cross-phase state registry schema (if you determine one is needed)
   - Patch/correction object schemas
   - Finding object schema (typed, with source layer tracking)
   - Review result schema

3. **SYNTHESIS REDESIGN**
   - How templates get parsed into section checklists
   - Section-aware generation flow (section-by-section vs bounded groups)
   - Validation gates and where they sit in the pipeline
   - How synthesis interacts with any cross-phase state mechanism

4. **REVIEW PIPELINE REDESIGN**
   - Optimal execution model (sequential, parallel, or hybrid) with reasoning
   - How findings merge and deduplicate before correction
   - How corrections are applied (patch-based, regeneration, or hybrid)
   - Topic ID preservation through founder re-engagement
   - Revalidation trigger logic after corrections

5. **CONFIGURATION & MODEL SUPPORT**
   - Must support 4 model tiers: Haiku 4.5, Sonnet 4.5, Sonnet 4.6 standard, Sonnet 4.6 high reasoning
   - Single config block switches all roles between tiers
   - Token budgets per role must be model-aware (Haiku caps at 200K context)
   - Thinking mode toggle (disabled for Haiku, configurable for others)

6. **MIGRATION ORDER**
   - Which modules to build first, second, third
   - What can be extracted from main.py vs written fresh
   - How to validate each module independently before integration
   - When the first end-to-end test becomes possible
   - Explicit criteria for when the old main.py can be retired

## Constraints The Spec Must Respect

- The 10-phase methodology is V1.0 and does NOT change
- 23 deliverables and all template files are unchanged
- The Ocean Golf test scenario is unchanged
- Research integration: Perplexity API + Grok API + Anthropic web_search must all work
- The 4-layer expert review architecture (L1/L2/L3/L4) is preserved
- All 4 persona files drive L2/L3/L4 reviews — preserved as-is
- Git push to GitHub after each phase must continue working
- Cost ceiling of $200/run must be enforceable
- The founder memory concept stays but its implementation is open to redesign
- The system uses the Anthropic Messages API for all LLM calls

## Key Evidence To Examine

Start with these files for the highest-signal analysis:

1. `code/main.py` — The entire orchestrator. Focus on:
   - `run_phase()` and `main()` for the overall flow
   - `run_synthesis()` for deliverable generation
   - `run_review_pipeline()` for the review architecture
   - `run_correction_synthesis()` and `apply_patches()` for correction handling
   - `load_prior_deliverables()` for cross-phase state management
   - `run_cross_phase_consistency_check()` for post-run validation
   - `_execute_stream()` and `serialize_for_replay()` for API interaction fragility

2. `evidence/metrics/cross-phase-consistency.json` — Concrete data on cross-phase contradictions

3. `evidence/review-pipelines/` — All 12 pipeline summaries showing correction deltas per phase

4. `templates/phase-1-synthesis.md` vs `templates/phase-2-users.md` — Compare the separate synthesis template (Phase 1) against a combined template (Phase 2+) to understand the dual-template pattern

5. `architecture/d188-review-architecture.md` — The design intent for the review pipeline

## Output Format

Your output will be compared directly against reviews from other AI models. To enable structured comparison, you MUST follow this exact document template. Do not skip sections, rename sections, or reorder them. Every section must be present even if brief.

Do NOT produce actual Python implementation code. Produce the analysis and specification that an implementation team would work from. Use code blocks for all type definitions and function signatures.

### Required Document Structure

```
# PlatformForge Orchestrator — Architecture Review & Re-Architecture Specification

**Reviewing Model:** [Your model name and version]
**Date:** [Date]
**Files Analyzed:** [List all files you read from the repository]

---

## PHASE 1: ARCHITECTURE REVIEW

### 1.1 System Comprehension Summary
[Demonstrate your understanding of the orchestrator's architecture in 2-4 paragraphs.
Cover: overall flow, conversation layer, synthesis layer, review pipeline, 
cross-phase state management, and publishing. Reference specific function names 
and line ranges.]

### 1.2 Architectural Problems
[Number each problem sequentially. For EACH problem, use this exact format:]

**Problem N: [Title]**
- **Location:** [Function names and line ranges]
- **What happens:** [Factual description of the behavior]
- **Why it is a problem:** [Architectural reasoning, not just "it's bad"]
- **Evidence:** [Specific data from the evidence files — scores, deltas, 
  contradiction counts, metrics. Cite filenames.]

### 1.3 Root Cause Analysis
[For each major problem identified in 1.2, trace it to its architectural root cause.
Group related problems that share a root cause. Use this format:]

**Root Cause A: [Title]**
- **Problems it causes:** [Reference problem numbers from 1.2]
- **Architectural mechanism:** [How the architecture makes this inevitable]
- **Evidence chain:** [Data path from code to observed failure]

### 1.4 Fragility Map (Top 10)
[Rank-ordered. For EACH entry, use this exact format:]

**Rank N: [Function/subsystem name] ([line range])**
- **Why it is fragile:** [One sentence]
- **Blast radius:** [What breaks if this breaks]
- **Recommended fix:** [One sentence]

### 1.5 Cross-Phase Consistency Analysis
[Analyze how the system manages (or fails to manage) facts across phases.
Reference cross-phase-consistency.json specifically. Cover:]
- Current consistency score and number of issues found
- Categories of drift (pricing, counts, permissions, services, etc.)
- Architectural cause of each drift category
- Which phases are most affected and why

### 1.6 Review Pipeline Effectiveness
[Analyze the 4-layer review pipeline using evidence data. Cover:]
- L1 initial miss counts per phase (cite review-pipeline JSONs)
- Correction deltas per phase (characters added during review)
- Whether the pipeline is doing review work or authorship work
- Expert review finding quality (sample from expert-review JSONs)
- Re-engagement effectiveness (reference interview briefs)
- Net assessment: is the pipeline achieving its design intent?

---

## PHASE 2: RE-ARCHITECTURE SPECIFICATION

### 2.1 Module Map
[For EACH module, use this exact format:]

**Module: [filename.py]**
- **Responsibility:** [Single sentence]
- **Imports from:** [List other project modules, max 3]
- **Public API:**
  ```python
  [Function signatures with full type hints]
  ```

[After all modules, include:]
**Data Flow Diagram:**
```
[ASCII or text diagram showing which modules call which]
```

### 2.2 Data Contracts
[Use code blocks for every type definition. Group as:]

**2.2.1 Core Types**
```python
[Pydantic models or dataclasses for fundamental objects]
```

**2.2.2 Cross-Phase State Registry Schema**
```python
[The state store schema with supersession rules]
```

**2.2.3 Patch/Correction Types**
```python
[Patch object, finding object, correction result]
```

**2.2.4 Review Types**
```python
[Review result, finding set, merge result]
```

### 2.3 Synthesis Redesign
[Cover each of these explicitly:]
- Template parsing: how templates become section checklists
- Generation flow: section-by-section, bounded groups, or other approach
- Validation gates: where validate_deliverable() sits, what blocks on failure
- State registry interaction: how synthesis reads/writes canonical facts
- **Trade-off noted:** [Any design choice where you picked one option over another.
  State what you chose, what you rejected, and why.]

### 2.4 Review Pipeline Redesign
[Cover each of these explicitly:]
- Execution model: sequential, parallel, or hybrid — with reasoning
- Finding merge and deduplication logic
- Correction application method (patch-based, regeneration, or hybrid)
- Topic ID preservation through founder re-engagement
- Revalidation trigger logic: which layers re-review which changed sections
- **Trade-off noted:** [Same format as above]

### 2.5 Configuration & Model Support
[Provide the actual config schema. Must show:]
- How 4 model tiers are defined (Haiku 4.5, Sonnet 4.5, Sonnet 4.6 std, Sonnet 4.6 high)
- How a single config change switches all roles
- Token budget table per role per model tier
- Thinking mode toggle logic
- Cost ceiling enforcement mechanism

### 2.6 Migration Order
[Numbered sequence. For EACH step:]

**Step N: [What to build]**
- **Source:** Extract from main.py lines [X-Y] / Write fresh
- **Validation:** [How to verify this module works before proceeding]
- **Dependencies:** [Which prior steps must be complete]
- **Estimated complexity:** Small / Medium / Large

[End with:]
**Main.py retirement criteria:** [Explicit conditions under which the old 
file can be deleted]

**First end-to-end test possible after:** Step [N]

---

## SUMMARY

### Top 3 Highest-Impact Changes
[Rank ordered. One sentence each with expected impact.]

### Estimated Total Migration Complexity
[Small / Medium / Large / Very Large — with reasoning]

### Risks and Open Questions
[Anything you are uncertain about or that needs human judgment]
```

Follow this template exactly. Every section header must match. Every sub-format must match. This enables direct section-by-section comparison across reviewing models.
