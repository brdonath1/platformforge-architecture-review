# PlatformForge Orchestrator — Architecture Review

## Your Assignment

You are performing an independent architecture review of the PlatformForge dry-run orchestrator. This is a Python application that guides AI models through a structured 10-phase conversation methodology, producing technical deliverables for software platform planning.

**Read every file in `code/src/` and `code/tests/` completely before beginning your analysis.** Do not skim. Do not sample. Read each file top-to-bottom. Your analysis must demonstrate familiarity with the entire codebase — findings that could only come from reading specific functions, specific error paths, and specific test cases.

The codebase consists of 8 production modules and their corresponding test files:

| Module | Role |
|---|---|
| `contracts.py` | Data models, enums, and type definitions |
| `settings.py` | Configuration and environment management |
| `llm_gateway.py` | LLM API client (Anthropic, Perplexity, Grok) |
| `template_parser.py` | Markdown template loading and variable injection |
| `run_store.py` | Persistence layer for run state and artifacts |
| `phase_service.py` | Phase execution logic (conversation, synthesis, research) |
| `review_pipeline.py` | Multi-gate quality validation of deliverables |
| `orchestrator.py` | Top-level run coordinator across all 10 phases |

---

## Analysis Domains

Analyze the codebase across all seven domains below. Every domain must appear in your report. Do not skip domains even if you find no issues — state that explicitly.

### Domain 1: Error Handling & Resilience

Inspect every function that can fail — LLM calls, file I/O, network requests, JSON parsing, template rendering.

- Are all error paths handled explicitly, or do some rely on implicit propagation?
- When an LLM call returns an error in its response payload (e.g., `result.error`, API-level errors vs HTTP-level errors), is that checked before the result is used?
- Are retry mechanisms present where appropriate? Do they have backoff? Are there retry limits?
- What happens when a phase fails mid-execution? Is state left inconsistent?
- Are exceptions caught at appropriate granularity (specific vs broad `except Exception`)?
- Do error messages include enough context (which phase, which sub-phase, which call) for debugging?

### Domain 2: Data Integrity & State Management

Trace the lifecycle of a run from start to completion.

- Is run state always consistent? Are there windows where a crash would leave state corrupted or unrecoverable?
- Are artifacts persisted in the correct order relative to validation? (i.e., does the system ever persist something before confirming it passed review?)
- When state is updated across multiple steps, are those updates atomic or can partial updates occur?
- Are identifiers (run IDs, phase IDs, topic IDs) generated, passed, and stored correctly through the full pipeline?
- Is there any place where data is silently dropped, overwritten, or collapsed in a way that loses information?

### Domain 3: LLM Integration Patterns

Examine how the system interacts with language model APIs.

- Are prompts constructed safely (no injection vectors from user-provided content)?
- Is the system robust to unexpected LLM response formats (missing fields, extra fields, truncated responses)?
- Are token limits and context windows managed explicitly?
- Are model-specific behaviors handled (different API shapes for Anthropic vs Perplexity vs Grok)?
- Is there appropriate separation between the LLM transport layer and business logic?
- Are costs tracked or bounded? Is there protection against runaway API spend?

### Domain 4: Architecture & Modularity

Evaluate the structural quality of the codebase.

- Are module boundaries clean? Does each module have a single clear responsibility?
- Are there circular dependencies or inappropriate coupling between modules?
- Is the dependency direction correct (higher-level modules depend on lower-level, not vice versa)?
- Are interfaces (function signatures, class APIs) stable and well-defined?
- Is there duplicated logic that should be consolidated?
- Are there God functions (>100 lines) or God classes that do too much?

### Domain 5: Test Coverage & Quality

Evaluate the test suite's effectiveness, not just its existence.

- Do tests cover the critical paths identified in Domains 1-4?
- Are failure modes tested (not just happy paths)?
- Are edge cases covered (empty inputs, maximum sizes, malformed data)?
- Do tests actually assert meaningful properties, or are they shallow (just checking "no exception thrown")?
- Are mocks used appropriately — do they accurately represent the real dependencies?
- Are there integration tests that verify cross-module behavior?
- Are there gaps where untested code contains complex logic?

### Domain 6: Security & Configuration

Review how secrets, configuration, and external inputs are handled.

- Are API keys and secrets handled safely (not logged, not exposed in error messages)?
- Is configuration validated at startup or lazily (and what are the consequences of invalid config)?
- Are there any path traversal, injection, or other input-handling vulnerabilities?
- Are file system operations (reads, writes) safely scoped?

### Domain 7: Performance & Operational Readiness

Assess production-readiness concerns.

- Are there obvious performance bottlenecks (synchronous waits where async would help, unnecessary re-reads)?
- Is logging sufficient for production debugging without being excessive?
- Are there resource leaks (unclosed files, connections, abandoned async tasks)?
- Is the system observable — could an operator diagnose a stuck or failing run from logs alone?

---

## Report Format

Structure your report with the following sections in this exact order. Use the exact section headers shown.

### Section 1: Executive Summary

- Total finding count by severity
- Top 3 most impactful findings (one sentence each)
- Overall architectural assessment (2-3 sentences)

### Section 2: Codebase Overview

- Brief description of what each module does based on your reading (1-2 sentences per module)
- Key architectural patterns you observed
- Total lines of production code and test code (approximate)

### Section 3: Findings

Each finding must follow this exact template:

```
#### [SEVERITY] F-{N}: {Title}

**Domain:** {Domain name}
**Location:** `{filename}`, lines {start}-{end} (or function name if line numbers unavailable)
**Description:** {What the issue is — be specific, reference actual code}
**Impact:** {What could go wrong in practice}
**Recommendation:** {Concrete fix, not vague guidance}
```

Number findings sequentially starting at F-1. Group findings by severity (all CRITICALs first, then MAJORs, then MINORs, then NOTEs).

### Section 4: Positive Observations

List 5-10 things the codebase does well. Be specific — cite actual patterns, actual modules, actual design choices. This section is not optional.

### Section 5: Cross-Cutting Concerns

Patterns that span multiple domains or modules. These are architectural observations that don't fit neatly into a single finding but represent systemic characteristics (positive or negative) of the codebase.

### Section 6: Recommendations Summary

Prioritized list of actions. Group by:
- **Immediate (pre-production):** Must fix before real users touch this
- **Short-term:** Should fix within the next development cycle
- **Long-term:** Improvements for maturity, not blockers

---

## Severity Definitions

Apply these strictly. When in doubt, use the higher severity.

| Severity | Definition | Criteria |
|---|---|---|
| **CRITICAL** | System failure or data loss likely in normal operation | Will definitely cause problems for real users — not hypothetical. Crashes, data corruption, silent data loss on the happy path. |
| **MAJOR** | Significant issue that will cause problems under realistic conditions | Error paths that lose context, state inconsistencies that occur under non-exotic failure modes, missing validation on untrusted input. |
| **MINOR** | Correctness or quality issue with limited practical impact | Code smell, minor duplication, suboptimal error messages, missing edge case handling for rare scenarios. |
| **NOTE** | Observation or improvement suggestion | Not a bug or risk — a recommendation for maintainability, readability, or future-proofing. |

---

## Rules of Engagement

1. **Be exhaustive.** A shorter report is not a better report. If the codebase has 30 findings, report 30 findings. Do not summarize, consolidate, or "pick the top ones." Every issue you identify must appear in the report.

2. **Cite code.** Every finding must reference specific files and specific code — function names, variable names, the actual logic that is problematic. A finding without a code reference is not a finding.

3. **No false positives.** Do not report speculative issues. If you are not confident something is actually a problem, do not include it as a finding. You may mention uncertain observations in Cross-Cutting Concerns.

4. **No prior knowledge.** Analyze only the code in this repository. Do not reference any external documentation, prior reviews, or assumptions about what the system "should" do beyond what the code itself reveals.

5. **Be concrete in recommendations.** "Improve error handling" is not a recommendation. "Check `result.error` before accessing `result.content` in `phase_service.py::_run_conversation_turn()`" is a recommendation.

6. **Preserve nuance.** If something is both good and problematic, say both. If a pattern works well in one module but is implemented poorly in another, note the contrast.

7. **Test the tests.** The test suite is part of the codebase. If tests have quality issues, those are findings too.

Save your complete report as `architecture-review.md` in the designated output directory.
