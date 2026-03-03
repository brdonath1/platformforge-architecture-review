# CLAUDE.md — PlatformForge Dry Run (Orchestrator)

## Task: Execute D-196 Re-Architecture Step 6 (review_pipeline.py)

Read `step-6-brief.md` in this directory. It contains the complete implementation specification for Step 6.

### Quick Summary

Build `src/review_pipeline.py` with one primary class and module-level helpers:
1. **ReviewPipeline** — 4-layer expert review: L1 compliance → L2/L3/L4 parallel reviews → correction synthesis → founder re-engagement → targeted update
2. **Helper functions** — XML parsing (findings, patches), patch application engine, persona loading/parsing
3. **Constants** — MAX_L1_RETRIES, MAX_REENGAGEMENT_TOPICS, MAX_REENGAGEMENT_EXCHANGES, REENGAGEMENT_COMPLETE_MARKER

Also extend:
- `src/contracts.py` with `ReviewFinding`, `PatchEntry`, `PatchResult`, `ReviewPipelineResult` (Section 6.2)
- `src/run_store.py` with five review artifact methods (Section 6.6)

### Execution Steps

1. Read `step-6-brief.md` completely before writing any code
2. Add `ReviewFinding`, `PatchEntry`, `PatchResult`, `ReviewPipelineResult` to `src/contracts.py` (Section 6.2)
3. Add five review artifact methods to `src/run_store.py` (Section 6.6)
4. Add tests for RunStore extensions to `src/tests/test_run_store.py`
5. Verify existing tests still pass: `python -m pytest src/tests/ -v`
6. Implement `src/review_pipeline.py` following Sections 6.1-6.5 exactly
7. Implement `src/tests/test_review_pipeline.py` following Section 6.9
8. Run all tests: `python -m pytest src/tests/ -v`
9. Run type checking: `python -m mypy src/review_pipeline.py src/contracts.py src/run_store.py --strict`
10. Verify validation criteria (Section 6.10)
11. Push all changes to GitHub

### Constraints

- Haiku 4.5 baseline (D-197) — no Sonnet-specific logic
- Do NOT look at `archive/main_v1_monolith.py` (D-198)
- Imports only from `contracts.py`, `settings.py`, `llm_gateway.py`, `run_store.py` + stdlib
- No print statements — use `logging` module
- Decimal for all money — no float
- All LLM calls via mocked AnthropicGateway in tests — no real API calls
- concurrent.futures.ThreadPoolExecutor for parallel L2/L3/L4 reviews

<!-- EOF: CLAUDE.md -->
