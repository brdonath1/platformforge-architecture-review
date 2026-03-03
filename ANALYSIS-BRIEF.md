# PlatformForge Orchestrator — Code Quality Audit

## What This Repository Contains

This is a code quality audit package for the PlatformForge orchestrator — a Python-based AI conversation system that guides non-technical founders through a structured 10-phase methodology to produce comprehensive technical specifications for software platforms.

The orchestrator was re-architected from a single ~190KB monolith into 8 typed modules with comprehensive test coverage. A Layer 1 audit (Claude Opus 4.6 clean-room property inspection) has already been completed, producing 83 findings. All CRITICAL and MAJOR findings have been fixed. This audit seeks independent second-model verification to catch what same-model repetition would miss.

## Repository Structure

```
code/
  src/
    __init__.py
    contracts.py         — Typed data contracts (CanonicalFact, MessageJob, PhaseResult, etc.)
    settings.py          — Configuration, role policies, budget management
    llm_gateway.py       — Anthropic API client with retry, streaming, tool continuation
    template_parser.py   — Phase template parsing (gates, required elements, sections)
    run_store.py         — File-based artifact persistence and run state management
    phase_service.py     — Conversation orchestration, synthesis, research integration
    review_pipeline.py   — 4-layer expert review (L1-L4), correction synthesis, patches
    orchestrator.py      — Top-level run coordinator, GitHub publishing, timing
  tests/
    __init__.py
    test_contracts.py
    test_settings.py
    test_llm_gateway.py
    test_template_parser.py
    test_run_store.py
    test_phase_service.py
    test_review_pipeline.py
    test_orchestrator.py
    test_integration.py
    fixtures/            — Test fixtures (JSON responses, template stubs)
  CLAUDE.md              — Implementation specs and module architecture overview

evidence/
  layer1-consolidated-report.md  — Complete Layer 1 audit findings (83 total)
```

## Current Test Status

- **357 tests passing, 0 failed**
- **mypy --strict: 0 errors in source files**
- 14 tests skipped (known issues, not regressions)

## What We Want You To Do

Perform an independent code quality audit focused on what a same-model (Claude) audit would miss. Different training, different failure modes, different blind spots.

### Focus Areas

1. **Logic errors and subtle bugs** — Off-by-one errors, race conditions, state corruption, incorrect control flow, silent data loss. Not style issues.

2. **Contract violations** — Do modules honor the typed contracts in contracts.py? Are there implicit assumptions between modules that aren't enforced by types?

3. **Error handling gaps** — Unhandled exceptions, swallowed errors, error paths that produce corrupt state rather than clean failures.

4. **Concurrency issues** — ThreadPoolExecutor usage in review_pipeline.py and llm_gateway.py, shared mutable state, thread safety of CostTracker and RunStore.

5. **API integration correctness** — Anthropic API call patterns, streaming handling, tool continuation logic, thinking block serialization. Are there edge cases that would cause silent failures with real API responses?

6. **Test coverage blind spots** — Not missing tests (Layer 1 covered that), but tests that PASS but don't actually validate what they claim to. Mock configurations that mask real bugs. Assertions that are too loose.

### Output Format

- **Severity:** CRITICAL / MAJOR / MINOR / INFO
- For each finding: module, exact location (file + line range), description of the problem, evidence (show the problematic code), recommended fix
- Group findings by module
- End with a **cross-module patterns** section if you find systemic issues

### What To Skip

- Style preferences, naming conventions, docstring formatting, import ordering
- Anything already covered in evidence/layer1-consolidated-report.md — check before reporting duplicates
- Intentional design divergences from briefs (documented in Layer 1 report Section D, Patterns 3-4)

### Reading Order

1. code/CLAUDE.md — Architecture overview (start here)
2. code/src/contracts.py — Data contracts that all modules share
3. code/src/settings.py — Configuration layer
4. code/src/llm_gateway.py — API integration (high complexity)
5. code/src/template_parser.py — Template processing
6. code/src/run_store.py — State persistence
7. code/src/phase_service.py — Core conversation logic (largest module)
8. code/src/review_pipeline.py — Review system (second largest, uses concurrency)
9. code/src/orchestrator.py — Top-level coordinator
10. evidence/layer1-consolidated-report.md — Prior findings (avoid duplicates)
11. Test files as needed for Focus Area 6
