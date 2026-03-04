# Triple-Model Architecture Review — Cross-Model Comparison

---

## Summary

| Metric | Gemini 3.1 Pro | ChatGPT 5.3 Codex | Claude Codex 4.6 |
|---|---|---|---|
| **Total Findings** | 8 | 8 | 30 |
| CRITICAL | 1 | 0 | 2 |
| MAJOR | 6 | 6 | 11 |
| MINOR | 1 | 2 | 12 |
| NOTE | 0 | 0 | 5 |
| **Report Size** | 13.8 KB | 9.3 KB | 52.2 KB |
| **Positive Observations** | 6 | 0 | 10 |
| **Cross-Cutting Concerns** | 2 | 2 | 5 |
| **Ran Tests?** | No | Yes (noted failures) | No (used sub-agents) |
| **Line Counts Provided?** | Approximate | No | Exact per module |

---

## Consensus Findings (All 3 Models Agree)

These are the highest-confidence issues — independently discovered by three different models.

### 1. LLM API Errors Silently Swallowed in Conversation/Synthesis

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-1 | F-4 | F-1 |
| **Severity** | CRITICAL | MAJOR | CRITICAL |
| **Location** | phase_service.py:463-568 | phase_service.py:517-569, 637-649, 826-884 | phase_service.py:516-531 |

**Core issue:** `result.error` is never checked after gateway calls in conversation and synthesis. Failed API calls produce empty text, which is replaced with placeholder strings or empty deliverables. The system continues as if everything succeeded.

**Severity disagreement:** Gemini and Claude rated CRITICAL; ChatGPT rated MAJOR. The CRITICAL rating is well-justified — this corrupts the entire output pipeline silently.

---

### 2. Review Pipeline Suppresses Errors / Silent Pass on API Failure

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-4 | F-6 | F-2 |
| **Severity** | MAJOR | MAJOR | CRITICAL |
| **Location** | review_pipeline.py:753-765 | review_pipeline.py:734-765, 860-868 | review_pipeline.py:734-749, 860-870, 1290-1294 |

**Core issue:** Review layers don't check `result.error`. L1 misclassifies API failure as a parse error. L2/L3/L4 return zero findings on failure, making a defective deliverable appear to pass review.

**Severity disagreement:** Claude escalated to CRITICAL because combined with finding #1 above, the full failure chain is: garbage conversation → garbage synthesis → approved by review → persisted. Gemini and ChatGPT rated MAJOR.

**Coverage note:** Claude additionally identified the `_run_targeted_update()` call site (line 1290) that the other two missed.

---

### 3. Review Notes Never Persisted (Duplicate save_deliverable Bug)

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-2 | F-1 | F-6 |
| **Severity** | MAJOR | MAJOR | MAJOR |
| **Location** | orchestrator.py:264-269 | orchestrator.py:264-269 | orchestrator.py:260-269 |

**Core issue:** When `review_result.review_notes` is present, the code saves `review_result.deliverable_text` instead — the notes are silently lost. All three models identified the same root cause and proposed the same fix (dedicated save method).

**Full consensus** — identical severity, identical location, identical recommendation.

---

## Two-of-Three Agreement (Gemini + ChatGPT, Not Claude)

These findings were caught by both Gemini and ChatGPT but not by Claude. Worth verifying independently.

### 4. Phase Metrics Persisted Before Review Completes

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-3 | F-2 | — |
| **Severity** | MAJOR | MAJOR | Not found |

**Core issue:** `save_phase_metrics()` runs immediately after `run_phase()` but before `review_pipeline.run()`. Review adds cost, time, and may change the deliverable — none of this is reflected in the saved metrics.

**Why Claude may have missed it:** Claude focused heavily on the error-handling gaps and found 27 unique findings. This temporal coupling issue is subtler — it requires tracing the orchestrator's execution order rather than inspecting individual function signatures. Claude's F-8 (cost_usd type mismatch) is tangentially related but addresses a different problem.

---

### 5. Topic ID Loss in Founder Re-engagement ("combined")

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-5 | F-7 | — |
| **Severity** | MAJOR | MAJOR | Not found |

**Core issue:** `_run_founder_reengagement()` collapses all founder responses to `topic_id="combined"`, but `_run_targeted_update()` expects accurate per-topic IDs. The mapping between review gaps and founder answers is broken.

**Why Claude may have missed it:** Claude found F-22 (RoleName.L2 misused for reengagement) and F-11 (_run_targeted_update uses full regeneration) — both in the same code area — but didn't trace the topic_id data flow through the re-engagement pipeline.

---

### 6. Final Publish Pushes Stale PhaseKey.P1 on Empty Run

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-6 | F-3 | — |
| **Severity** | MAJOR | MAJOR | Not found |

**Core issue:** If `completed_keys` is empty (no phases completed), the fallback `completed_keys[-1] if completed_keys else PhaseKey.P1` publishes whatever stale P1 files exist from a prior run.

---

### 7. Tests Bless Broken "combined" Topic ID

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-7 | F-8 | — |
| **Severity** | MINOR | MINOR | Not found |

**Core issue:** Test suite asserts `topic_id == "combined"` and feeds this broken structure into targeted update, locking in the buggy behavior from finding #5.

---

### 8. guide_signaled_ready Is Dead Code

| | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Finding ID** | F-8 | F-5 | — |
| **Severity** | NOTE | MINOR | Not found |

**Core issue:** Flag is set when the guide emits `[READY_FOR_SYNTHESIS]` but never read or acted upon.

---

## Claude-Only Findings (27 Unique)

These were found exclusively by Claude Codex 4.6. Grouped by domain.

### Error Handling & Resilience (4 unique)

| ID | Severity | Finding |
|---|---|---|
| F-7 | MAJOR | `StateRegistry.from_json()` crashes on corrupt or forward-version fact data — no try/except around Pydantic validation |
| F-9 | MAJOR | `_stream_call()` exceptions not converted to `MessageResult` — unexpected response shapes crash the gateway |
| F-10 | MAJOR | `fetch_github_file()` has no error handling — network/auth failures produce opaque urllib traceback |
| F-15 | MINOR | Malformed facts logged at DEBUG level — invisible in production |

### Data Integrity & State Management (5 unique)

| ID | Severity | Finding |
|---|---|---|
| F-3 | MAJOR | Non-atomic file writes risk corrupt deliverables on crash during 6-12 hour runs |
| F-8 | MAJOR | `cost_usd` assigned string instead of Decimal — masked by Pydantic coercion and `type: ignore` |
| F-14 | MINOR | `run_parallel()` None filter could silently shorten result list |
| F-18 | MINOR | `fact_key()` delimiter collision risk with `:` and `.` in LLM-generated values |
| F-23 | MINOR | Empty synthesis saves 0-byte deliverable treated as completed on resume |

### LLM Integration Patterns (6 unique)

| ID | Severity | Finding |
|---|---|---|
| F-4 | MAJOR | `apply_patches()` regex injection — `$` and `\` in LLM content crashes `re.subn()` |
| F-5 | MAJOR | Guide message history drops tool use blocks — conversation history becomes malformed |
| F-16 | MINOR | `parse_correction_patches()` greedy regex strips legitimate XML content |
| F-17 | MINOR | Empty tool results sent for server-side tool continuations |
| F-20 | MINOR | `_strip_synthesis_preamble()` fragile first-heading detection |
| F-21 | MINOR | Markdown fence stripping removes internal fences in fact extraction |

### Architecture & Modularity (2 unique)

| ID | Severity | Finding |
|---|---|---|
| F-11 | MAJOR | `_run_targeted_update()` still uses full document regeneration instead of D-195 diff-based patches |
| F-22 | MINOR | `RoleName.L2` misused for reengagement guide role — cost tracking and policy misattributed |

### Test Coverage & Quality (3 unique)

| ID | Severity | Finding |
|---|---|---|
| F-12 | MAJOR | No test coverage for `MessageResult.error` return path — the actual production failure mode |
| F-13 | MAJOR | No error-path tests for review pipeline failures |
| F-25 | MINOR | Fragile parameter extraction in gateway thinking tests — assertions pass trivially on empty params |

### Performance & Operational Readiness (2 unique)

| ID | Severity | Finding |
|---|---|---|
| F-19 | MINOR | `wall_seconds` undercount in multi-turn tool continuations |
| F-24 | MINOR | Mixed-format templates silently drop numbered sections |

### Security & Configuration (1 unique)

| ID | Severity | Finding |
|---|---|---|
| F-30 | NOTE | Template content injected into prompts without marker sanitization |

### Notes (4 unique)

| ID | Severity | Finding |
|---|---|---|
| F-26 | NOTE | Broad `except Exception` in `run_parallel()` loses error type |
| F-27 | NOTE | `retries_attempted` hardcoded to 0 for non-retryable errors |
| F-28 | NOTE | GitHub publish GET/PUT race condition |
| F-29 | NOTE | No defense against negative token values from API |

---

## Analysis

### What the Consensus Tells Us

The three consensus findings form a **complete silent-failure chain**:

1. Conversation/synthesis ignores API errors → garbage input
2. Review pipeline ignores API errors → garbage passes review
3. Review notes are discarded → human can't catch it either

This is the #1 priority fix. All three models agree, and the combined impact is that an API outage during a multi-hour run can produce convincingly complete but entirely useless deliverables with no error signal.

### What Gemini + ChatGPT Found That Claude Missed

The 5 findings Claude missed share a common trait: they require **tracing execution order across the orchestrator** rather than inspecting individual functions. The metrics-before-review timing issue (#4), the topic_id data flow through re-engagement (#5), and the empty-run publish fallback (#6) are all orchestrator-level sequencing bugs. Claude went deep on individual functions but may have under-indexed on the orchestrator's top-level control flow.

### What Claude Found That Nobody Else Did

Claude's 27 unique findings cluster into two categories:

**High-value unique finds (should fix):**
- F-4: Regex injection in `apply_patches()` — one-line fix, prevents crashes on common content
- F-3: Non-atomic file writes — real risk on 6-12 hour runs
- F-5: Tool use blocks dropped from message history — degrades research-heavy phases
- F-12/F-13: Test suite tests the wrong failure mode — explains why the error-handling bugs weren't caught
- F-11: Targeted update still uses full regeneration — known tech debt

**Lower-priority unique finds (nice to have):**
- F-14 through F-30: Edge cases, code smells, and hardening opportunities

### Report Quality Comparison

| Dimension | Gemini | ChatGPT | Claude |
|---|---|---|---|
| **Depth** | Focused on high-impact issues | Focused on high-impact issues | Exhaustive — went deep into edge cases |
| **Code Citations** | Function names + line ranges | Inline code snippets | Function names + line ranges + code context |
| **Positive Observations** | 6 (good quality) | 0 (missing section) | 10 (detailed, with code references) |
| **Report Structure** | Followed PROMPT.md format | Custom format (by-module, not by-severity) | Followed PROMPT.md format exactly |
| **Actionability** | Clear recommendations | Clear recommendations | Very specific recommendations (e.g., exact lambda fix for F-4) |
| **False Positives** | None detected | None detected | None detected |

### Notable: ChatGPT Format Deviation

ChatGPT organized findings by module rather than by severity as specified in PROMPT.md. It also omitted the Positive Observations section entirely and used a custom "Cross-Module Patterns" section instead of the specified Cross-Cutting Concerns format. The report also ran tests against the repo (finding 41 failures) — useful real-world context but outside the prompt's scope.

### Notable: ChatGPT Ran Tests

ChatGPT actually ran `pytest` against the review repo checkout and reported 41 failures, 202 passed, 14 skipped, 95 errors. This is valuable operational data — the review repo doesn't include `config.json` or the full template fixtures, so it's expected that the suite won't pass as checked out. However, this observation is useful context for anyone attempting to reproduce findings.

---

## Recommended Fix Priority (Synthesized Across All Three Reports)

### Immediate — Pre-Production (consensus-backed)

1. **Add `result.error` checks to all gateway call sites** — All 3 models, highest-impact fix
2. **Fix review notes persistence bug** — All 3 models, copy-paste bug
3. **Fix `apply_patches()` regex injection** — Claude only, but one-line fix preventing crashes

### Short-Term

4. **Move `save_phase_metrics()` after review pipeline** — Gemini + ChatGPT
5. **Preserve topic IDs through re-engagement** — Gemini + ChatGPT
6. **Guard final publish against empty `completed_keys`** — Gemini + ChatGPT
7. **Make file writes atomic** — Claude only, but real risk on long runs
8. **Preserve tool use blocks in conversation history** — Claude only, affects research phases
9. **Add error-path tests for `MessageResult.error`** — Claude only, prevents regression

### Long-Term

10. **Migrate `_run_targeted_update()` to diff-based patches** — Claude only, known tech debt
11. **Unify gateway error model** — Claude only, architectural improvement
12. **Fix remaining MINOR/NOTE items** — Claude's 17 lower-severity findings

<!-- EOF: cross-model-comparison.md -->
