# Review Pipeline Configuration

> Single source of truth for D-188 review pipeline constants, model assignments,
> classification rules, and output formats. Referenced by main.py at runtime.

## Model Assignments Per Layer

All review layers use a single configurable model variable (`REVIEW_MODEL`) for easy graduated escalation (D-192).

| Layer | Role | Max Tokens | Thinking | Notes |
|-------|------|-----------|----------|-------|
| L1 | Compliance checker | 8,192 | none | Mechanical checklist — no reasoning needed |
| L2 | Domain expert review | 32,768 | high | Phase-specific SME — needs deep analysis |
| L3 | Downstream consumer review | 32,768 | high | Next-phase usability — needs cross-phase reasoning |
| L4 | Founder comprehension | 16,384 | high | Accessibility check — needs nuanced judgment |
| Correction | Surgical fix synthesis | 32,768 | high | Must output complete corrected deliverable |

## Graduated Model Escalation (D-192)

| Tier | Model ID | Est. Cost/Run | Est. Runtime | Purpose |
|------|----------|--------------|-------------|---------|
| 1 | claude-haiku-4-5-20251001 | ~$15-25 | 3-5h | Mechanical pipeline validation |
| 2 | claude-sonnet-4-5-20241022 | ~$50-70 | 6-8h | Mid-tier quality check |
| 3 | claude-sonnet-4-6 | ~$100-120 | 10-14h | Near-top quality |
| 4 | claude-sonnet-4-6 (high) | ~$135 | 12-18h | Full quality ceiling |

## Pipeline Constants

```
MAX_REENGAGEMENT_TOPICS = 8     # Cap on should-improve items per phase brief
MAX_L1_RETRIES = 2              # L1 re-check attempts before accepting
MAX_CORRECTION_TOKENS = 32768   # Token limit for correction synthesis
MAX_L1_TOKENS = 8192            # Token limit for L1 compliance check
MAX_L2_TOKENS = 32768           # Token limit for L2 domain expert review
MAX_L3_TOKENS = 32768           # Token limit for L3 downstream consumer review
MAX_L4_TOKENS = 16384           # Token limit for L4 founder comprehension
MAX_REENGAGEMENT_EXCHANGES = 5  # Max exchanges in founder re-engagement conversation
```

## Pipeline Flow (D-189)

Sequential, blocking, no parallelism. Each layer reviews the CORRECTED output from the previous layer.

```
1. Synthesis generates deliverable draft
2. L1 Compliance audit → correct if needed → L1 re-check until clean
3. L2 Domain Expert review → must-fix corrections → L1 re-check
4. L3 Downstream Consumer review → must-fix corrections → L1 re-check
5. L4 Founder Comprehension review → must-fix corrections → L1 re-check
6. Consolidate all should-improve items into interview brief
7. Founder re-engagement (one conversation covering all should-improve topics)
8. Targeted synthesis update from founder's answers
9. Final L1 re-check (compliance only — no full re-review)
10. Consider items → companion review notes document
11. DONE → pristine deliverable + review notes → save → push
```

## Classification Decision Tree

Apply IN ORDER. First "yes" determines category:

1. Is this factually wrong? (incorrect data, contradicts prior deliverable, references nonexistent entity) → **must-fix**
2. Is a required element missing or empty? (template requires X, deliverable lacks X) → **must-fix**
3. Would this block the next phase's work? (downstream team cannot proceed) → **must-fix**
4. Is this thin/vague where founder's knowledge would produce better content? → **should-improve**
5. Is a technical concept unexplained for non-technical reader? → **should-improve**
6. Everything else (suggestions, alternatives, nice-to-haves) → **consider**

## Boundary Rules

- **"Thin but not wrong"** → should-improve (not must-fix)
- **"Missing subsection vs missing section"** → must-fix only if template lists it as required
- **"Could be better"** → consider
- **"Wrong model/framework choice"** → must-fix ONLY if contradicts explicit founder decision; otherwise should-improve
- **"Inconsistency within same deliverable"** → must-fix (factual conflict)
- **"Inconsistency with prior deliverable"** → must-fix (cross-phase contradiction)

## XML Output Format (Required for L2/L3/L4)

```xml
<finding>
  <id>L{layer}-{number}</id>
  <category>must-fix | should-improve | consider</category>
  <section>{deliverable section where the issue lives}</section>
  <issue>{one sentence: what is wrong or missing}</issue>
  <evidence>{quote or reference from deliverable OR template}</evidence>
  <recommendation>{one sentence: specific action to resolve}</recommendation>
</finding>
```

## Interview Brief Format

```xml
<interview_brief phase="{phase_key}">
  <summary>{what was reviewed, how many should-improve items, which layers}</summary>
  <topic_group source="L2 -- Domain Expert ({role_title})">
    <topic id="SI-{phase}-L2-{n}">
      <context>{what the deliverable currently says}</context>
      <gap>{what's missing or thin}</gap>
      <question>{specific question to ask the founder}</question>
    </topic>
  </topic_group>
  <topic_group source="L3 -- Downstream Consumer ({role_title})">
    <topic id="SI-{phase}-L3-{n}">
      <context>{what the deliverable currently says}</context>
      <gap>{why insufficient for next phase}</gap>
      <question>{specific question to ask the founder}</question>
    </topic>
  </topic_group>
  <topic_group source="L4 -- Founder Comprehension">
    <topic id="SI-{phase}-L4-{n}">
      <context>{what the deliverable currently says}</context>
      <gap>{what's unclear for non-technical reader}</gap>
      <question>{specific question to ask the founder}</question>
    </topic>
  </topic_group>
</interview_brief>
```

## Guide Re-engagement Rules

1. One conversation, not three — weave all topics naturally
2. L2 topics first, L4 topics last (deepest technical gaps while founder is fresh)
3. Ask, don't lead — open questions for real answers
4. Max topics per brief: MAX_REENGAGEMENT_TOPICS (default 8)
5. Capture verbatim — no summarizing or editorializing founder's answers

<!-- EOF: review-config.md -->
