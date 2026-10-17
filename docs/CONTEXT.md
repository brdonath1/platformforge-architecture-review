# PlatformForge Architecture Review

Status: finished (Brian, October 16, 2026).

## What it is
A triple-model, independent architecture review of the PlatformForge dry-run
orchestrator (a Python app that guides AI models through a 10-phase
conversation methodology to produce platform-planning deliverables).
Gemini 3.1 Pro, Claude Codex 4.6 and ChatGPT 5.3 Codex each reviewed the same
code from the same prompt without seeing each other's output.

## Layout
- `PROMPT.md`: universal analysis prompt, identical for all three models.
- `code/src/`, `code/tests/`: the code under review (read-only input; 8 modules:
  contracts, settings, llm_gateway, template_parser, run_store, phase_service,
  review_pipeline, orchestrator).
- `reports/<model>/architecture-review.md`: the three independent reports.
- `reports/cross-model-comparison.md`: comparison matrix across the three.
- `archive/`: earlier review artifacts, reference only.

## Run / test / deploy
No deployment. The review protocol is in README.md. The code under review is
Python with a pytest-style suite in `code/tests/`; it was not modified here.

## History
This repo had no PRISM, metaswarm, handoff or Claude harness files, so
`docs/history/` does not exist. Git log holds the full history.
