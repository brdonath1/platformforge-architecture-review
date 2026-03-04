#ChatGPT 5.3 Codex Extra High

# PlatformForge Fresh Architecture Audit

**Date:** March 4, 2026  
**Scope:** current checkout only  
**Method:** source review of the live tree plus a `python3 -m pytest -q` run from `code/`  
**Constraint honored:** no git history, no prior audit artifacts, no recovered context

## Findings by Module

### `code/src/orchestrator.py`

#### 1. `MAJOR` — Review notes are generated but never persisted

- **Location:** `code/src/orchestrator.py:264-269`
- **Problem:** when `review_result.review_notes` is present, the code writes the reviewed deliverable again instead of saving the notes text. The notes are lost.
- **Evidence:**

```python
if review_result.review_notes:
    self._store.save_deliverable(
        phase,
        review_result.deliverable_text,
    )
```

- **Why this matters:** the review pipeline returns a distinct `review_notes` artifact, but the orchestrator discards it silently.
- **Recommended fix:** add a dedicated store method and filename for review notes, then persist `review_result.review_notes`.

#### 2. `MAJOR` — Saved phase metrics do not reflect the reviewed phase result

- **Location:** `code/src/orchestrator.py:229-236`, `code/src/orchestrator.py:250-269`, `code/src/phase_service.py:370-389`
- **Problem:** metrics are saved before the review pipeline runs, but review can add cost, elapsed time, and even replace the deliverable. The persisted `PhaseOutcome` is therefore stale.
- **Evidence:**

```python
self._store.save_phase_metrics(
    phase, phase_result.outcome.model_dump(mode="json")
)

review_result = self._review_pipeline.run(
    phase,
    phase_result.deliverable_text,
    template_text,
    prior_deliverables,
)
```

```python
outcome = PhaseOutcome(
    phase=phase,
    status="completed",
    deliverable_chars=len(deliverable_text),
    cost_usd=self._ledger.phase_summary(phase).get(
        "cost_usd", "0"
    ),
    elapsed_seconds=elapsed,
)
```

- **Why this matters:** resume/reporting paths can claim a phase completed with earlier costs and content than what was actually published after review.
- **Recommended fix:** rebuild and persist the final phase metrics after review completes and after the final deliverable text is known.

#### 3. `MAJOR` — Final publish can push stale artifacts when no phase completed

- **Location:** `code/src/orchestrator.py:345-353`
- **Problem:** if the run halts before any phase completes, final publish still executes and falls back to `PhaseKey.P1`.
- **Evidence:**

```python
if pat:
    self._store.publish_to_github(
        completed_keys[-1] if completed_keys else PhaseKey.P1,
        GITHUB_REPO,
        pat,
        label="final",
    )
```

- **Why this matters:** an empty or failed run can republish old files already sitting in `output/`.
- **Recommended fix:** skip final publish when `completed_keys` is empty.

### `code/src/phase_service.py`

#### 4. `MAJOR` — Multiple LLM error paths are ignored and converted into bad successful state

- **Location:** `code/src/phase_service.py:517-569`, `code/src/phase_service.py:637-649`, `code/src/phase_service.py:826-843`, `code/src/phase_service.py:865-884`
- **Problem:** conversation, synthesis, founder-memory generation, and founder-memory update all consume `result.text` without checking `result.error`.
- **Evidence:**

```python
guide_result = self._gateway.run(MessageJob(...))
if guide_result.usage is not None:
    self._ledger.record(phase, guide_result.usage)

guide_text = guide_result.text
if not guide_text:
    guide_text = "[The guide is processing research results and will continue the conversation.]"
```

```python
result = self._gateway.run(MessageJob(...))
if result.usage is not None:
    self._ledger.record(phase, result.usage)

deliverable_text = result.text or ""
```

- **Why this matters:** a transport or API failure can still produce a nominally completed phase with placeholder conversation turns, an empty deliverable, or blank founder memory.
- **Recommended fix:** fail fast on `result.error` in conversation and synthesis, and treat memory helper errors as explicit logged no-ops.

#### 5. `MINOR` — `guide_signaled_ready` is dead state

- **Location:** `code/src/phase_service.py:513`, `code/src/phase_service.py:551-553`
- **Problem:** the conversation loop records that the guide emitted `[READY_FOR_SYNTHESIS]`, but no later control flow uses that signal.
- **Evidence:**

```python
guide_signaled_ready = False
...
if GUIDE_COMPLETE_MARKER in guide_text:
    guide_signaled_ready = True
```

- **Why this matters:** once the guide says the phase is ready, the loop still keeps running until the founder separately emits `[PHASE_COMPLETE]` or the hard exchange cap is reached.
- **Recommended fix:** use the flag to allow one founder follow-up turn, then exit unless the founder explicitly extends the conversation.

### `code/src/review_pipeline.py`

#### 6. `MAJOR` — Reviewer/gateway failures are misclassified as content findings or silently suppressed

- **Location:** `code/src/review_pipeline.py:734-765`, `code/src/review_pipeline.py:860-868`
- **Problem:** `_run_l1_compliance()` and `_run_layer_review()` ignore `result.error`.
- **Evidence:**

```python
result = self._gateway.run(job)
if result.usage:
    self._ledger.record(phase, result.usage)

text = result.text.strip()
try:
    clean = text.replace("```json", "").replace("```", "").strip()
    parsed = json.loads(clean)
except json.JSONDecodeError:
    logger.warning("L1 response not valid JSON — treating as fail")
    return [ReviewFinding(
        id="L1-PARSE",
        category="must-fix",
        section="PARSE_ERROR",
        issue="L1 response was not valid JSON",
    )]
```

```python
result = self._gateway.run(job)
if result.usage:
    self._ledger.record(phase, result.usage)

review_text = result.text.strip()

if not review_text:
    logger.warning("L%d %s: empty response — skipping", layer, layer_name)
    return []
```

- **Why this matters:** transient infrastructure failures can trigger bogus L1 must-fix loops or make L2/L3/L4 findings disappear entirely.
- **Recommended fix:** branch on `result.error` explicitly and propagate a pipeline failure instead of converting the failure into content.

#### 7. `MAJOR` — Founder re-engagement drops topic identity, breaking targeted update mapping

- **Location:** `code/src/review_pipeline.py:1234-1240`, `code/src/review_pipeline.py:1261-1274`
- **Problem:** re-engagement collapses every founder answer to `topic_id="combined"`, but targeted update claims it will update the section for the corresponding interview-brief topic.
- **Evidence:**

```python
for entry in transcript:
    if entry["role"] == "founder":
        responses.append({
            "topic_id": "combined", "response": entry["text"],
        })
```

```python
"    For each founder response, update the deliverable section\n"
"    identified in the corresponding interview brief topic.\n"
```

- **Why this matters:** once topic IDs are discarded, there is no reliable contract connecting a founder answer back to a specific review gap.
- **Recommended fix:** preserve topic IDs through the re-engagement transcript and pass structured per-topic responses into targeted update.

### `code/tests/test_review_pipeline.py`

#### 8. `MINOR` — Tests bless the broken `"combined"` topic contract instead of catching it

- **Location:** `code/tests/test_review_pipeline.py:546-550`, `code/tests/test_review_pipeline.py:565-570`
- **Problem:** tests explicitly assert the collapsed topic ID and feed that same collapsed structure into targeted update.
- **Evidence:**

```python
result = pipeline._run_founder_reengagement(
    PhaseKey.P1, "<interview_brief>test</interview_brief>"
)
assert len(result) >= 1
assert result[0]["topic_id"] == "combined"
```

```python
result = pipeline._run_targeted_update(
    PhaseKey.P1,
    "# Original Doc\n\nOriginal content here.",
    "<brief>test</brief>",
    [{"topic_id": "combined", "response": "my answer"}],
)
```

- **Why this matters:** the suite validates the exact behavior that makes targeted updates lossy.
- **Recommended fix:** require topic IDs from the interview brief to survive re-engagement and reach targeted update unchanged.

## Cross-Module Patterns

### Pattern 1 — LLM error handling is inconsistent

`phase_service._extract_facts()` checks `result.error`, but most other LLM call sites in `phase_service.py` and `review_pipeline.py` do not. The system has one correct pattern and several unsafe call sites.

### Pattern 2 — Persisted artifacts lag behind runtime truth

The pipeline can change deliverables and generate review-only artifacts, but the orchestrator persists phase metrics too early and does not persist review notes at all.

## Verification Notes

I ran:

```bash
python3 -m pytest -q
```

from `code/`.

Observed result in the current checkout:

- `41 failed`
- `202 passed`
- `14 skipped`
- `95 errors`

Important context from the live tree:

- many setup errors come from missing `config.json`
- several template-parser tests fail because only a subset of template fixtures is present

That means the current repository state does **not** support any claim that the suite is green as checked out.
