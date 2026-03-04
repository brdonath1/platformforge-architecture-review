# PlatformForge Architecture Review

Triple-model independent architecture review of the PlatformForge dry-run orchestrator.

## Structure

- `PROMPT.md` — Universal analysis prompt (identical input for all three models)
- `code/` — Production source and test suite (read-only input, do not modify)
- `reports/` — Independent analysis outputs
  - `gemini-3.1-pro/` — Google Gemini 3.1 Pro analysis
  - `claude-codex-4.6/` — Anthropic Claude Codex 4.6 (max reasoning) analysis
  - `chatgpt-5.3-codex/` — OpenAI ChatGPT 5.3 Codex analysis
- `archive/` — Previous review artifacts (for reference only, not part of current review)

## Protocol

1. Each model reads `PROMPT.md` and all files under `code/`
2. Each model produces `architecture-review.md` in its designated `reports/` subdirectory
3. No model sees another model's output
4. Reports follow identical structure defined in `PROMPT.md`

## Running a Review

Point each tool at this repository and instruct it to:

> Read PROMPT.md for your instructions. Read all files under code/src/ and code/tests/ completely. Produce your report as reports/{model-name}/architecture-review.md following the exact format specified in PROMPT.md.

<!-- EOF: README.md -->
