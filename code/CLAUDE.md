# CLAUDE.md — D-194: Parallelize Review Pipeline + Error Hardening

## CONTEXT

You are modifying `dry-run/main.py` in the `brdonath1/platformforge` repo. The script is a 10-phase AI orchestrator (~3,948 lines, ~169KB). It runs dual-Claude conversations, synthesizes deliverables, and then runs a D-188 4-layer expert review pipeline on each deliverable.

**The problem:** The review pipeline runs L2/L3/L4 sequentially with per-layer correction passes and L1 re-checks between each. This tripled per-phase runtime (45 min review on a 10 min conversation). On Haiku, Phase 1 alone took 54.5 minutes; 45 of those were the review pipeline. Projected total: 12+ hours for 13 phase units.

**The fix:** L2, L3, and L4 are independent reviewers — they all assess the same deliverable without needing each other's output. Run them in parallel, merge all findings, do ONE correction synthesis pass, ONE L1 re-check. Expected time reduction: ~45 min → ~15 min per phase.

---

## TASK 1: D-194 — PARALLELIZE L2/L3/L4 IN REVIEW PIPELINE

### What to change

**File:** `dry-run/main.py`

**Function:** `run_review_pipeline()` (line ~3334)

### Current sequential flow (REPLACE THIS):
```
L1 → correct if needed → L1 re-check loop
L2 review → correct L2 must-fix → L1 re-check
L3 review → correct L3 must-fix → L1 re-check
L4 review → correct L4 must-fix → L1 re-check
Consolidate should-improve → reengagement → targeted update → final L1 re-check
```

### New parallel flow (IMPLEMENT THIS):
```
L1 → correct if needed → L1 re-check loop (UNCHANGED)
[L2 + L3 + L4 in parallel] — all three review the L1-corrected deliverable simultaneously
Merge ALL must-fix findings from L2+L3+L4 into one list
ONE correction synthesis pass on the merged must-fix list
ONE L1 re-check after merged correction
Consolidate should-improve → reengagement → targeted update → final L1 re-check (UNCHANGED)
```

### Implementation details

1. **Add import at top of file:**
   ```python
   import threading
   from concurrent.futures import ThreadPoolExecutor, as_completed
   ```

2. **Make CostTracker thread-safe.** Add a `threading.Lock` to `CostTracker.__init__`:
   ```python
   self._lock = threading.Lock()
   ```
   Wrap ALL mutations in `record_call()` and `record_external_call()` with `with self._lock:`.

3. **Buffer print output per thread.** The three parallel reviews will interleave print output. Two options (pick the simpler one):
   - Option A: Prefix all print lines inside `run_layer_review` with `[L{layer}]` so output is traceable even if interleaved.
   - Option B: Capture prints per thread and flush after all three complete.
   **Preferred: Option A** — simpler, and interleaved output with prefixes is fine for a CLI tool.

4. **Replace Steps 2-4 in `run_review_pipeline` with parallel execution:**
   ```python
   # ── Step 2: L2 + L3 + L4 Parallel Review ──────────────────────────
   print(f"\n  {'─'*50}")
   print(f"  Step 2: L2 + L3 + L4 Parallel Expert Review")
   print(f"  {'─'*50}")

   l2_persona = review_personas.get("l2", {}).get(phase_key, "Senior domain expert reviewer.")
   l3_persona = review_personas.get("l3", {}).get(phase_key, "Downstream phase consumer reviewer.")
   l4_persona = review_personas.get("l4", "Non-technical founder comprehension reviewer.")

   findings_l2, findings_l3, findings_l4 = [], [], []

   with ThreadPoolExecutor(max_workers=3, thread_name_prefix="review") as executor:
       futures = {
           executor.submit(
               run_layer_review, current, template, phase_key, 2,
               l2_persona, prior_deliverables, cost_tracker
           ): "L2",
           executor.submit(
               run_layer_review, current, template, phase_key, 3,
               l3_persona, prior_deliverables, cost_tracker
           ): "L3",
           executor.submit(
               run_layer_review, current, template, phase_key, 4,
               l4_persona, "", cost_tracker
           ): "L4",
       }

       for future in as_completed(futures):
           layer_label = futures[future]
           try:
               result = future.result()
               if layer_label == "L2":
                   findings_l2 = result
               elif layer_label == "L3":
                   findings_l3 = result
               elif layer_label == "L4":
                   findings_l4 = result
           except Exception as e:
               print(f"  ❌ {layer_label} review failed: {type(e).__name__}: {str(e)[:200]}")
               print(f"  ⚠ Continuing with remaining review layers")

   # ── Step 3: Merged Correction Synthesis ────────────────────────────
   print(f"\n  {'─'*50}")
   print(f"  Step 3: Merged Correction Synthesis")
   print(f"  {'─'*50}")

   all_must_fix = (
       [f for f in findings_l2 if f["category"] == "must-fix"] +
       [f for f in findings_l3 if f["category"] == "must-fix"] +
       [f for f in findings_l4 if f["category"] == "must-fix"]
   )

   if all_must_fix:
       # Merge all must-fix findings into ONE correction pass
       all_findings = findings_l2 + findings_l3 + findings_l4
       current = run_correction_synthesis(current, all_findings, phase_key, cost_tracker)

       # ONE L1 re-check after merged corrections
       l1_post_review = run_l1_compliance(current, template, phase_key, cost_tracker)
       if l1_post_review:
           print(f"  ⚠ L1 re-check post-review: {len(l1_post_review)} item(s) — correcting")
           l1_findings = [{
               "id": f"L1-PR-{i+1}", "category": "must-fix",
               "section": item.get("section", "unknown"),
               "issue": item.get("detail", "Missing after review correction"),
               "evidence": "Required by phase template",
               "recommendation": f"Restore missing element: {item.get('detail', '')}",
           } for i, item in enumerate(l1_post_review)]
           current = run_correction_synthesis(current, l1_findings, phase_key, cost_tracker)
   else:
       print(f"  ✅ No must-fix findings across L2/L3/L4 — skipping correction")
   ```

5. **Keep Step 5 (should-improve consolidation + reengagement) UNCHANGED.** It already receives `findings_l2`, `findings_l3`, `findings_l4` as separate lists. No change needed.

6. **Update the pipeline summary** to reflect the new step numbering (Steps 2-4 become Step 2, correction becomes Step 3, should-improve becomes Step 4, final L1 becomes Step 5).

7. **Update the docstring** of `run_review_pipeline` to reflect the new parallel architecture.

### What NOT to change
- `run_layer_review()` — it's self-contained and works as-is in a thread
- `run_l1_compliance()` — still runs on the main thread, before and after parallel review
- `run_correction_synthesis()` — still runs on the main thread, after parallel review completes
- `run_founder_reengagement()` — still sequential, still after corrections
- `build_interview_brief()` — unchanged
- `_build_review_notes()` — unchanged
- `_parse_review_findings()` — unchanged
- The Anthropic client singleton — the SDK handles concurrent requests safely

### Testing checkpoint
After implementing, do a `--dry-run` to confirm no import errors. Then run Phase 1 only (`--phase 1 --max-phases 1` if that flag exists, otherwise we need to add a way to run single phases for testing). Verify:
- L2, L3, L4 all produce findings (check the metric files)
- The pipeline completes in roughly 1/3 the time (~15 min instead of ~45 min)
- Cost report shows all three review layers recorded
- The correction synthesis receives merged findings from all three layers

---

## TASK 2: ERROR HARDENING AUDIT

The script has been accumulating error/retry overhead that turns 4-hour runs into 12-hour runs. Every API call path needs to fail fast or succeed cleanly — no slow limping.

### 2A: Audit every `call_api()` invocation

Search for all calls to `call_api(` in the file. For EACH one, verify:

1. **Thinking mode is correct for the model.** If `REVIEW_MODEL` or any model variable could be Haiku:
   - `enable_thinking=True` is ONLY valid if the model is NOT Haiku, OR if thinking is set to `type: "enabled"` with `budget_tokens` (not `type: "adaptive"`).
   - Current code at line ~2789 passes `enable_thinking=True` and `thinking_effort="high"` to `run_layer_review`. If REVIEW_MODEL is Haiku, `call_api` should handle this gracefully. **Verify that `call_api` already skips thinking for Haiku models** (line ~700 area: `if enable_thinking and "haiku" not in model`). If yes, this is already safe. Document that it's safe and why.

2. **max_tokens does not exceed model limits.** Haiku 4.5 max output is **64,000 tokens** (verified — 200K context window, 64K output ceiling). The S89 fix capping max_tokens to 64K is correct. Check all `MAX_L2_TOKENS`, `MAX_L3_TOKENS`, `MAX_L4_TOKENS`, `MAX_CORRECTION_TOKENS` constants. If any exceed 64,000 and the model is Haiku, they need capping. This is likely already handled but verify.

3. **Beta headers are model-appropriate.** The 1M context header is already skipped for Haiku (line ~660). Confirm no other beta headers are model-inappropriate.

4. **Response parsing handles edge cases.** For each call, verify what happens if:
   - The response is empty or has no text blocks
   - The response is truncated (`stop_reason == "max_tokens"`)
   - The XML parsing fails (malformed findings)
   - The response contains only thinking blocks and no text

### 2B: Retry configuration audit

Check these constants (find them near the top of the file):
- `API_MAX_RETRIES` — should be 3, not higher. Higher just burns time.
- `API_OVERLOADED_MAX_WAIT` — how long does the 529 loop wait? If it's >5 min, that's too long for a single call. A 5-minute 529 wait × 80 calls per phase = catastrophic.
- Retry delays — exponential backoff should max out at 30-60 seconds, not grow unbounded.

**Principle:** Any single API call should either succeed within 2 minutes or fail permanently. If it fails, log the error clearly and move on (or abort the phase). Never retry indefinitely.

### 2C: Add fast-fail for unrecoverable errors

Add a check after each API call: if the response is fundamentally unusable (empty, all thinking, no parseable content), log a clear error and SKIP that step rather than feeding garbage into the next step. Currently, the script may pass empty strings into correction synthesis, which then produces garbage, which then fails L1 re-check, which triggers more corrections — a cascade.

### 2D: Verify Haiku compatibility end-to-end

The S89 handoff mentions fixes were applied for Haiku but never confirmed working. Do a final sweep:
- `enable_thinking` disabled or properly configured for all Haiku calls
- `max_tokens` within Haiku limits for all calls
- 1M beta header skipped for Haiku
- No `type: "adaptive"` thinking anywhere Haiku could be the model

---

## TASK 3: TIMING INSTRUMENTATION

Add granular timing to every major segment so we can identify bottlenecks. This is lightweight — just `time.time()` bookends and data collection.

### 3A: Per-segment timing in `run_phase()`

Add timing around each major segment inside `run_phase()` and include the breakdown in the phase metrics JSON:

```python
metrics = {
    "phase": str(phase_key),
    "status": "COMPLETED",
    "synthesis_attempts": 1,
    "exchanges": len([t for t in transcript if t["role"] == "founder"]),
    "deliverable_chars": len(deliverable),
    "review_model": REVIEW_MODEL,
    "elapsed_seconds": round(elapsed),
    "timestamp": datetime.now().isoformat(),
    # NEW: segment timing breakdown
    "timing": {
        "conversation_seconds": round(conversation_elapsed),
        "synthesis_seconds": round(synthesis_elapsed),
        "review_pipeline_seconds": round(review_elapsed),
    },
}
```

This requires adding `time.time()` calls before and after `run_conversation()`, the synthesis call, and `run_review_pipeline()`.

### 3B: Per-layer timing in `run_review_pipeline()`

Extend the existing `phase-N-review-pipeline.json` to include per-layer timing:

```python
summary = {
    # ... existing fields ...
    "timing": {
        "l1_initial_seconds": round(l1_elapsed),
        "l2_seconds": round(l2_elapsed),
        "l3_seconds": round(l3_elapsed),
        "l4_seconds": round(l4_elapsed),
        "correction_synthesis_seconds": round(correction_elapsed),
        "reengagement_seconds": round(reengagement_elapsed),
        "final_l1_seconds": round(final_l1_elapsed),
    },
}
```

With D-194 parallelization, L2/L3/L4 run concurrently, so record both individual times AND the wall-clock time for the parallel block.

### 3C: Per-call timing and retry count in `call_api()`

Add timing around the entire `call_api()` function and track retry count:

```python
# At the start of call_api:
call_start = time.time()

# At the end (successful return):
call_elapsed = time.time() - call_start
result["call_elapsed_seconds"] = round(call_elapsed, 2)
result["retry_count"] = attempt - 1
return result
```

This makes retry overhead visible in the data without changing how callers work — it's just additional fields in the response dict that callers can optionally use.

### 3D: Run-level timing waterfall

At the end of `main()`, after all phases complete, write a single `timing-waterfall.json` to the metrics directory that consolidates all per-phase and per-segment timings into one file:

```python
{
    "run_start": "2026-03-02T19:00:00",
    "run_end": "2026-03-03T01:30:00",
    "total_elapsed_hours": 6.5,
    "model": "claude-haiku-4-5-20251001",
    "phases": [
        {
            "phase": "1",
            "total_seconds": 1200,
            "conversation_seconds": 180,
            "synthesis_seconds": 120,
            "review_pipeline_seconds": 900,
            "review_detail": {
                "l1_seconds": 60,
                "l2_seconds": 280,
                "l3_seconds": 260,
                "l4_seconds": 240,
                "correction_seconds": 45,
                "reengagement_seconds": 15
            }
        },
        ...
    ]
}
```

This single file tells us exactly where the hours went and which segments to optimize next.

---

## TASK 4: CLEAN OUTPUT BEFORE RUNNING

Before launching any new run:
```bash
cd ~/platformforge
git reset --hard origin/main
git clean -fd dry-run/output/
```

This ensures no stale artifacts from previous runs contaminate results.

---

## EXECUTION ORDER

> **D-194 Tasks 1-3 are DONE** (parallelization, error hardening, timing). D-195 is the new priority.

1. `git pull` to get latest code
2. **Implement D-195** (diff-based correction synthesis) — see addendum at bottom of this file
3. Clean output: `git clean -fd dry-run/output/`
4. Run `python3 main.py --dry-run` to verify no errors
5. Run Phase 1 only as a test — verify:
   - Parallel review fires L2/L3/L4 simultaneously (CONFIRMED working)
   - Correction synthesis outputs small XML patches (NOT full document regeneration)
   - L1 re-check finds FEWER issues after correction (NOT more)
   - No cascading degradation loop
6. If Phase 1 completes cleanly, proceed with full 10-phase run
7. If errors occur, fix and re-test Phase 1 before proceeding
8. Push all changes to GitHub with commit message: `D-195: Diff-based correction synthesis`

---

## CONSTRAINTS

- Do NOT modify the conversation or synthesis logic — only the review pipeline
- Do NOT change model selection logic — that's controlled by config constants
- Do NOT add new dependencies beyond `threading` and `concurrent.futures` (both stdlib)
- Do NOT change the deliverable output format or file structure
- PRESERVE all existing metric recording — the parallel version must produce the same metric files (phase-N-l2-review.json, phase-N-l3-review.json, phase-N-l4-review.json, phase-N-review-pipeline.json)
- Test on Haiku first (cheapest/fastest) before running on higher tiers

<!-- EOF: CLAUDE.md -->

---

# CLAUDE.md — ADDENDUM: D-195 Diff-Based Correction Synthesis

> **Priority: IMPLEMENT BEFORE LAUNCHING ANY FULL RUN.**
> This replaces the current `run_correction_synthesis()` function.

## THE PROBLEM

The current correction synthesis asks the model to regenerate the ENTIRE deliverable (130KB+) with targeted fixes applied. On Haiku, this causes **collateral damage**: fixing 9 items introduces 4+ new problems because the model can't faithfully reproduce 130KB while making surgical edits. Each re-check finds more issues, triggering more regenerations, creating a degradation spiral:

```
L1 finds 9 missing → correction outputs 130KB → L1 finds 13 missing → correction outputs 130KB → L1 finds 22 missing → ...
```

## THE FIX: DIFF-BASED CORRECTION

Instead of regenerating the whole document, ask the model to output **only the corrections as structured patches**. Then apply those patches programmatically in Python. The original deliverable stays intact except for the targeted edits.

## IMPLEMENTATION

### Step 1: Replace the correction prompt

The model should output corrections in this XML format:

```xml
<corrections>
  <patch id="L2-3">
    <action>replace</action>
    <anchor>## 1.3 Target Audience</anchor>
    <search_text>The platform targets golf course operators</search_text>
    <new_text>The platform targets golf course operators and event coordinators using a B2B2C model where the primary customer is the golf course operator (B2B) who serves end consumers (B2C) through the platform</new_text>
  </patch>
  <patch id="L3-1">
    <action>insert_after</action>
    <anchor>## 5.7 Risk Assessment</anchor>
    <search_text><!-- end of risk table --></search_text>
    <new_text>

### 5.8 Regulatory Compliance Risk

PCI-DSS compliance is required for payment processing. The platform must implement tokenized payment handling through Stripe to avoid storing card data directly.

</new_text>
  </patch>
  <patch id="L4-5">
    <action>replace</action>
    <anchor>## 3.2 Permission Matrix</anchor>
    <search_text>RBAC controls with hierarchical permission inheritance enable granular access management across organizational boundaries</search_text>
    <new_text>Each team member gets specific permissions based on their role. A Senior Concierge can do everything a Team Member can, plus approve refunds and edit schedules. The Operator (founder) can do everything.</new_text>
  </patch>
</corrections>
```

**Action types:**
- `replace` — find `search_text` near `anchor`, replace with `new_text`
- `insert_after` — find `search_text` near `anchor`, insert `new_text` after it
- `insert_before` — find `search_text` near `anchor`, insert `new_text` before it
- `append_to_section` — find section by `anchor` heading, append `new_text` at end of section (before next heading)

### Step 2: New correction prompt

```python
system = (
    "You are a precise document patch generator. For each finding, output a "
    "targeted correction patch. Do NOT output the full document. Output ONLY "
    "the <corrections> XML block with patches for each must-fix finding.\n\n"
    "RULES:\n"
    "1. Each patch targets ONE specific location in the document.\n"
    "2. <anchor> must be an EXACT markdown heading from the document (e.g., '## 1.3 Target Audience').\n"
    "3. <search_text> must be a UNIQUE phrase (10-50 words) that appears EXACTLY once "
    "   in the document near the anchor. Copy it character-for-character.\n"
    "4. <new_text> is the replacement content. Include surrounding context if needed "
    "   for the replacement to read naturally.\n"
    "5. For missing sections/content, use action='append_to_section' or 'insert_after'.\n"
    "6. For incorrect content, use action='replace'.\n"
    "7. Keep patches minimal — change only what the finding requires.\n"
    "8. If a finding requires adding a NEW section that doesn't exist, use "
    "   action='insert_before' with the anchor set to the heading AFTER where "
    "   the new section should appear."
)

user_prompt = (
    "<correction_request>\n"
    f"  <deliverable>\n{deliverable}\n  </deliverable>\n"
    f"  <findings>\n{findings_xml}  </findings>\n"
    "  <instruction>\n"
    "    For each finding, output ONE patch in the <corrections> block.\n"
    "    Do NOT output the full document. Output ONLY the corrections XML.\n"
    "  </instruction>\n"
    "</correction_request>"
)
```

### Step 3: Python patch applicator

```python
import re

def apply_patches(deliverable: str, patches_xml: str) -> tuple[str, list[dict]]:
    """
    Apply correction patches to deliverable.
    Returns (patched_deliverable, application_log).
    
    Each log entry: {id, action, status, detail}
    Status: 'applied', 'skipped_not_found', 'skipped_ambiguous'
    """
    result = deliverable
    log = []
    
    # Parse patches from XML
    patches = parse_correction_patches(patches_xml)
    
    for patch in patches:
        pid = patch["id"]
        action = patch["action"]
        search_text = patch.get("search_text", "")
        new_text = patch.get("new_text", "")
        anchor = patch.get("anchor", "")
        
        # Verify anchor exists
        if anchor and anchor not in result:
            log.append({"id": pid, "action": action, "status": "skipped_anchor_not_found",
                        "detail": f"Anchor not found: {anchor[:80]}"})
            continue
        
        if action == "replace":
            if not search_text:
                log.append({"id": pid, "action": action, "status": "skipped_no_search",
                            "detail": "No search_text provided"})
                continue
            
            count = result.count(search_text)
            if count == 0:
                # Try fuzzy: strip extra whitespace and retry
                normalized_search = " ".join(search_text.split())
                normalized_result = " ".join(result.split())
                if normalized_search in normalized_result:
                    # Apply on original with flexible whitespace matching
                    pattern = re.escape(search_text)
                    pattern = re.sub(r'\\ +', r'\\s+', pattern)  # flexible whitespace
                    result, n = re.subn(pattern, new_text, result, count=1)
                    if n:
                        log.append({"id": pid, "action": action, "status": "applied_fuzzy",
                                    "detail": "Applied with whitespace normalization"})
                        continue
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": f"search_text not found: {search_text[:80]}"})
                continue
            elif count > 1:
                # Ambiguous — try to use anchor to narrow scope
                if anchor:
                    anchor_pos = result.find(anchor)
                    # Find the occurrence closest to the anchor
                    search_pos = result.find(search_text, max(0, anchor_pos - 2000))
                    if search_pos != -1 and search_pos < anchor_pos + 5000:
                        result = result[:search_pos] + new_text + result[search_pos + len(search_text):]
                        log.append({"id": pid, "action": action, "status": "applied_anchored",
                                    "detail": f"Resolved ambiguity using anchor (found {count} matches)"})
                        continue
                log.append({"id": pid, "action": action, "status": "skipped_ambiguous",
                            "detail": f"search_text appears {count} times"})
                continue
            else:
                result = result.replace(search_text, new_text, 1)
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Replaced {len(search_text)} chars with {len(new_text)} chars"})
        
        elif action == "insert_after":
            if search_text and search_text in result:
                pos = result.find(search_text) + len(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Inserted {len(new_text)} chars after search_text"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": f"search_text not found for insert_after"})
        
        elif action == "insert_before":
            if search_text and search_text in result:
                pos = result.find(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Inserted {len(new_text)} chars before search_text"})
            elif anchor and anchor in result:
                pos = result.find(anchor)
                result = result[:pos] + new_text + "\n\n" + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied_via_anchor",
                            "detail": f"Inserted before anchor heading"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": "Neither search_text nor anchor found"})
        
        elif action == "append_to_section":
            if anchor and anchor in result:
                anchor_pos = result.find(anchor)
                # Find next heading of same or higher level
                heading_level = len(anchor) - len(anchor.lstrip('#'))
                pattern = r'\n#{1,' + str(heading_level) + r'} [^\n]+'
                next_heading = re.search(pattern, result[anchor_pos + len(anchor):])
                if next_heading:
                    insert_pos = anchor_pos + len(anchor) + next_heading.start()
                else:
                    insert_pos = len(result)  # End of document
                result = result[:insert_pos] + "\n\n" + new_text + "\n" + result[insert_pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Appended {len(new_text)} chars to section"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_anchor_not_found",
                            "detail": f"Section anchor not found: {anchor[:80]}"})
        
        else:
            log.append({"id": pid, "action": action, "status": "skipped_unknown_action",
                        "detail": f"Unknown action type: {action}"})
    
    return result, log


def parse_correction_patches(xml_text: str) -> list[dict]:
    """Parse <corrections> XML into list of patch dicts."""
    patches = []
    patch_blocks = re.findall(r'<patch\s+id="([^"]*)">(.*?)</patch>', xml_text, re.DOTALL)
    
    for pid, block in patch_blocks:
        patch = {"id": pid}
        for field in ["action", "anchor", "search_text", "new_text"]:
            match = re.search(rf'<{field}>(.*?)</{field}>', block, re.DOTALL)
            patch[field] = match.group(1).strip() if match else ""
        patches.append(patch)
    
    return patches
```

### Step 4: Replace `run_correction_synthesis()` 

Replace the ENTIRE function body. The new function:

1. Builds findings XML (same as before)
2. Sends the diff-based prompt (NOT the full-regeneration prompt)
3. Parses the patches from the response
4. Applies patches programmatically via `apply_patches()`
5. Logs which patches succeeded/failed
6. Returns the patched deliverable

**Critical:** The model receives the full deliverable in the prompt (it needs to read it to generate accurate patches), but it only OUTPUTS the small corrections XML. This means:
- Input tokens: same as before (deliverable + findings)
- Output tokens: ~2-5KB instead of ~130KB (massive reduction)
- No collateral damage because the original document is never regenerated
- Failed patches are skipped, not catastrophic

### Step 5: Update the sanity check

The old sanity check (`len(corrected) < len(deliverable) * 0.5`) was designed for full-document regeneration. Replace with:

```python
applied_count = sum(1 for entry in log if "applied" in entry["status"])
skipped_count = sum(1 for entry in log if "skipped" in entry["status"])

print(f"  ✅ Patches: {applied_count} applied, {skipped_count} skipped")
for entry in log:
    symbol = "✓" if "applied" in entry["status"] else "✗"
    print(f"     {symbol} {entry['id']}: {entry['status']} — {entry['detail'][:80]}")

if applied_count == 0 and len(patches) > 0:
    print(f"  ⚠ No patches could be applied — keeping original deliverable")
    return deliverable
```

### Step 6: Remove the truncation/continuation logic

The old code had handling for `stop_reason == "max_tokens"` where it would request a continuation of the regenerated document. This is no longer needed because the output is a small corrections XML block, not a 130KB document. **Delete the continuation logic entirely.**

## CONSTRAINTS

- Do NOT change `run_layer_review()`, `run_l1_compliance()`, or any other function
- Do NOT change the findings format — patches are generated FROM the same findings list
- The function signature stays identical: `run_correction_synthesis(deliverable, findings, phase_key, cost_tracker) -> str`
- Callers don't change — they still receive a corrected deliverable string
- If ALL patches fail, return the original deliverable unchanged (never return garbage)
- Log all patch application results to console AND to a metrics file

## TESTING

After implementing, the Phase 1 test should show:
- Correction synthesis outputting small XML (~2-5KB) instead of regenerating 130KB
- Patch application log showing which patches succeeded
- L1 re-check finding FEWER issues than the initial L1 (not MORE)
- No cascading degradation loop

<!-- EOF: D-195 ADDENDUM -->
