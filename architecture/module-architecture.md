# PlatformForge Phase 1 — Module Architecture Design

> **Decision:** D-76 — Modularize Phase 1 template from monolith to module set
> **Status:** DRAFT — requires review before implementation
> **Guardrail:** G-9 — No split that breaks cross-module edge case integrity

---

## 1. Module Boundaries

### Module A: Foundation (phase-1-foundation.md)
**Contents:** phase_role + context_load_manifest + decision_ledger_contextualization
**Size:** ~26 KB
**Purpose:** AI identity, context budget rules, and the D-55 ledger schema that every other module references.
**When loaded:** Always — this is the base layer for both conversation and synthesis modes.

### Module B: Behavioral Rules (phase-1-behavioral.md)
**Contents:** phase_behavioral_rules
**Size:** ~21 KB
**Purpose:** Phase-specific behavioral guidance — how the AI communicates, tracks decisions, handles glossary candidates, adapts to founder types.
**When loaded:** Always during conversation mode. Referenced (not loaded) during synthesis.

### Module C: Research Protocol (phase-1-research.md)
**Contents:** phase_research_requirements
**Size:** ~22 KB
**Purpose:** The 7 structured research points, engine assignments, triggers, fallbacks, ambient research guidance, and cross-feeding rules.
**When loaded:** Conversation mode. The research FINDINGS (not the protocol) feed into synthesis.

### Module D: Conversation Engine (phase-1-conversation.md)
**Contents:** phase_conversation_structure including all edge cases and edge case composition rules
**Size:** ~58 KB
**Purpose:** The 7 conversation areas, 26 edge cases, all founder-response handling, scope management, and edge case composition rules.
**When loaded:** Conversation mode only.

### Module E: Synthesis & Output (phase-1-synthesis.md)
**Contents:** synthesis_formatting_rules + pre_flight_verification + phase_completion_gate + phase_outputs (including manifest template)
**Size:** ~67 KB
**Purpose:** Everything needed to produce deliverables: D1 spec, GLOSSARY.md, demo-requirements-flag, cross-reference manifest.
**When loaded:** Synthesis mode only. Replaces Modules B/C/D in context.

---

## 2. Module Contract Spec

### 2.1 Shared Schema: D-55 Decision Ledger

The D-55 schema is the primary integration interface. Every module reads or writes to it.

**Defined in:** Module A (Foundation)
**Written to by:** Module D (Conversation Engine) — during conversation
**Read by:** Module B (Behavioral Rules) — for tracking guidance
**Read by:** Module C (Research Protocol) — for logging research-triggered decisions
**Read by:** Module E (Synthesis & Output) — as primary input for D1 production

**Contract:** The D-55 schema in Module A is the single source of truth for ledger format. No other module may redefine the schema. Other modules may reference it by name ("log in D-55 ledger using the schema defined in Foundation") but must not duplicate the schema definition.

### 2.2 Cross-Module References

When Module X references a concept defined in Module Y, the reference format is:

```
<!-- XREF: module-Y → section-name → specific-item -->
```

Example in Conversation Engine:
```
Log the re-platform decision in the D-55 ledger
<!-- XREF: foundation → decision_ledger_contextualization → D-55 schema -->
with binds to Phase 4 (data migration) and Phase 7 (migration build cards).
```

This does NOT mean Module Y must be loaded. It means:
- During CONVERSATION mode: Module A (Foundation) IS loaded, so the D-55 schema is available.
- During SYNTHESIS mode: Module A (Foundation) IS loaded, so the D-55 schema is available.
- The XREF tag is for maintenance — when you update the referenced item, grep for XREFs to find all dependent modules.

### 2.3 Cross-Module Edge Cases

These edge cases modify behavior across multiple modules. Each affected module contains the portion relevant to its scope, with XREFs linking the parts.

| Edge Case | Modules Affected | What Each Module Contains |
|-----------|-----------------|--------------------------|
| Consortium/non-commercial | B (language adaptation), C (research query adaptation), D (conversation flow adaptation), E (D1 section title adaptation, manifest field interpretation) |  B: language reframing rules. C: research 1.1 query adaptation. D: completion gate adaptation, risk category substitution, data governance probing. E: Section 6 title changes, manifest field reinterpretation. |
| White-label platform | D (dual-identity capture, demo distinction), E (manifest white_label fields, D1 Section 1.2 dual-identity spec) | D: conversation probing for vendor vs. deployed identity. E: output spec for dual-identity, manifest fields. |
| Domain outsider | B (front-load research behavioral rule), C (research execution priority), D (conversation sequencing) | B: behavioral adjustment. C: research priority rule. D: sequencing guidance. |
| Already-expanded founder | B (skip expansion behavioral override), D (constraint-first conversation approach) | B: expansion override. D: conversation flow change. |
| Already-expanded + Domain outsider (composition) | B + C + D (specific composition rule) | Composition rule lives in D (Conversation Engine) with XREFs to B and C. |
| PlatformForge adjacent + Research embargo (composition) | C + D (specific composition rule) | Composition rule lives in D with XREF to C. |
| Mid-phase pivot | A (D-55 supersession protocol), D (conversation restart protocol, context compression) | A: ledger supersession rules. D: conversation handling. |
| Story-driven communication | B (extraction behavioral rule), D (story handling protocol) | B: extraction mindset. D: specific protocol steps. |
| B2B2B | D (conversation probing for multi-tier), E (unit economics output spec, demo audiences) | D: probing questions. E: output format for multi-tier economics. |

### 2.4 Module Loading Protocol

**Conversation Mode:**
```
Load: Module A (Foundation) — 26 KB
Load: Module B (Behavioral Rules) — 21 KB
Load: Module C (Research Protocol) — 22 KB
Load: Module D (Conversation Engine) — 58 KB
Load: Master System Prompt — 37 KB
Total: ~164 KB — within 200K effective attention range
```

**Synthesis Mode:**
```
Load: Module A (Foundation) — 26 KB
Load: Module E (Synthesis & Output) — 67 KB
Load: Master System Prompt — 37 KB
Load: Conversation transcript + D-55 ledger — ~25 KB
Total: ~155 KB — within 200K effective attention range
```

**Evaluation Mode (per-module L1):**
```
Load: Module under test — 22-67 KB
Load: Module A (Foundation) — 26 KB (always, for D-55 schema context)
Load: Master System Prompt — 37 KB
Load: Evaluation prompt — ~12 KB
Load: Benchmark scenarios — 25 KB
Total: 122-167 KB — all within Tier 2 200K limit
Maximum output budget: 33-78K tokens — ample for full evaluation
```

---

## 3. Evaluation Architecture

### Layer 1 (Module-Level / Unit Testing)
Each module gets its own L1 evaluation targeting the dimensions it owns:

| Module | Primary Dimensions | Secondary Dimensions |
|--------|-------------------|---------------------|
| A: Foundation | 7 (Decision Ledger), 8 (Progressive Context Loading) | 1 (Structural Compliance) |
| B: Behavioral Rules | 2 (Novice-First Language), 6 (Internal Consistency) | 1 (Structural Compliance) |
| C: Research Protocol | 5 (Research Integration) | 6 (Internal Consistency) |
| D: Conversation Engine | 9 (Edge Case Coverage), 4 (Completion Gate Rigor) | 2 (Novice-First), 6 (Consistency) |
| E: Synthesis & Output | 3 (Spec Precision), 10 (Manifest Quality) | 1 (Structural), 6 (Consistency) |

### Layer 2 (Module-Level / Exploratory)
Same as current L2 but targeted per module. Novel scenarios probe each module's specific edge case boundaries.

### Layer 3 (Integration / NEW)
Tests that modules compose correctly:

**Test 3.1 — Contract Verification:**
For each XREF tag, verify the referenced item exists in the target module and matches the expected schema/format.

**Test 3.2 — Edge Case Span Verification:**
For each cross-module edge case, simulate a founder who triggers it and verify all affected modules produce consistent, non-contradictory output.

**Test 3.3 — Reproducibility (the ultimate test):**
Feed identical simulated conversation transcripts into Module E (Synthesis) twice, independently, and diff the D1 outputs. Divergence points = ambiguities to eliminate. This directly measures improvisation risk.

---

## 4. Migration Plan

### Step 1: Module Contract Finalization (this session)
Review and finalize this architecture document. Assign D-76 status: SETTLED.

### Step 2: Mechanical Split (next session)
Extract each module from the monolith along the documented boundaries. Add XREF tags at every cross-module reference point. Add module headers with version, dependencies, and export declarations. Push each module to artifacts/current/.

### Step 3: Contract Verification (same session as Step 2)
Run Test 3.1 — verify every XREF resolves. This is mechanical and can be scripted.

### Step 4: Module-Level L1 Baseline (1-2 sessions)
Run L1 evaluation on each module individually. These are the new baselines. Each module should score at least as well as its dimensions scored in the monolith clean1 (95.36 overall). If any module scores lower, the split introduced a defect — fix before proceeding.

### Step 5: Integration Testing (1 session)
Run Tests 3.2 and 3.3. Fix any cross-module inconsistencies.

### Step 6: Resume Convergence (ongoing)
Apply remaining L2 clean2 fixes (the 17 findings) to the appropriate modules. Run per-module evaluations. Iterate to targets.

---

## 5. Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| Split introduces subtle breaks (cross-references that silently break) | Test 3.1 is automated XREF verification. Run before any evaluation. |
| Edge cases spanning modules become inconsistent after independent edits | G-9 guardrail. XREF grep before pushing any module edit. Integration test 3.2 after any cross-module edge case change. |
| Module A (Foundation) becomes a bottleneck — every change there affects all modules | Foundation should be the MOST stable module. Changes to D-55 schema require re-evaluation of all modules that reference it. |
| Evaluation prompt needs redesign for module-level testing | Each module gets a tailored evaluation prompt targeting its primary dimensions. Reuse L1 prompt structure but narrow the scope. |
| Total system complexity increases | Module contract spec is the single source of truth for architecture. Keep it updated. |

<!-- EOF: module-architecture.md -->
