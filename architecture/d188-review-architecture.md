# D-188: Multi-Layer Expert Review Architecture

> **Status:** DESIGN COMPLETE — ready for implementation
> **Created:** S85 (2026-03-02)
> **Updated:** S88 (2026-03-02) — D-189/D-190/D-191 integrated, all 5 design items completed
> **Replaces:** `critic_review_deliverable()` (main.py ~lines 2501-2615) and `run_recalibration()` (main.py ~lines 2660+)
> **Location:** artifacts/current/d188-review-architecture.md

---

## Problem Statement

The current critic function (`critic_review_deliverable()`, main.py lines ~2501-2615) is a generic quality reviewer with no phase-specific knowledge. It receives the deliverable and prior deliverables but NOT the phase template that defines what the deliverable should contain. Its system prompt says "find genuine flaws" without any rubric for what constitutes a flaw. Despite this, the critic's findings drive automated recalibration (D-181 `run_recalibration()`, lines ~2660+), which re-engages the founder with expert personas and surgically modifies deliverables. The entire quality control chain — from review through correction — operates without reference to the methodology's own specifications.

**Specific code reference:** The critic system prompt (line ~2559) reads: "You are a rigorous quality reviewer. Find genuine flaws — factual errors, contradictions with prior deliverables, missing required sections, and architectural inconsistencies." It has NO access to what "required sections" actually are for any given phase. The user prompt (line ~2534) says "You are an independent quality reviewer for a Phase N deliverable" with no phase-specific criteria.

**Impact:** The system has been "improving" deliverables based on uninformed review. Recalibration cycles ($5-10 each per D-185 notes) may have degraded deliverables by injecting content addressing fabricated gaps. Clean run results should treat all critic scores as uninformed baselines.

---

## Agreed Architecture: 4-Layer Sequential Expert Review

Each phase is a self-contained cycle. No phase proceeds to the next until its deliverable has passed through all 4 layers and any required revisions are complete.

### Layer 1 — Specification Compliance (Mechanical)

- **Input:** Deliverable + corresponding phase template
- **Reviewer:** Not a persona — a structured checklist audit
- **Task:** Binary pass/fail on every required element in the template. Does Section X exist? Are manifest fields A, B, C populated? Are required cross-references present? Are EOF sentinels in place?
- **Output:** List of missing/incomplete items (must-fix only — these are objective, binary gaps)
- **Action:** Must-fix items go directly to synthesis for surgical correction. Re-check Layer 1 after correction. Deliverable must be structurally complete before proceeding to Layer 2.
- **Key principle:** This layer has no opinions. It only checks whether the template's requirements are present in the deliverable. A section can be present but poorly written — Layer 1 doesn't care. It only flags absence.

### Layer 2 — Domain Expert Review (Technical Quality)

- **Input:** Structurally complete deliverable (post-Layer 1 correction if needed) + phase template
- **Reviewer:** The persona who would RECEIVE and USE this deliverable in a real company. Changes per phase. This is the subject matter expert for the deliverable's domain.
- **Task:** Is the content technically sound? Would this actually work if built? Are there errors, bad patterns, missing considerations that a domain expert would catch? Does the content reflect current best practices?
- **Output:** Classified feedback — each item tagged as must-fix, should-improve, or consider
- **Independence:** Does NOT see Layer 1's findings. Only sees the corrected deliverable.
- **Key principle:** This is the deepest, most specialized review. The expert evaluates against their domain knowledge AND the template specification. They can identify both "this is wrong" and "the template asked for X and what you wrote doesn't adequately address it."

### Layer 3 — Downstream Consumer Review (Next-Phase Usability)

- **Input:** L2-corrected deliverable (post-Layer 2 must-fix corrections) + phase template + knowledge of what the NEXT phase needs
- **Reviewer:** The persona who would use this deliverable as INPUT for their work in the next phase. Typically this is the Layer 2 persona of the NEXT phase.
- **Task:** Can I do my job based on this document? Are there gaps that would stall my work? Is the information organized in a way I can consume? Are there ambiguities that would force me to make assumptions?
- **Output:** Classified feedback — each item tagged as must-fix, should-improve, or consider
- **Independence:** Does NOT see Layer 2's feedback. Only sees the deliverable.
- **Key principle:** Catches a completely different class of problems — not errors in the document, but gaps that would block the next team. A technically perfect Phase 4 schema that doesn't include enough detail for Phase 5's infrastructure decisions is a Layer 3 finding.

### Layer 4 — Founder Comprehension Check (Accessibility)

- **Input:** L3-corrected deliverable (post-Layer 3 must-fix corrections)
- **Reviewer:** Non-technical founder persona (same persona across all phases)
- **Task:** Can the person who paid for this understand what they're getting? Are technical decisions explained in business terms? Could they discuss this with a co-founder, investor, or potential CTO? Is there a founder-facing summary layer?
- **Output:** Classified feedback — each item tagged as must-fix, should-improve, or consider
- **Independence:** Does NOT see Layer 2 or Layer 3 feedback. Only sees the deliverable.
- **Key principle:** The deliverable needs to be technically precise for developers AND comprehensible to the founder. This layer ensures the accessibility requirement isn't sacrificed for technical depth.

---

## Post-Review Flow (D-189: Sequential Corrected-Per-Layer Pipeline)

The review pipeline is fully sequential and blocking. Each layer reviews the corrected output from the previous layer, not the original synthesis. Quality compounds across layers.

**Full pipeline per phase:**

1. **Synthesis** generates deliverable draft.
2. **Layer 1 (Compliance)** audits against template. Must-fix items (missing sections, absent fields) → correction synthesis → L1 re-check until clean.
3. **Layer 2 (Domain Expert)** reviews the L1-corrected deliverable. Must-fix items → correction synthesis → L1 re-check. Should-improve and consider items held.
4. **Layer 3 (Downstream Consumer)** reviews the L2-corrected deliverable. Must-fix items → correction synthesis → L1 re-check. Should-improve and consider items held.
5. **Layer 4 (Founder Comprehension)** reviews the L3-corrected deliverable. Must-fix items → correction synthesis → L1 re-check. Should-improve and consider items held.
6. **Should-improve consolidation.** All should-improve items from L2, L3, L4 consolidated into a single **interview brief**, organized by source layer.
7. **Founder re-engagement.** Guide re-engages the founder in ONE conversation covering all should-improve items.
8. **Targeted synthesis update** incorporating founder's actual answers.
9. **Final L1 re-check** on the updated deliverable (compliance verification only — no full 4-layer re-review to prevent infinite cycles).
10. **Consider** items → attached as companion **review notes document** (.md) alongside the deliverable.
11. **DONE** → pristine .md deliverable + review notes → save → push → proceed to next phase.

**Blocking model (D-189):** This pipeline is blocking across all three surfaces (Dry Run, Beta Harness, Production). No phase proceeds to the next until its deliverable has completed the full pipeline. This maximizes quality at the cost of runtime — accepted tradeoff per D-189.

---

## Feedback Classification Schema

Every review finding from L2, L3, and L4 MUST be classified into exactly one of three categories. L1 is excluded — it only produces binary pass/fail results (present or absent).

### Classification Decision Tree

Apply these tests IN ORDER. The first "yes" determines the category:

1. **Is this factually wrong?** (incorrect data, contradicts a prior deliverable, references something that doesn't exist) → **must-fix**
2. **Is a required element missing or empty?** (template says include X, deliverable doesn't have X or X has no substance) → **must-fix**
3. **Would this block the next phase's work?** (the downstream team cannot proceed without this being resolved) → **must-fix**
4. **Is this thin, vague, or assumed where the founder's actual knowledge would produce better content?** (the content exists but lacks specificity that only the founder can provide) → **should-improve**
5. **Is a technical concept unexplained for a non-technical reader?** (jargon without plain-language explanation, no business impact stated) → **should-improve**
6. **Everything else** — suggestions, alternatives, enhancements, nice-to-haves, stylistic preferences → **consider**

### Boundary Rules

These resolve ambiguous cases explicitly:

- **"Thin but not wrong"** → should-improve, not must-fix. If the section exists and says something accurate but lacks depth, the founder can fill it in. It's not an error.
- **"Missing subsection vs missing section"** → If the TEMPLATE lists it as a required section/subsection, it's must-fix. If it's something the reviewer thinks should be there but the template doesn't require it, it's should-improve at most.
- **"Could be better"** → consider. If the deliverable works without the change, it's not must-fix or should-improve.
- **"Wrong model/framework choice"** → must-fix ONLY if it contradicts an explicit founder decision from the conversation. Otherwise should-improve (raise it with the founder).
- **"Inconsistency within the same deliverable"** → must-fix. Section A says X, Section B says Y — that's a factual conflict.
- **"Inconsistency with a prior deliverable"** → must-fix. Cross-phase contradictions are always errors.

### Output Format (Required for All Reviewers)

Every finding MUST use this exact structure. No free-form prose.

```xml
<finding>
  <id>L{layer}-{number}</id>
  <category>must-fix | should-improve | consider</category>
  <section>{deliverable section where the issue lives}</section>
  <issue>{one sentence: what is wrong or missing}</issue>
  <evidence>{quote or reference from deliverable OR template that proves this is an issue}</evidence>
  <recommendation>{one sentence: specific action to resolve}</recommendation>
</finding>
```

**Why structured output matters:** With lower-capability models, free-form feedback drifts into vague commentary. The XML format forces precision — each finding must cite a specific section, state a specific issue, provide specific evidence, and propose a specific fix. If the reviewer can't fill all fields, the finding isn't well-formed enough to act on.

### Category Definitions

#### must-fix
**Definition:** An objective error, factual inaccuracy, or critical gap that would cause the deliverable to fail its purpose if shipped as-is. A qualified professional would agree this is wrong or missing without further discussion.

**Litmus test:** "Can I point to a specific fact, reference, or template requirement that proves this is wrong?" If yes → must-fix.

**Correction path:** Direct to correction synthesis. No founder input needed.

**Examples:**
- "The schema references a `bookings` table but no such table is defined in the ERD." (L2 — factual error)
- "Phase 5 architecture specifies PostgreSQL but Phase 4 data model was designed for MongoDB." (L3 — cross-phase contradiction)
- "Section 3.2 (Revenue Model) is listed in the template as required but contains no content." (L2 — missing required element)

#### should-improve
**Definition:** A quality gap where the content exists but lacks specificity, depth, or clarity that the founder's actual knowledge could resolve. The deliverable is not wrong — it's incomplete in a way that only the founder can fix.

**Litmus test:** "Would asking the founder a specific question produce content that makes this section materially better?" If yes → should-improve.

**Correction path:** Consolidated into interview brief → founder re-engagement → targeted synthesis update.

**Examples:**
- "The competitive analysis lists 3 competitors but doesn't address pricing differentiation — was this discussed with the founder?" (L2 — underspecified)
- "The API rate limiting section says 'standard limits' without numbers. Infrastructure team needs concrete values." (L3 — insufficient for downstream)
- "The technical architecture uses 'edge functions' and 'RLS policies' with no plain-language explanation." (L4 — accessibility gap)

#### consider
**Definition:** A suggestion or enhancement that is not a flaw. The deliverable is correct and usable without this change.

**Litmus test:** "Would the deliverable still pass review if this suggestion were ignored entirely?" If yes → consider.

**Correction path:** No correction. Attached as companion review notes document.

**Examples:**
- "The feature roadmap could optionally include effort estimates per feature." (L3 — nice to have)
- "Consider adding a glossary appendix for founder reference." (L4 — enhancement)
- "An alternative caching strategy would be edge caching via Cloudflare Workers." (L2 — alternative approach)

---

## Interview Brief Format

The interview brief consolidates all should-improve findings from L2, L3, and L4 into a single structured document that the Guide uses to re-engage the founder. One brief per phase. One conversation per brief.

### Brief Structure

```xml
<interview_brief phase="{phase_key}">
  <summary>
    {1-2 sentences: what was reviewed, how many should-improve
    items were found across which layers}
  </summary>

  <topic_group source="L2 — Domain Expert ({role_title})">
    <topic id="SI-{phase}-L2-{n}">
      <context>{1 sentence: what the deliverable currently says}</context>
      <gap>{1 sentence: what's missing or thin}</gap>
      <question>{the specific question to ask the founder}</question>
    </topic>
  </topic_group>

  <topic_group source="L3 — Downstream Consumer ({role_title})">
    <topic id="SI-{phase}-L3-{n}">
      <context>{1 sentence: what the deliverable currently says}</context>
      <gap>{1 sentence: why this is insufficient for the next phase}</gap>
      <question>{the specific question to ask the founder}</question>
    </topic>
  </topic_group>

  <topic_group source="L4 — Founder Comprehension">
    <topic id="SI-{phase}-L4-{n}">
      <context>{1 sentence: what the deliverable currently says}</context>
      <gap>{1 sentence: what's unclear for a non-technical reader}</gap>
      <question>{the specific question to ask the founder}</question>
    </topic>
  </topic_group>
</interview_brief>
```

### Guide Behavioral Rules for Re-engagement

1. **One conversation, not three.** The Guide weaves all topics into a natural dialogue — it does not conduct three separate interviews.
2. **L2 topics first, L4 topics last.** Deepest technical gaps first (while founder is fresh), accessibility clarifications last (lighter cognitive load).
3. **Ask, don't lead.** The question must be open enough for the founder to give a real answer. "Should we add pricing differentiation?" is leading. "How does Ocean Golf's pricing compare to competitors, and was that a deliberate choice?" gives the founder room.
4. **Max 8 topics per brief (configurable: `MAX_REENGAGEMENT_TOPICS`).** If more than 8 should-improve items exist, the Guide prioritizes by impact (items that affect the most deliverable content) and defers the rest to consider status. **FUTURE REVIEW:** This cap is initial — tune based on observed coherence in test runs.
5. **Capture verbatim.** The founder's answers are passed to targeted synthesis exactly as spoken. The Guide does not summarize, interpret, or editorialize.

---

## Targeted Synthesis Update Process

Corrections are applied surgically — the correction synthesis receives the full deliverable but only modifies the sections identified in the findings. It does NOT regenerate the entire deliverable.

### Must-Fix Correction (after each layer)

Input to correction synthesis:

```xml
<correction_request>
  <deliverable>{full deliverable markdown}</deliverable>
  <findings>
    {all must-fix findings from the current layer, in XML format}
  </findings>
  <instruction>
    Apply ONLY the corrections specified in the findings above.
    For each finding:
    1. Locate the section named in <section>.
    2. Apply the fix described in <recommendation>.
    3. Do not modify any other section.
    Output the complete deliverable with corrections applied.
    Preserve all formatting, headings, and content outside the
    corrected sections exactly as-is.
  </instruction>
</correction_request>
```

**Key constraint:** The correction synthesis must output the COMPLETE deliverable, not just the changed sections. This ensures the document stays intact and L1 re-check can validate the full structure.

### Founder-Informed Update (after re-engagement)

Input to correction synthesis:

```xml
<founder_update_request>
  <deliverable>{full deliverable markdown}</deliverable>
  <interview_brief>{the original interview brief with topic IDs}</interview_brief>
  <founder_responses>
    <response topic_id="SI-{phase}-L2-{n}">
      {founder's verbatim answer}
    </response>
  </founder_responses>
  <instruction>
    For each founder response, update the deliverable section
    identified in the corresponding interview brief topic.
    Incorporate the founder's answer as authoritative content —
    do not paraphrase, soften, or editorialize. The founder's
    words represent ground truth about their business.
    Do not modify any section not referenced by a topic ID.
    Output the complete updated deliverable.
  </instruction>
</founder_update_request>
```

### Guardrails on Correction Synthesis

- **No creative additions.** The correction synthesis fixes what it's told to fix. It does not add content, sections, or ideas that weren't in the findings or founder responses.
- **No deletions unless specified.** If a finding says "remove the reference to X," it removes it. Otherwise all existing content is preserved.
- **One pass per trigger.** Must-fix corrections happen once per layer. Founder updates happen once after re-engagement. No iterative correction loops.

---

## Key Design Decisions (S85, updated S88)

| Decision | Rationale |
|----------|-----------|
| Each reviewer works INDEPENDENTLY | Prevents anchoring bias — Layer 3 shouldn't defer to Layer 2's findings |
| Sequential corrected-per-layer L1→L2→L3→L4 (D-189) | Each layer reviews output corrected by the previous layer, not the original. Quality compounds. Prevents later layers from flagging issues already fixed. |
| Blocking across all surfaces (D-189) | Same sequential pipeline in Dry Run, Beta Harness, and Production. Quality gate is hard — no phase advances until review is complete. |
| Sonnet 4.6 high effort baseline (D-190) | All review layers use Sonnet 4.6 with high effort thinking. Opus injected only where testing proves measurable quality gap. ~$135/run with caching vs $274 prior. |
| Fast iteration via model swap (D-191) | Single config variable switches all roles to Haiku 4.5 for mechanical testing (~$20/run, ~4h). Sonnet baseline preserved for quality validation. |
| Should-improve items trigger founder re-engagement | Brian's explicit direction — the founder's voice must stay in the deliverable. AI should not fill gaps with its own assumptions. |
| One consolidated re-engagement per phase | Avoids founder fatigue from 3 separate follow-up conversations |
| Process runs per-phase as a quality gate | Every phase builds on a reviewed, founder-verified, expert-approved foundation. Quality compounds across phases. |
| Each phase has its own reviewer cast | Domain expertise varies dramatically across phases — a DB architect has nothing useful to say about user personas |
| Layer 4 persona is consistent across phases | The founder comprehension bar is universal — same person, same perspective |
| No full re-review after revision | Layer 1 re-check only. Prevents infinite review loops while ensuring corrections were applied. |

---

## Model & Cost Architecture (D-190, D-191)

### Model Assignments

All roles use a single configurable model variable per category. Default configuration (D-190 quality mode):

| Role | Model | Max Tokens | Thinking | Notes |
|------|-------|-----------|----------|-------|
| Guide | Sonnet 4.6 | 65,536 | high | Steers conversation, web search |
| Founder | Sonnet 4.6 | 16,384 | none | Conversational only |
| Synthesis | Sonnet 4.6 | 128,000 | high | Deliverable generation |
| Utility | Sonnet 4.6 | 8,192 | none | Validation, memory |
| L1 Compliance | Sonnet 4.6 | 8,192 | none | Mechanical checklist |
| L2 Domain Expert | Sonnet 4.6 | 32,768 | high | Phase-specific SME |
| L3 Downstream | Sonnet 4.6 | 32,768 | high | Next-phase consumer |
| L4 Founder Comp | Sonnet 4.6 | 16,384 | high | Accessibility check |
| Correction Synthesis | Sonnet 4.6 | 32,768 | high | Surgical fixes |

**Fast iteration mode (D-191):** All roles switch to Haiku 4.5 via a single config block at the top of main.py. Estimated ~$20/run, ~4h runtime. Used for mechanical pipeline validation and rapid iteration. Haiku 4.5 caps at 200K context — all role allocations fit within this limit.

**Estimated costs per full 10-phase run:**

| Mode | Model | Est. Cost | Est. Runtime |
|------|-------|-----------|-------------|
| Fast iteration (D-191) | Haiku 4.5, no thinking | ~$15-25 | 3-5h |
| Quality baseline (D-190) | Sonnet 4.6, high effort | ~$135 | 12-18h |

### External Persona Files

Review personas are stored as external .md files, matching the existing pattern established by persona.md (founder). main.py loads these at startup and indexes by phase/layer.

```
dry-run/
  persona.md                    ← founder (exists)
  personas/
    l2-domain-experts.md        ← 10 phase-specific domain expert profiles
    l3-downstream-consumers.md  ← 10 phase-specific downstream consumer profiles
    l4-founder-comprehension.md ← 1 universal founder accessibility reviewer
    review-config.md            ← model assignments, token limits, layer flow
```

**Design rationale:**
- Group by layer (not by phase) because the L3→L2 chain must be verified for continuity — all L2 personas visible together, all L3 personas visible together.
- Prompt templates live in main.py; persona metadata (role, expertise, criteria) lives in the .md files. Runtime assembles full prompt from template + metadata.
- review-config.md is the single source of truth for model assignments per layer, making model swaps a one-file change.

---

## Per-Phase Reviewer Personas (PRELIMINARY — NOT FINALIZED)

These were brainstormed in S85 but need full definition. Each persona needs: role title, years/type of experience, specific expertise areas, evaluation criteria for that phase's deliverable, and prompt engineering for the API call.

| Phase | Layer 2 (Domain Expert) | Layer 3 (Downstream Consumer) |
|-------|------------------------|------------------------------|
| 1 (Vision/Strategy) | Co-founder / Strategic Advisor / Investor | Head of Product / UX Research Director |
| 2 (Users) | Head of Product / UX Research Director | Product Manager / VP Product |
| 3 (Features) | Product Manager / VP Product | Senior Database Architect / Backend Lead |
| 4 (Data Architecture) | Senior Database Architect / Backend Lead | CTO / VP Engineering |
| 5 (Technical Architecture) | CTO / VP Engineering | Design Director / Principal Designer |
| 6a/b/c (Design) | Design Director / Principal Designer | Engineering Manager / Technical PM |
| 7 (Build Planning) | Engineering Manager / Technical PM | DevOps Lead / Head of Infrastructure |
| 8 (Lifecycle/Ops) | DevOps Lead / Head of Infrastructure | QA Director / Release Manager |
| 9 (Review/Validation) | QA Director / Release Manager | Technical Program Manager |
| 10 (Handoff/Export) | Technical Program Manager | CTO (holistic review of complete package) |

**Layer 4** across all phases: Non-technical founder persona (consistent).

**NOTE:** The L3→L2 chain creates a natural flow where Phase N's downstream consumer IS Phase N+1's domain expert. This means every persona appears twice: once as a domain expert for their own phase, and once as the downstream consumer for the previous phase. This is intentional — they're evaluating from different perspectives each time.

---

## Implementation Plan for main.py

### Files to Create

```
dry-run/personas/
  l2-domain-experts.md        ← Phase-indexed L2 profiles
  l3-downstream-consumers.md  ← Phase-indexed L3 profiles
  l4-founder-comprehension.md ← Single universal L4 profile
  review-config.md            ← Model/token/thinking config per layer
```

### Config Changes (top of main.py)

```python
# Add after existing model constants (line ~92):
REVIEW_MODEL = FOUNDER_MODEL  # Default: same as other roles

# D-191 Fast Iteration Mode — uncomment to switch all roles:
# GUIDE_MODEL = "claude-haiku-4-5-20251001"
# FOUNDER_MODEL = "claude-haiku-4-5-20251001"
# SYNTHESIS_MODEL = "claude-haiku-4-5-20251001"
# REVIEW_MODEL = "claude-haiku-4-5-20251001"
# UTILITY_MODEL = "claude-haiku-4-5-20251001"

# Add Haiku to PRICING dict:
# "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00,
#   "cache_read": 0.10, "cache_write": 1.25}

# Review pipeline config
MAX_REENGAGEMENT_TOPICS = 8
MAX_L1_RETRIES = 2           # L1 re-check attempts before failing
MAX_CORRECTION_TOKENS = 32768
MAX_L2_TOKENS = 32768
MAX_L3_TOKENS = 32768
MAX_L4_TOKENS = 16384
```

### Code to Remove

| What | Lines | Replaced By |
|------|-------|-------------|
| `EXPERT_PERSONAS` dict | ~177-194 | External persona files |
| `critic_review_deliverable()` | ~2501-2615 | `run_review_pipeline()` |
| `run_recalibration()` | ~2660-2850+ | Post-review flow inside `run_review_pipeline()` |

### New Functions

```python
def load_review_personas() -> dict:
    """Load all persona files at startup. Returns nested dict
    indexed by layer and phase_key.
    Called once in main(). Result passed to pipeline."""

def run_l1_compliance(deliverable, template, phase_key,
                      cost_tracker) -> list[dict]:
    """Binary checklist audit. Returns list of missing/incomplete
    items. No findings XML — just section names + pass/fail."""

def run_layer_review(deliverable, template, phase_key, layer,
                     persona, prior_deliverables, cost_tracker)
                     -> list[dict]:
    """Generic reviewer for L2/L3/L4. Assembles prompt from
    template + persona metadata. Returns parsed findings XML.
    `layer` is 2, 3, or 4. Persona comes from loaded files."""

def run_correction_synthesis(deliverable, findings, phase_key,
                             cost_tracker) -> str:
    """Applies must-fix corrections. Returns complete corrected
    deliverable markdown."""

def build_interview_brief(findings_l2, findings_l3, findings_l4,
                          phase_key) -> str:
    """Consolidates should-improve items into XML interview brief.
    Applies MAX_REENGAGEMENT_TOPICS cap. Returns brief XML."""

def run_founder_reengagement(brief, persona, phase_key,
                             cost_tracker) -> list[dict]:
    """Guide re-engages founder using brief. Returns list of
    {topic_id, response} dicts."""

def run_targeted_update(deliverable, brief, responses, phase_key,
                        cost_tracker) -> str:
    """Applies founder responses to deliverable. Returns complete
    updated deliverable markdown."""

def run_review_pipeline(deliverable, template, phase_key, persona,
                        prior_deliverables, review_personas,
                        cost_tracker) -> tuple[str, str]:
    """MAIN ORCHESTRATOR. Runs full D-188/D-189 pipeline:
    L1 → correct → L2 → correct → L3 → correct → L4 → correct
    → brief → re-engage → update → final L1.
    Returns (final_deliverable, review_notes)."""
```

### Integration Point

In the main phase loop, replace:

```python
# OLD (current):
critic_report = critic_review_deliverable(deliverable, ...)
recalib_transcript = run_recalibration(phase_key, critic_report, ...)
# ... deliverable update from recalibration

# NEW:
final_deliverable, review_notes = run_review_pipeline(
    deliverable, template, phase_key, persona,
    prior_deliverables, review_personas, cost_tracker
)
```

### Persona File Format

Each persona file uses markdown with phase-indexed sections:

```markdown
# L2 Domain Expert Personas

## Phase 1
- **Role:** Co-founder / Strategic Advisor
- **Expertise:** Business model validation, market sizing,
  revenue assumptions, competitive positioning
- **Evaluation focus:** Are the strategic assumptions sound?
  Would an investor challenge any of these claims?
- **Key template sections:** [list from phase-1 template]

## Phase 2
...
```

main.py parses these into a dict at startup: `personas["l2"][1] → {role, expertise, focus, sections}`

---

## Relationship to Existing Components

| Current Component | Status After D-188 |
|------------------|-------------------|
| `critic_review_deliverable()` (lines ~2501-2615) | **REPLACED** by 4-layer review pipeline |
| `run_recalibration()` (lines ~2660+) | **REPLACED** by post-review flow (must-fix correction + should-improve re-engagement) |
| `EXPERT_PERSONAS` dict (lines ~177-194) | **REPLACED** by external persona files in `personas/` directory. Dict removed from main.py. |
| `GUIDE_MODEL`, `FOUNDER_MODEL`, `SYNTHESIS_MODEL` constants | **PRESERVED** — add `REVIEW_MODEL` constant. All four switchable via D-191 fast iteration config. |
| `PRICING` dict | **EXPANDED** — add `claude-haiku-4-5-20251001` pricing entry for D-191 mode. |
| D-181 (inter-phase expert recalibration) | **SUPERSEDED** by D-188. Expert re-engagement preserved but triggered by informed expert review, not uninformed critic. |
| Validation function (Sonnet structural check) | **ABSORBED** into Layer 1 (Compliance). Both perform structural checks — L1 replaces standalone validation. |

<!-- EOF: d188-review-architecture.md -->
