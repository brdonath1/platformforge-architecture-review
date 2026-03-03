# Layer 1 Consolidated Findings Report

**Date:** 2026-03-03
**Scope:** 7 clean-room audit sessions (Steps 0-1, 2, 3, 4, 5, 6, 7)
**Auditor:** Claude Opus 4.6 (synthesis only — no re-audit)

---

## A. Severity Roll-Up

| Report | CRITICAL | MAJOR | MINOR | INFO | Total |
|---|---|---|---|---|---|
| Step 0-1 (contracts + settings) | 0 | 2 | 1 | 4 | 7 |
| Step 2 (llm_gateway) | 0 | 1 | 9 | 0 | 10 |
| Step 3 (template_parser) | 0 | 1 | 5 | 5 | 11 |
| Step 4 (run_store) | 0 | 0 | 3 | 6 | 9 |
| Step 5 (phase_service) | 0 | 0 | 10 | 10 | 20 |
| Step 6 (review_pipeline) | 0 | 0 | 10 | 4 | 14 |
| Step 7 (orchestrator) | 1 | 1 | 5 | 5 | 12 |
| **Totals** | **1** | **5** | **43** | **34** | **83** |

---

## B. All CRITICAL and MAJOR Findings

| ID | Module | Description | Recommended Fix | Estimated Effort |
|---|---|---|---|---|
| **Step7-A4-D1** | orchestrator.py | **CRITICAL: Review notes save bug.** When `review_result.review_notes` is truthy, the code saves `review_result.deliverable_text` (the full deliverable again) instead of the `review_notes` string. Review notes are permanently lost every phase — generated at API cost but never persisted. | Change line 267 to save `review_result.review_notes` via a dedicated store method or with a notes-specific filename. | trivial (< 5 min) |
| **Step01-D1** | test_contracts.py | **MAJOR: Missing test — CanonicalFact rejects invalid value types.** Brief explicitly requires testing rejection of types outside the `FactValue` union (`bytes`, `set`, `None`, `list[int]`). No such test exists. Additionally, Pydantic v2 may silently coerce some types (e.g., `bool→int`, `list[int]→list[str]`), meaning validation itself may be weaker than intended. | Add `test_canonical_fact_rejects_invalid_types` with `bytes`, `set`, `None`. Consider `ConfigDict(strict=True)` if strict rejection is required. | small (5-30 min) |
| **Step01-D2** | test_settings.py | **MAJOR: Missing test — `resolve_role_policy()` raises KeyError for unknown role.** Brief explicitly requires this. `test_unknown_tier_raises` tests unknown *tier* but not unknown *role*. The implementation handles it (`settings.py:133-138`) but it is untested. | Add `test_unknown_role_raises_keyerror` that creates a config with a missing role and verifies the KeyError. | trivial (< 5 min) |
| **Step2-B2-D1** | test_llm_gateway.py | **MAJOR: `test_parallel_concurrency_limit` not implemented.** Brief specifies testing that `max_workers` respects the role's `max_parallel` policy. The logic exists in source (line 133-138) but is untested. | Implement `test_parallel_concurrency_limit` verifying `max_workers = min(len(jobs), max_parallel, 4)`. | small (5-30 min) |
| **Step3-D1** | test_template_parser.py | **MAJOR: Template root path resolution is wrong.** Test resolves to `dry-run/templates_cache/` instead of `dry-run/output/templates_cache/`. `HAS_REAL_TEMPLATES` evaluates to `False` even when real templates are present. 10 integration tests are silently skipped. Phases 3-10 are only tested via synthetic templates that don't exercise Deliverable+Section, standalone bold, or sub_phase_completion_gate patterns. | Change test line 41 to `parent.parent.parent / "output" / "templates_cache"`. | trivial (< 5 min) |
| **Step7-B2-2** | orchestrator.py | **MAJOR: No HTTP error handling in `fetch_github_file`.** `urllib.request.urlopen` raises `urllib.error.HTTPError` on 404/403/500 which propagates unhandled. A single missing template file would crash the entire orchestrator run with an opaque urllib traceback. | Wrap `urlopen` in try/except for `HTTPError`, raise `FileNotFoundError` with descriptive message. | trivial (< 5 min) |

---

## C. MINOR Findings — Triage

### 1. Fix before end-to-end run

These could cause runtime failures or produce incorrect output during a simulated Phase 1-10 run:

| ID | Module | Description |
|---|---|---|
| Step7-B2-1 | orchestrator.py | Final publish executes even when `completed_keys` is empty — falls back to `PhaseKey.P1`, publishes stale/empty content for a phase that never ran. |
| Step5-A-D5 | phase_service.py | `guide_signaled_ready` flag is set but never acted on. Brief says "give founder one more turn" after guide signals `[READY_FOR_SYNTHESIS]`. Current code ignores the flag — conversations may run to `max_exchanges` even when guide is done, burning API cost. |
| Step5-B-D1 | phase_service.py | `cost_usd` default fallback is string `"0"` instead of `Decimal("0")`. Pydantic coerces it at runtime, but the chain is fragile if `phase_summary()` format changes. |

### 2. Fix before founder testing

Edge cases that real users might hit but won't affect a controlled simulation:

| ID | Module | Description |
|---|---|---|
| Step5-C-D2 | test_phase_service.py | No test for gateway error in conversation loop. If `gateway.run()` returns a `MessageResult` with `error` set, conversation continues with empty/garbage text. |
| Step5-C-D3 | test_phase_service.py | No test for gateway error in synthesis path. Same gap as above for the synthesis flow. |
| Step5-C-D1 | test_phase_service.py | No `run_phase` error path test (template not found, gateway failure). |
| Step5-C-D4 | test_phase_service.py | No `_get_founder_memory` gateway error test. |
| Step5-C-D5 | test_phase_service.py | No `_update_founder_memory` edge case tests (empty delta, gateway error). |
| Step6-C2-G1 | test_review_pipeline.py | No gateway error test for `_run_layer_review`. |
| Step6-C2-G2 | test_review_pipeline.py | No max-exchange-limit test for `_run_founder_reengagement`. |
| Step6-C2-G3 | test_review_pipeline.py | No truncation/continuation test for `_run_targeted_update`. |
| Step6-C1-G1 | test_review_pipeline.py | No error path test for `apply_patches` `insert_after` (search_text not found). |
| Step6-C1-G2 | test_review_pipeline.py | No anchor fallback or both-missing test for `apply_patches` `insert_before`. |
| Step6-C1-G3 | test_review_pipeline.py | No anchor-not-found or end-of-document test for `apply_patches` `append_to_section`. |
| Step4-C1-D1 | test_run_store.py | No test for `build_phase_outcome` when only deliverable exists (no conversation, no metrics). |
| Step4-C2-D1 | test_run_store.py | No direct test for `get_by_key()`. |
| Step01-D3 | test_settings.py | Incomplete budget verification — 7 of 9 roles only check `> 0`, not exact values. A config typo would pass undetected. |

### 3. Defer

Cosmetic, dead code, style issues with no functional impact:

| ID | Module | Description |
|---|---|---|
| Step2-A1-D1 | contracts.py | `MessageJob.messages` type is `list[dict[str, object]]` instead of brief's `list[dict[str, str]]`. Functionally superior. |
| Step2-A3-D1 | llm_gateway.py | `RETRYABLE_EXCEPTIONS` not defined as named constant. Functionally equivalent via separate exception handling. |
| Step2-A4-D1 | llm_gateway.py | `_resolve_thinking` takes extra `policy` parameter. Better design than brief. |
| Step2-A4-D2 | llm_gateway.py | `_stream_call` takes extra `job` parameter. Required for complete MessageResult. |
| Step2-A4-D3 | llm_gateway.py | `_handle_tool_continuation` third param is `base_params` instead of `prior_response_blocks`. Better design. |
| Step2-B1-D1 | test_llm_gateway.py | `fixture_error_429.json` missing. Tests construct errors programmatically. Same coverage. |
| Step2-D5-D1 | test_llm_gateway.py | No test for 403 non-retryable. Same code path as 400/401. |
| Step2-D5-D2 | test_llm_gateway.py | No test for 404 non-retryable. Same code path as 400/401. |
| Step2-C4-1 | llm_gateway.py | Default fallback message when messages empty. Could mask caller bugs. |
| Step3-B4-1 | template_parser.py | `_parse_completion_gate` continuation lines: sub-bullet lines starting with `-` break the current item. Unlikely in practice. |
| Step3-B6-D1 | template_parser.py | `_build_required_elements` has unused `phase_val = phase.value` assignment (dead code). |
| Step3-B7-1 | template_parser.py | `_first_sentence` doesn't detect sentence-final period without trailing space. Acceptable for typical gate items. |
| Step3-D2 | template_parser.py | `_extract_tag_content` returns content after unclosed open tag. More permissive than brief. Defensively correct. |
| Step3-D6 | template_parser.py | Duplicate of B6-D1 (dead `phase_val` assignment). |
| Step4-A4-D1 | run_store.py | `phase_summary()` omits `external_cost_usd`. Matches brief, minor asymmetry with `build_report()`. |
| Step5-A-D1 | phase_service.py | `_run_conversation` has extra `adapted_prompt` parameter. Better design — avoids redundant computation. |
| Step5-A-D2 | phase_service.py | `_run_synthesis` has extra `adapted_prompt` parameter. Same rationale. |
| Step5-C-D6 | test_phase_service.py | No full-research-mode test for `_adapt_master_prompt`. Only websearch-only tested. |
| Step6-A6-D1 | review_pipeline.py | `_strip_synthesis_preamble` duplicated locally instead of imported from phase_service. DRY violation. |
| Step6-A8-D1 | review_pipeline.py | `MessageResult` not imported. Code works via implicit typing. |
| Step6-C1-G4 | test_review_pipeline.py | `_parse_persona_file` has minimal test coverage (only happy path). |
| Step6-C1-G5 | test_review_pipeline.py | `load_review_personas` has no happy-path test (only missing-files case). |
| Step7-A4-D2 | orchestrator.py | `_save_phase_artifacts` not extracted as separate method. Inlined in `run()`. |
| Step7-A4-D3 | orchestrator.py | `_build_timing_entry` takes pre-calculated floats instead of raw objects. |
| Step7-B1-2 | orchestrator.py | `conversation_elapsed` naming misleading — actually measures conversation + synthesis. |
| Step7-D2-3 | orchestrator.py | `synthesis_seconds` not tracked separately from `conversation_seconds` in timing waterfall. |

---

## D. Cross-Module Patterns

### Pattern 1: Gateway error responses not checked in callers

**Modules affected:** phase_service.py (conversation loop, synthesis, founder memory), review_pipeline.py (layer review)

`_extract_facts` in phase_service.py correctly checks `result.error`, demonstrating the intended pattern. But `_run_conversation`, `_run_synthesis`, `_get_founder_memory`, and `_update_founder_memory` all call `gateway.run()` without inspecting the error field. If the gateway returns an error, these methods continue with empty or garbage text, potentially producing malformed deliverables or empty memories.

**Recommendation:** Add `if result.error: log + break/return` guards after each `gateway.run()` call. This is a systemic gap — 4+ call sites across 2 modules.

### Pattern 2: Missing error/edge-case test coverage

**Modules affected:** ALL (Steps 0-1 through 7)

Every module has passing happy-path tests but gaps in error-path coverage. The pattern is consistent:
- Step 0-1: Missing negative type rejection tests
- Step 2: Missing concurrency limit test
- Step 4: Missing partial-artifact and `get_by_key` tests
- Step 5: 7 missing error-path tests across conversation, synthesis, memory
- Step 6: 8 missing error/edge-case tests for patch operations and pipeline methods
- Step 7: Missing HTTP error, KeyboardInterrupt, and timing entry tests

**Recommendation:** A dedicated error-path test pass would close these gaps efficiently.

### Pattern 3: Intentional type widening from brief specs

**Modules affected:** contracts.py (MessageJob.messages, PhaseResult.transcript), llm_gateway.py, phase_service.py

Multiple modules widen `dict[str, str]` to `dict[str, object]` for message/transcript dicts. This is consistently applied and justified — transcript entries may contain structured `research` data, tool results can be lists, etc. The brief's `str` type is too narrow for real-world usage.

**Status:** Intentional improvement, not a defect.

### Pattern 4: Private method signatures diverge from briefs

**Modules affected:** llm_gateway.py, phase_service.py

Private methods (`_resolve_thinking`, `_stream_call`, `_run_conversation`, `_run_synthesis`) consistently add parameters not in the brief's signatures. In every case, the added parameter improves the design (e.g., passing pre-computed values to avoid redundant lookups). Since these are private APIs, the divergence has no external impact.

**Status:** Intentional improvement, not a defect.

### Pattern 5: DRY violation in utility functions

**Modules affected:** review_pipeline.py, phase_service.py

`_strip_synthesis_preamble` is defined in both modules. If the preamble-stripping logic needs to change, only one copy may be updated, causing inconsistent behavior between synthesis and targeted-update flows.

**Recommendation:** Import from `phase_service.py` instead of duplicating locally. Single-line fix.

---

## E. End-to-End Run Readiness Assessment

**Is the codebase ready for an end-to-end simulated run?**

**YES, with one precondition.**

The single CRITICAL finding (Step7-A4-D1: review notes save bug) should be fixed first. Without the fix, every phase will silently discard review notes — the "consider" improvement suggestions generated by L2/L3/L4 are computed at API cost but never persisted. The deliverables themselves are unaffected; only the notes are lost. This is a one-line fix.

The 5 MAJOR findings are all either missing tests or non-fatal runtime issues:
- 3 missing tests (Step01-D1, Step01-D2, Step2-B2-D1) — tests don't affect runtime
- 1 test path bug (Step3-D1) — only affects test coverage, not runtime
- 1 HTTP error handling gap (Step7-B2-2) — would only crash if a specific GitHub file is missing; templates are known to exist

None of the MAJOR findings would cause a runtime failure during a controlled simulation where templates are pre-cached and the GitHub API is available.

**Preconditions for clean run:**
1. Fix the review notes save bug (CRITICAL — one-line change)
2. Ensure `GITHUB_PAT` environment variable is set (for template fetching)
3. Ensure `ANTHROPIC_API_KEY` environment variable is set
4. Pre-cache templates via `load_all_phase_templates()` (already done in `main()`)

---

## F. Recommended Fix Plan

| Priority | Module | Finding ID | Fix Description | Effort |
|---|---|---|---|---|
| **P0** | orchestrator.py | Step7-A4-D1 | Fix review notes save: change `review_result.deliverable_text` → `review_result.review_notes` at line 267. Add `save_review_notes` to RunStore if needed. | trivial |
| **P0** | orchestrator.py | Step7-B2-2 | Add try/except for `urllib.error.HTTPError` in `fetch_github_file`, raise `FileNotFoundError` with descriptive message. | trivial |
| **P1** | test_template_parser.py | Step3-D1 | Fix `_REAL_TEMPLATE_ROOT` path: change line 41 to `parent.parent.parent / "output" / "templates_cache"`. Unblocks 10 integration tests. | trivial |
| **P1** | test_contracts.py | Step01-D1 | Add `test_canonical_fact_rejects_invalid_types` with `bytes`, `set`, `None`. | small |
| **P1** | test_settings.py | Step01-D2 | Add `test_unknown_role_raises_keyerror`. | trivial |
| **P1** | test_llm_gateway.py | Step2-B2-D1 | Add `test_parallel_concurrency_limit` verifying max_workers calculation. | small |
| **P1** | phase_service.py | Step5-A-D5 | Act on `guide_signaled_ready` flag: break conversation loop after founder's next response when flag is True. | small |
| **P1** | phase_service.py | Step5-B-D1 | Change `cost_usd` default from `"0"` to `Decimal("0")` at line 384. | trivial |
| **P1** | phase_service.py | Step5-C-D2/D3 | Add `result.error` checks after `gateway.run()` in `_run_conversation` and `_run_synthesis`. | small |
| **P1** | orchestrator.py | Step7-B2-1 | Guard final publish: skip if `completed_keys` is empty. | trivial |
| **P2** | test_phase_service.py | Step5-C-D1/D4/D5 | Add error-path tests for `run_phase`, `_get_founder_memory`, `_update_founder_memory`. | medium |
| **P2** | test_review_pipeline.py | Step6-C1-G1/G2/G3 | Add error-path tests for `apply_patches` edge cases (`insert_after` not found, `insert_before` anchor fallback, `append_to_section` missing anchor). | small |
| **P2** | test_review_pipeline.py | Step6-C2-G2/G3 | Add tests for reengagement max-exchange limit and targeted-update truncation/continuation. | small |
| **P2** | test_run_store.py | Step4-C1-D1/C2-D1 | Add tests for `build_phase_outcome` partial artifacts and `get_by_key` direct call. | small |
| **P2** | test_settings.py | Step01-D3 | Add exact budget value assertions for all 9 roles (not just `> 0`). | small |
| **P2** | review_pipeline.py | Step6-A6-D1 | Import `_strip_synthesis_preamble` from phase_service instead of duplicating locally. | trivial |
| **P2** | review_pipeline.py | Step6-A8-D1 | Add `MessageResult` to the contracts import for explicit type safety. | trivial |
| **P2** | template_parser.py | Step3-B6-D1 | Remove dead assignment `phase_val = phase.value` in `_build_required_elements`. | trivial |

---

*Consolidated from 7 Layer 1 audit reports. No severities were downgraded or upgraded from the original audits. Cross-cutting concerns noted where multiple reports identified the same underlying pattern.*

<!-- EOF: layer1-consolidated-report.md -->
