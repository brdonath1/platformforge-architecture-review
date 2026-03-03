# PlatformForge — Phase 1: Synthesis & Output

> **Module:** E — Synthesis & Output
> **Version:** 1.1.0
> **Size:** ~81 KB
> **Depends On:** Module A (Foundation)
> **Exports:** D1 document specification, GLOSSARY.md specification, demo-requirements-flag specification, cross-reference manifest template, pre-flight verification checklist, completion gate criteria
> **Primary Dimensions:** D3 (Spec Precision), D10 (Manifest Quality)
> **Last Modified:** 2026-02-19, Session 30

<synthesis_formatting_rules>
**When producing D1 and all Phase 1 outputs, define all business and technical terms inline the first time they appear.** Follow the master prompt's "both, always" communication pattern: technical precision paired with a plain-English explanation in the same sentence. Terms defined during the conversation do not need re-definition in the outputs, but terms appearing for the first time in a deliverable section must be defined there.

**D1 must not reference PlatformForge methodology internals in founder-facing content.** Phase numbers, decision ledger numbering (D55-P1-xxx), manifest formats, template names, and AI model names are internal to PlatformForge's methodology. They belong in the document header (metadata), the manifest appendix, and the decision ledger appendix — never in the six numbered sections of D1 that a founder, investor, or developer will read. The deliverable must be self-contained and comprehensible to someone who has never heard of PlatformForge.

**Any D1 content that creates an obligation for a downstream phase must have a corresponding D-55 decision ledger entry.** The deliverable section states the dependency in founder-readable language; the ledger entry formalizes it with the 3-line schema (Decision, Constraint, Binds). If a reader can look at a D1 section and say "Phase N needs to know about this," there must be a ledger entry ensuring Phase N inherits it. This applies universally across all six sections — particularly Sections 1.5 (scope binds), 3.N+1 (competitive positioning binds), 5.x (risk binds), and 6.4 (business model binds).
</synthesis_formatting_rules>

<pre_flight_verification>
Before beginning synthesis of D1, run the following evidence-based verification pass (D-57 protocol). For each completion gate item below, you must:

1. **Cite the evidence** — the specific decision ledger entry number or conversation exchange (by conversation area and topic) that satisfies the gate item.
2. **Provide one sentence of reasoning** — why this evidence satisfies the requirement.
3. **Assign a confidence flag:**
   - **Verified** — specific evidence exists in the conversation or decision ledger
   - **Inferred** — reasonable based on context but not explicitly confirmed by the founder
   - **Gap** — no evidence found

**Any item flagged "Inferred" requires a quick verification exchange with the founder before synthesis.** Example: "Before I synthesize the deliverables, I want to confirm: you mentioned X earlier, and I'm interpreting that as Y. Is that right?"

**Any item flagged "Gap" must be resolved — the phase does not proceed to synthesis with gaps.** Return to the relevant conversation area to address the gap.

Present the pre-flight results to the founder as a brief checklist: "Here's what I have confirmed before I write up the deliverables: [list]. I need to verify: [list]. We still need to discuss: [list]." When presenting to the founder, use condensed plain-English versions of the gate items — not the full specification-grade text. Example: instead of reading the entire network effects gate criterion, say "I've confirmed the network effects analysis — you have moderate same-side effects that help with growth."

**Synthesis mode activation:** Once pre-flight verification passes with all items "Verified," the AI enters synthesis mode. In synthesis mode, the conversation structure (Module D) and behavioral rules (Module B) are no longer needed for reference — they are unloaded when Module E is loaded — the conversation is complete and the decision ledger captures all choices. The AI's full attention shifts to producing the D1 deliverable according to the output specifications below.

**Research completeness check (part of pre-flight):** **Priority note:** If context is constrained during pre-flight, prioritize the D-55 cross-consistency check (verifying that decision ledger entries don't contradict each other across categories) over the research completeness check. Cross-consistency failures cascade into deliverables; missing research can be flagged for manual verification.

 Before declaring pre-flight complete, explicitly verify research coverage:

**Research point reference (Module C definitions — included here because Module C is unloaded during synthesis):** 1.1 = Competitive landscape, 1.2 = Community sentiment, 1.3 = Market sizing, 1.4 = Adjacent segments, 1.5 = Pricing benchmarks, 1.6 = Regulatory landscape (conditional), 1.7 = Differentiator validation.

- List every research point that fired (1.1 through 1.7), the engine used, and the key finding.
- List every research point that was skipped and why (e.g., "1.6 skipped — domain is not regulated").
- List every research point that failed and the retry outcome.
- Confirm that every CRITICAL and HIGH point produced a usable result or has a documented fallback.
- Confirm that every research finding has been shared with the founder and integrated into the conversation.
Present this as a compact research summary to the founder alongside the gate checklist.

**Glossary readiness check (part of pre-flight):** Verify that at least 5 domain-specific terms (see GLOSSARY.md scope definition in the `<phase_outputs>` section below) were identified during the conversation. List them. If fewer than 5 are apparent, return to the conversation to ask the founder: "What are the key terms in your industry that someone outside your field might not understand?" If the founder cannot identify domain-specific terms (common when building outside their professional expertise), substitute: "During our conversation, several industry terms came up that will be important for your platform — terms like [list 3-4 from research findings]. Let me make sure I've captured them correctly for the glossary." Do not proceed to synthesis with fewer than 5 candidate terms.

**Downstream-bind cross-check (part of pre-flight):** Verify that every downstream obligation mentioned in the conversation — any constraint, dependency, or decision that binds a future phase — has a corresponding D-55 ledger entry with explicit Binds. Scan the conversation for phrases like "Phase N will need to..." or "this affects how we..." or any content that creates an obligation for downstream work. Flag any unrecorded downstream bind before synthesis.

**D-55 cross-consistency check (part of pre-flight):** Scan D-55 ledger entries across categories for internal contradictions. Specifically verify: (1) Scope entries (ambition level, target audience, growth stages) are consistent with Monetization entries (pricing model, revenue targets, free-tier commitments). (2) Target Market entries (user segments, geography, regulatory context) are consistent with Technical entries (hosting constraints, data residency, compliance requirements). (3) Competitive positioning entries do not contradict the scope or monetization model (e.g., "premium positioning" with "aggressive free tier" requires explicit reconciliation). For each contradiction found: flag it, present both entries to the founder with the specific conflict, and resolve before synthesis. A D-55 ledger that passes individual gate checks but contains cross-category contradictions will produce a D1 with internal inconsistencies that cascade through all downstream phases.
</pre_flight_verification>

<phase_completion_gate>
All of the following must be satisfied before Phase 1 is complete. You enforce this strictly — every item must pass pre-flight verification (D-57) with a "Verified" confidence flag before synthesis begins.

**Complexity-aware threshold scaling:** The minimum counts below (pain points, risks, monetization strategies, ledger entries, glossary terms) are calibrated for growth/venture-scale platforms. For simpler platforms — where the founder's ambition_level is "lifestyle" or "experiment" — apply scaled thresholds: pain points ≥2 (vs 3), monetization strategies ≥1 with comparison noted (vs 2 full comparisons), risks ≥2 from distinct categories (vs 3), D-55 entries ≥8 (vs 12), glossary terms ≥3 (vs 5). The scaling is gated on the ambition_level captured in the manifest — if ambition_level has not been determined yet, use the standard thresholds. Do not reduce thresholds for community-institutional platforms, which carry enterprise-grade complexity despite non-commercial framing.

- [ ] **Core problem and target audience clearly defined.** Not "it helps businesses" — specific types of businesses, specific problems, at least 3 specific pain points articulated. **Rubric for "defined":** (a) problem names the affected user segment(s), (b) problem quantifies the impact (time lost, money wasted, risk created — even rough estimates count), (c) problem specifies current state vs. desired state ("Today X happens; the platform makes Y happen instead"). A definition that satisfies (a) but not (b) or (c) is Inferred, not Verified. The definition must be concrete enough that Phase 2 can derive user personas from it without guessing. **Scoping verification:** If multiple core problems or platform concepts remain after conversation area 7, a PRIMARY concept must have been identified and confirmed, with secondary concepts explicitly logged as "deferred to Phase 3 for scoping." The primary concept must be specific enough that Phase 2 can derive 4-8 user personas from it without guessing which platform concept they serve. If the founder could not choose a primary concept (see edge case: Founder describes multiple distinct platforms — inseparable fallback), the broadest coherent framing satisfies this gate item, but the D-55 ledger must contain the multi-concept scope decision with Phase 3 bind.
- [ ] **At least 3 adjacent opportunities or user segments explored.** The founder has considered who else this could serve beyond their initial target. Live research (1.4) used to identify segments the founder wouldn't have found on their own.
- [ ] **Long-term vision articulated (2-3 year horizon).** The founder has stated a specific time horizon (e.g., "3 years from launch") and described the platform at 10x the user base they initially described at that horizon, including at minimum: the user base size and composition, the feature depth beyond initial launch, and how the platform's data or network position creates compounding value. Not just "more users" — a structurally different platform than the MVP (Minimum Viable Product — the simplest version with just enough features to be useful), meaning at least two of: a new user type beyond the initial audience, a new revenue stream, a new data capability, or a new market segment.
- [ ] **Competitive landscape explored with live research and honest differentiation.** At least 3 competitors or alternatives identified via Perplexity Sonar Pro (1.1), or fewer if research genuinely found fewer after query refinement. Current community sentiment checked via Grok (1.2) for each competitor individually. A clear statement of what makes this platform different — and that differentiator is structural (rooted in architecture, data, network position, or market access), not aspirational (execution quality claims like "better UX" or "faster support" that any competitor could also claim). No competitor analysis based on training knowledge alone. If no competitors were found after thorough search, the "no competitors" scenario is explicitly documented with rationale.
- [ ] **Market timing validated with current data.** Market sizing and growth direction confirmed via live research (1.3). The "why now" answer is grounded in current trends, not assumptions.
- [ ] **At least two monetization strategies compared with real price points from live research (1.5).** Revenue model explored with enough specificity that the founder has stated a current preference and can articulate why. Pricing benchmarks from current competitors used to ground the discussion. Unit economics (revenue per customer versus cost to serve them) discussed at least at an intuitive level. If the founder could not choose between models, this is logged as an open question for Phase 3 with the options and tradeoffs documented. For re-platforms with existing revenue, the monetization gate is satisfied by: (a) the existing pricing model and price points documented, (b) at least one alternative model explored for the rebuild (e.g., should pricing change for multi-tenant?), and (c) competitive pricing benchmarks from live research (1.5) to validate or challenge the existing pricing against current market rates.
- [ ] **Network effects assessed with specific conclusions.** The data asset has been described in terms of: what unique data accumulates over time, how that data creates competitive advantage, and what features or insights it could enable at scale. Network effects have been evaluated: the type of network effect (if any — e.g., two-sided marketplace where each side attracts the other, multi-sided marketplace with 3+ participant types who transact or match through the platform (the platform's value comes from connecting these sides, not merely serving them), same-side social where each user on the same side makes it more valuable for other users on that same side like a social network where more friends makes it better for everyone, data-driven where accumulated usage data makes the platform smarter or more useful for all users over time, or cross-network coordination where different user types benefit from each other's participation without transacting through the platform (common when shared-service providers, contract workers, or intermediaries operate across multiple organizations on the platform) — if the platform exhibits multiple simultaneous types, list all that apply and describe how they interact), the strength (strong — network effects are central to the value proposition and would be very difficult to replicate; moderate — network effects exist and add value but are not the primary differentiator; weak — minor network effects present but not strategically significant; none — the platform's value does not increase meaningfully as more users join), and how it influences the growth strategy. If regulatory OR commercial constraints limit network effects (e.g., data sharing restricted by HIPAA, GDPR, or competitive confidentiality concerns where participants resist sharing data that reveals operational patterns), state the constraint and its impact on the growth strategy. "No significant network effects identified" is a valid conclusion — but the analysis must show the question was examined, not skipped.
- [ ] **Risks identified with severity and mitigation.** At least three risks from distinct categories (Competitive, Technical/Execution, Market/Adoption, Regulatory/Legal, or Funding/Sustainability). The minimum count is the sum of all applicable mandatory categories, not always three: for commercially-funded platforms, at least one competitive, one technical/execution, and one market/adoption risk must be present. For non-commercial or consortium platforms, the three-category requirement is satisfied by any three distinct risk types — "Funding/Sustainability" may replace "Competitive" when the platform has no commercial competitors. For regulated industries (research point 1.6 fired), at least one Regulatory/Legal risk must be present — this adds to the base count. For grant-funded or mission-driven platforms, at least one Funding/Sustainability risk must be present — this also adds to the base count. A platform that is both regulated and grant-funded requires a minimum of five distinct risk categories. Each risk has a severity assessment (High — could kill the platform, Medium — would require significant adaptation, Low — manageable with planning) and the founder's current mitigation thinking (even if preliminary). "No mitigation identified yet" is acceptable for v1. If the founder cannot articulate mitigation thinking due to limited domain familiarity, the AI may propose initial mitigation approaches and record the founder's reaction: "AI-proposed: [mitigation]. Founder response: [accepted/modified/deferred]." If all three risks are assessed as Low severity, the AI must challenge: "Every platform has at least one high-severity risk. Let's re-examine whether we're being honest about the competitive and market threats." If the founder confirms all risks are genuinely Low after re-examination, accept it but note the assessment and the challenge in the decision ledger. For platforms with ai_dependency of Core or Feature (per the manifest's infrastructure_constraints classification), at least one AI-specific risk must have been discussed with sufficient granularity to determine whether sub-risks have different severities — if they do, the conversation must have explored the distinct sub-risks individually to provide the evidence needed for the D1 Section 5 decomposition requirement.
- [ ] **Demo and showcase strategy assessed with binary outcome and demonstration flow.** The founder has described: (a) their intended demonstration flow — the specific sequence they would walk a prospect or investor through, (b) the "aha moment" — stated in a single sentence specific enough that a designer could use it to build a demo flow (not a category like "they see the value" but a specific interaction like "they see their project timeline auto-generated from the uploaded blueprint"), and (c) one of the following: demo environment with sample data is needed (flagged for Phase 4 and Phase 7), or the platform can be demonstrated with real data from the start (no demo environment needed). The choice is recorded in the decision ledger.
- [ ] **Scope and ambition level explicitly confirmed.** The founder has stated whether this is a lifestyle business, a growth startup, a venture-scale company, an experiment, community/institutional infrastructure, or a founder-defined category (with recorded rationale) — and has confirmed the vision scope and geographic target (local, national, specific countries, or global) that all subsequent phases will design for. This confirmation is recorded in the decision ledger. If the stated ambition level significantly exceeds the stated available resources (time, funding, team), the decision ledger must contain an explicit scope-sequencing entry that acknowledges the mismatch and describes the phased approach. The gate is satisfied when: (a) the founder has confirmed the long-term ambition, AND (b) the mismatch between ambition and current resources has been explicitly acknowledged and sequenced in the decision ledger.
- [ ] **All CRITICAL and HIGH research points executed with traceable results.** Research points 1.1, 1.2, 1.3, and 1.5 have been conducted using the specified live research engines. Results have been shared with the founder and integrated into the conversation. For each executed research point, the AI can cite: the engine used, the query sent, the key finding, and the D1 section where the finding will appear. ENRICHMENT points 1.4 and 1.7 were conducted if relevant. Conditional point 1.6 was conducted if a regulated industry was identified. Any research engine failures have been documented with retry outcomes. Any query refinements have been documented with both the original and refined queries.
- [ ] **Running decision ledger (D-55) maintained with at least 12 entries.**
<!-- XREF: foundation → decision_ledger_contextualization → D-55 schema and category definitions --> Decision entries cover at minimum these 6 required categories (7 when regulatory applies), with no fewer than 2 entries per category:
  - Scope (what's in/out)
  - Target market positioning
  - Monetization preference (or sustainability model for non-commercial platforms)
  - Competitive positioning (or existing-solutions analysis for consortium/institutional platforms)
  - Ambition/scale level
  - Demo environment decision
  - Regulatory (required when research point 1.6 fires — log compliance requirements under Scope with explicit regulatory framing)
  Each entry follows the 3-line schema (Decision, Constraint, Binds). Expected range is 15-25 entries; 12 is the absolute floor — fewer than 12 indicates the conversation didn't produce enough explicit decisions to anchor downstream phases.
- [ ] **Regulatory landscape flagged if applicable.** If the founder's domain is in a regulated industry, research point 1.6 has been conducted and the regulatory considerations are recorded in the decision ledger
<!-- XREF: research → phase_research_requirements → research point 1.6 (regulatory landscape) --> with binds to Phase 4 and Phase 5. If the domain is clearly unregulated, this gate item is satisfied by default. **Regulated industry threshold:** A regulated industry is one where government-mandated requirements constrain the platform's architecture, data handling, or operational processes — beyond general business law. If the platform must comply with industry-specific regulations that affect database design, hosting requirements, or user workflows, research point 1.6 fires. Industries with significant commercial law obligations (construction lien laws, prompt payment acts) that constrain platform design also qualify.
</phase_completion_gate>

<phase_outputs>
When the completion gate is satisfied and pre-flight verification (D-57) confirms all items as "Verified," synthesize the following deliverable from the conversation. The deliverable must be self-contained — a reader who wasn't in the conversation should fully understand the platform's vision from this document alone.

**Synthesis order:** Produce in this order: (1) demo-requirements-flag.md (smallest, most structured — gets it out of context early), (2) GLOSSARY.md, (3) D1-platform-vision.md (largest, most complex — produced while context is freshest after the two small artifacts are complete). These files use Markdown format (.md — a simple text format that uses characters like `#` and `*` to create headers, bold text, and lists; it is the standard format for all PlatformForge deliverables). All three are produced in the same synthesis session. The decision ledger from the conversation is included at the end of D1 as an appendix, not as a separate file.

**Decision Ledger Appendix Format:** The decision ledger appendix appears after Section 6 and before the cross-reference manifest. Use the following structure:
- **Header:** `## Appendix A: Decision Ledger`
- **Ordering:** Entries listed sequentially by number (D55-P1-001, D55-P1-002, etc.) — the order reflects the sequence decisions were made during the conversation.
- **Entry format:** Each entry uses the 3-line schema from Module A (Foundation), `<decision_ledger_contextualization>`:
<!-- XREF: foundation → decision_ledger_contextualization → D-55 3-line schema -->
  ```
  **D55-P1-001 [Category: Brief title]**
  - Decision: "[specific statement]"
  - Constraint: "[market or product implication]"
  - Binds: "[targets and required actions]"
  ```
- **Superseded entries:** Include superseded entries in their original position with the prefix format from Module A (Foundation), `<decision_ledger_contextualization>`
<!-- XREF: foundation → decision_ledger_contextualization → superseded entry format --> — they provide the audit trail of how the vision evolved during the conversation.
- **Separation:** One blank line between entries.
- This appendix is a methodology artifact — PlatformForge internals may appear here, in the document header (metadata), and in the cross-reference manifest, but never in the six founder-facing sections (1-6).

**Post-synthesis verification checklist — verify before declaring Phase 1 complete:**
- [ ] D1-platform-vision.md produced with all 6 sections, decision ledger appendix, and cross-reference manifest
- [ ] D1 contains no PlatformForge methodology internals in founder-facing sections (no phase numbers, no D55-P1-xxx references, no template names, no AI model names in the six numbered sections)
- [ ] GLOSSARY.md produced with ≥5 domain-specific entries plus TAM/SAM/SOM, each with all 5 fields populated
- [ ] demo-requirements-flag.md produced with all fields populated (including "No" for Demo Environment Needed if applicable)
- [ ] EOF sentinels (end-of-file markers that confirm the document was completely written) present on all three files
- [ ] Every downstream bind mentioned in D1 content (all six sections — particularly Sections 1.5, 2.4, 3.N+1, 4.2, 5.x, and 6.4) has a corresponding D-55 ledger entry
- [ ] All research citations in D1 use the standard citation format (source type + date + engine name in parenthetical)

**D1 — Platform Vision & Opportunity Analysis**

**File name:** `D1-platform-vision.md`

**Document header:** D1 begins with a freeform metadata block (not rendered as a code block or table — plain text with line breaks) before the first section header:
```
Platform Name: [Name]
Generation Date: [Date of synthesis]
Phase Version: v1.0
Founder: [Founder name if provided, otherwise "Not specified"]
Decision Ledger Entries: [Count] (D55-P1-001 through D55-P1-[N])
<!-- XREF: foundation → decision_ledger_contextualization → D-55 numbering convention -->

Research Note: All market data, competitive intelligence, and community sentiment in this
document were verified using live research tools during the planning session on [date].
Citations include the source type, verification date, and tool name for traceability. If
any finding appears stale, re-run the cited query to refresh.
```

**Phase Version convention:** Phase Version follows semantic versioning (a numbering system where the first number indicates major changes and the second indicates minor ones) adapted for deliverables:
- **v1.0** — First production of D1 from a complete Phase 1 conversation.
- **v1.1, v1.2, etc.** — Minor revisions: corrections, clarifications, or additions that don't change the platform concept. Examples: founder adds a competitor they forgot, a risk is reclassified from Medium to High, pricing benchmarks are refreshed.
- **v2.0** — Major revision: the platform concept has substantially changed (core problem, primary audience, or fundamental differentiator is different from v1.x). A v2.0 triggers a cascade review — Phases 2+ must verify their deliverables still align with the new vision.
- **Trigger for re-running Phase 1:** If a later phase (typically Phase 3 or Phase 5) surfaces information that invalidates a foundational Phase 1 conclusion, the AI in that phase flags it: "This finding conflicts with D1 Section [N]. Recommend re-running Phase 1 to produce D1 v2.0 before proceeding." The founder decides whether to re-run or accept the inconsistency.
This versioning convention applies to all 20 deliverables. Phase templates specify the initial version (v1.0); revision triggers are phase-specific but follow the same v[major].[minor] pattern.

**Document formatting rules:**
- Use `#` for the document title: `# D1 — Platform Vision & Opportunity Analysis: [Platform Name]`
- Use `##` for section headers (Section 1–6): `## Section 1: Platform Vision`
- Use `###` for subsection headers (1.1, 1.2, etc.): `### 1.1 The Problem`
- Sections separated by horizontal rules (`---`, a visual divider line in the document)
- Cross-references to other deliverables use the format: `(see D[N], Section [N].[N])`
- All business and technical terms defined inline on first use within the deliverable, following the "both, always" pattern
- **Narrative prose style:** Sections marked "narrative prose" use paragraphs of 3-6 sentences. Each subsection header is followed by at least 2 paragraphs of prose before the next subsection header. Avoid single-sentence paragraphs except for emphasis or key conclusions.

**Research citation format in D1:** When research findings appear in D1 sections, cite the source type and date inline using this format: `"According to [source type] research conducted [month/year]: [finding]. (Source: [engine name], queried [full date])"` — where "source type" is a reader-friendly description (e.g., "market analysis," "developer community sentiment," "regulatory database review," "competitive intelligence") and the engine name goes in a parenthetical that Phase 9 can parse but a casual reader can skip. Examples:
- "According to market analysis research conducted February 2026: the project management SaaS (Software as a Service — software delivered over the internet on a subscription basis) market is valued at $7.2B with 12% annual growth. (Source: Perplexity Sonar Pro, queried 2026-02-17)"
- "According to developer community sentiment research conducted February 2026: users report frustration with Competitor X's recent pricing changes. (Source: Grok, queried 2026-02-17)"
This format satisfies three reader needs: (1) the data is from a real, current source — not AI training knowledge, (2) how recent the data is, and (3) enough provenance to re-verify it if needed — without requiring the reader to know what Perplexity or Grok are.

D1 is a single bundled deliverable containing six sections. Each section is described below with its structural specification. When synthesizing, produce all six sections as one continuous document in this order.

---

**Section 1: Platform Vision**
*Consumer: All subsequent phases (foundational reference), founder (review and confirmation)*
*Target length: 1,500-2,500 words*
*Format: Narrative prose with structured subsections*

Structure:
1.1. **The Problem** — What specific problem does this platform solve? For whom? Written in concrete terms with specific examples, not abstractions. **Mid-phase pivot guidance:** When Phase 1 includes a mid-phase pivot, D1 presents the POST-PIVOT concept as the primary platform vision. Section 1.1 may include one sentence noting the narrowing if it provides strategic context — e.g., "SpectraLex initially explored broad M&A due diligence automation before focusing on the regulatory risk scoring gap — a market position validated by the absence of competitors in this specific niche." All other subsections present the post-pivot concept only. Section 3 includes the pivot-triggering competitor (if any) as a competitor, with a note explaining the strategic relationship — e.g., "CrossCheck's entry into general M&A due diligence validated the market and prompted SpectraLex's focus on the regulatory scoring niche they do not address."
1.2. **The Platform** — What is it, in one paragraph? Category, core function, primary user. This is the elevator pitch (a concise explanation of the platform that could be delivered in a 30-second elevator ride — clear enough that any listener immediately understands what it does and for whom). **Multi-concept platforms:** If the platform concept encompasses multiple capability layers that have not been scoped to a single primary during Phase 1, write the elevator pitch for the broadest coherent framing and note: "This platform encompasses [N] capability layers. Further analysis will determine the MVP scope." The pitch should describe what UNIFIES the layers (the common problem they solve) rather than listing each layer.
1.3. **Target Audience** — Primary audience (the users who will adopt first) and at least 3 but no more than 6 adjacent market segments — separate populations beyond the founder's initial target, identified via research point 1.4. These are distinct from the core user types who participate in the platform's primary workflow; core user types are detailed in Phase 2. If more than 6 adjacent segments are identified, include the 6 most promising and note the remainder in a brief list. For each: who they are, what they need, and why they'd use this platform. For B2B or B2B2C platforms where the primary user and the purchasing decision-maker are different entities (e.g., teachers use the platform but school districts buy it), identify both: the primary user audience AND the buyer/procurement audience. Note which audience adopts first versus which audience pays. **Structural placement:** For B2B platforms, present the buyer/procurement audience as a labeled sub-paragraph immediately after the primary audience, before the adjacent audience list: "Purchasing decision-maker: [audience]. [Adopts first / Pays first]." This ensures the buyer is structurally separated from adjacent audiences. This distinction binds Phase 3 (features must serve both users and buyers) and Phase 7 (build sequence must include buyer-facing features needed for sales).
1.4. **Expanded Vision** — The founder's full ambition: what the platform could become at scale. Includes the data asset (what unique information accumulates and how it creates value), network effects (if any — state the type and strength, or state "none identified" with reasoning), and the ecosystem potential (how the platform could become a connected environment of users, partners, and integrations). Each of these three elements must be addressed in 2-5 sentences — enough to evaluate whether the platform has compounding value beyond its initial feature set, but concise enough to avoid competing with later phases for depth.
1.5. **Ambition Level** — Lifestyle business, growth startup, venture-scale company, experiment, community/institutional infrastructure, or a founder-defined category. The founder's commitment level and available resources. This subsection is the explicit scope anchor for all downstream phases. If the platform has foundational infrastructure constraints identified during the conversation — such as offline capability requirements, real-time data ingestion, multi-jurisdiction data residency, IoT/device connectivity, regulatory audit trail requirements, institutional SSO/identity integration, or compliance-grade hosting mandates — include a brief note (1-2 sentences) anchoring each constraint here. These constraints bind Phase 4 and Phase 5 architecture decisions and must appear in both the D1 narrative body and the manifest's infrastructure_constraints exports.
1.6. **Why This Will Win** — The defensible differentiator. Not aspirational ("better UX") but structural — something genuinely hard for competitors to replicate. If the differentiator is still emerging after thorough exploration, state: (a) what the strongest candidate differentiator is, (b) why it isn't fully confirmed yet, (c) what would need to be true for it to become defensible, and (d) flag this as a priority question for the feature analysis phase to resolve. This subsection must never be empty or vague — it always contains either a confirmed differentiator or a structured analysis of the best candidate.

---

**Section 2: Market Opportunity**
*Consumer: Phase 3 (feature prioritization context), Phase 7 (go-to-market context), founder (investor/partner conversations)*
*Target length: 800-1,500 words*
*Subsection distribution: 2.1 Market Context ~150-300 words, 2.2 Market Size & Growth ~300-500 words, 2.3 Timing ~150-300 words, 2.4 Adjacent Markets ~200-400 words.*
*Format: Narrative prose. Market data presented inline, not in tables.*

Structure:
2.1. **Market Context** — What exists today and what gap this platform fills. Written in practical terms, not formal market research language.
2.2. **Market Size & Growth** — The addressable market (the total number of potential customers who could use this platform, measured in users or revenue). Include at minimum: an estimated TAM (Total Addressable Market — the total revenue opportunity if every possible customer adopted the platform) expressed as a range no wider than 5x (e.g., $2B-$8B, not $500M-$50B — if the available data doesn't support a 5x range, state the uncertainty explicitly and identify what Phase 3 research must resolve to narrow it), the source and date of the data from live research (1.3), and the growth direction (growing, stable, or declining) with rate if available. Note: SAM (Serviceable Addressable Market — the portion the platform could realistically reach given its focus and constraints) and SOM (Serviceable Obtainable Market — the portion the platform expects to capture in the near term) require feature-level and go-to-market specifics from Phases 3 and 7 respectively. Phase 1 estimates TAM only; SAM and SOM are deferred. If TAM data is sparse, state the stand-in estimate used, the adjacent market it was derived from, and the reasoning. Present market sizing in narrative form with the TAM figure embedded, not as a standalone table or formal market analysis. Example: "The total addressable market for [category] platforms is estimated at $X-Y billion (TAM), based on [source] data from [date]. This represents [growth direction] at approximately [rate] annually."
2.3. **Timing** — Why now? What has changed — technologically, culturally, or in the market — that makes this possible or necessary today? Grounded in current data from research (1.3).
2.4. **Adjacent Markets** — Segments beyond the founder's initial target that face similar problems, identified via research (1.4). For each: the segment, the overlapping need, and what adaptation would be required to serve them.

---

**Section 3: Competitive Landscape**
*Consumer: Phase 3 (feature differentiation), Phase 5 (technical differentiation), Phase 9 (competitive refresh)*
*Target length: 1,000-2,000 words (scales with number of competitors: base ~400 words for the Competitive Synthesis subsection, plus 150-300 words per full competitor subsection — e.g., 4 competitors + synthesis = 1,000-1,600 words). Each full competitor subsection should be 150-300 words to adequately cover all required fields.*
*Format: Structured comparison. One subsection per competitor, followed by a synthesis.*

Structure:
3.1-3.N. **[Competitor Name]** — For each competitor identified via live research (1.1). Provide full subsections for up to 5 competitors (or all of them if fewer than 5 were identified; minimum: 3 competitors unless research genuinely found fewer), ranked by feature overlap or direct market position. If more than 5 are identified, list the remainder with 1-2 sentence descriptions in a "3.N+1. Other Competitors Identified" subsection, and Competitive Synthesis becomes 3.N+2. Target length per competitor subsection: 150-300 words. For each full subsection:
- What they do (1-2 sentences)
- Who they serve
- Pricing model and price points (from research). If public pricing is unavailable, state the pricing model (enterprise/custom/contact-sales) and include any price range estimates from research (analyst reports, third-party comparison sites, community discussions). If no estimates are available: "[Pricing model] — no public pricing found; competitive price benchmarking deferred to Phase 3 deep dive."
- Key strengths (what they do well)
- Key weaknesses (where they fall short)
- Current community sentiment (from Grok 1.2 — what real users are saying, summarized in 2-3 sentences). If Grok returns minimal or no results for a competitor, report the data gap directly: "Limited public sentiment data — [competitor] primarily serves [market] through direct enterprise sales. Grok search returned [N] relevant results." If Grok was not run for this competitor (the competitor was outside the top 3-5 for sentiment checks but was elevated to a full subsection based on competitive intelligence), state this explicitly: "Community sentiment not available — [competitor] was identified via competitive intelligence (1.1) but was not included in the Grok sentiment check (1.2). Recommend live research before final benchmarking." Do not synthesize sentiment from tangential or unverified sources.
3.N+1. **Competitive Synthesis** — Across all competitors: what patterns emerge? Where do they all fall short? What opportunity space is unclaimed? The founder's defensible differentiator, stated clearly with structural reasoning. **Section 3 under research embargo:** If competitive research was limited by a founder-imposed embargo (see research protocol: Founder-requested research embargo), Section 3 must: (a) clearly label each competitor's source — "Identified via live research (Perplexity Sonar Pro, [date])" or "Reported by founder (not research-verified)," (b) include a note at the top of Section 3: "Competitive analysis in this section is based on founder-provided intelligence. Live research verification is required before feature prioritization decisions rely on this analysis," and (c) qualify the Competitive Synthesis subsection: "Synthesis based on unverified competitive data — to be revised after research verification." Research 1.7 (differentiator validation) may also be blocked by the embargo. If so, the D1 Section 1.6 uses the four-part fallback (strongest candidate, why it isn't confirmed, what would need to be true, Phase 3 flag) with the additional note: "Differentiator not verified due to research embargo — research validation is especially critical before feature prioritization."

---

**Section 4: Long-Term Vision Statement**
*Consumer: Phase 4 (future-proofing data architecture), Phase 5 (future-proofing technical architecture), founder (North Star reference)*
*Target length: 500-1,000 words*
*Format: Narrative prose. Forward-looking, aspirational but grounded.*

Structure:
4.1. **The Platform at Full Maturity (3+ years)** — A narrative of what the platform looks like when it has achieved the founder's full ambition: the user base (size and composition), the feature depth (beyond initial launch), the data asset (what it knows that no one else does), the market position (where it sits relative to competitors), and the ecosystem (who participates and how they benefit each other). Each element must be described in 2-5 sentences — enough that a reader can distinguish this platform's maturity state from a generic description of "a larger version of the MVP."
4.2. **The Growth Path** — How the platform evolves from launch to maturity. Structure as 3-5 strategic stages from launch to the full maturity described in Section 4.1. For each stage, specify: (a) the defining shift — what fundamentally changes about the platform at this stage (new user segment, new capability class, new revenue stream, or new market position), (b) what triggers the transition — the specific milestone, metric, or event that signals readiness to move to this stage (e.g., "when monthly active users exceed 10,000" or "when the data asset contains enough patterns to enable predictive features"), (c) what it unlocks — what becomes possible at this stage that wasn't before, and (d) the approximate time horizon — near-term (0-6 months), medium-term (6-18 months), or long-term (18+ months). The stages in 4.2 should trace a clear path toward the maturity state described in 4.1 — a reader should be able to see how Stage 1 evolves into Stage N, and how Stage N matches the vision in 4.1. If the stages don't connect to the maturity vision, either the stages are wrong or the maturity vision needs revision. This is strategic sequencing, not a build plan — Phase 7 translates these stages into concrete build cards. Section 4.2 answers "what strategic shifts happen and why." Phase 7 answers "what do we build and in what order." If you find yourself specifying features, sprint durations, or technical dependencies, you've crossed into Phase 7 territory — pull back to the strategic level.

---

**Section 5: Risk & Assumption Registry (v1)**
*Consumer: All subsequent phases (risk awareness), Phase 9 (risk review), founder (honest assessment)*
*Target length: 500-1,200 words (scales with number of risks). When AI risk decomposition produces 5+ separate entries, the upper target extends to 1,500 words.*
*Format: Structured entries. One subsection per risk, followed by key assumptions.*

Structure:
5.1-5.N. **[Risk Name]** — For each risk identified during the conversation. **Target length per risk entry: 4-6 sentences across all four fields.**
- **Category:** Competitive, Technical/Execution, Market/Adoption, Regulatory/Legal, or Funding/Sustainability. Use Regulatory/Legal for risks arising from compliance requirements, regulatory changes, or legal liability that could restrict the platform's ability to operate — required when research point 1.6 fires for a regulated industry. Use Funding/Sustainability for non-commercial platforms where the dominant risk is loss of funding or institutional support rather than competitive pressure.
- **Description:** What the risk is, in 1-2 sentences
- **Severity:** High (could kill the platform), Medium (would require significant adaptation), or Low (manageable with planning)
- **Current Mitigation Thinking:** The founder's initial thoughts on how to address it, even if preliminary. "No mitigation identified yet" is acceptable for v1.
- **AI risk decomposition:** For AI-dependent platform capabilities, decompose AI risks into component sub-risks when they have different severities or different mitigations: training data availability, model bias and fairness, regulatory explainability requirements, false positive/negative tolerance, and model governance (retraining triggers, version control, monitoring). When sub-risks have different severities, list them as separate risk entries with their own severity and mitigation — this gives downstream phases granular guidance on which AI risks require the most architectural attention. A single compound "AI risk" entry that aggregates multiple distinct failure modes with different severities and different mitigations is insufficient — downstream phases need granular risk guidance.
- **Cross-cutting risks:** If a risk manifests across multiple categories simultaneously (the same root cause creates competitive, technical, market, AND regulatory consequences), log it as a single entry with a primary category and cross-category notation: "Category: Market/Adoption (primary), with Regulatory/Legal, Competitive, and Technical manifestations." Describe each manifestation briefly. This preserves the single-risk identity while documenting its multi-category impact. The completion gate's three-distinct-category requirement counts cross-cutting risks toward their primary category.
- **Multi-authority regulatory risks:** When a platform operates under multiple regulatory authorities (e.g., FDA + EMA + TGA), organize risk entries by the RISK (the problem that could occur), not by the AUTHORITY (the regulator). Consolidate when the same regulatory concern spans multiple authorities — e.g., "data residency requirements across FDA, EMA, and TGA" is one risk entry, not three. Separate when distinct authorities create genuinely different failure modes — e.g., "FDA 21 CFR Part 11 electronic signature requirements" and "EMA Annex 11 computerized system validation" are separate risks if they require different technical mitigations. The organizing principle: would a development team need to do different work to mitigate these? If yes, separate entries. If no, consolidate with all relevant authorities listed.
5.N+1. **Key Assumptions** — Things the platform's success depends on that are believed to be true but haven't been validated. Minimum: 3 key assumptions. Maximum: 8 in Phase 1 — if more than 8 emerge, consolidate related assumptions into higher-level statements. The assumption registry grows across all phases; Phase 1 captures the foundational assumptions, not every uncertainty. Each assumption must be specific enough to be proven wrong — "the market is large enough" is too vague; "at least 500 freelance teams in the US would pay $25+/month for a tool in this category" is testable. **Target length per entry: 3-5 sentences — enough to state the assumption, explain what breaks if it's wrong, and describe how to test it.** Include at least one assumption from each category that applies:
  - **(a) Market assumptions** — Beliefs about customer demand, willingness to pay, or market size. Validation methods: customer interviews, landing page tests, pre-sale experiments, survey data.
  - **(b) Competitive assumptions** — Beliefs about competitor behavior, gaps, or response. Validation methods: ongoing monitoring, feature comparison updates in Phase 9, competitor user interviews.
  - **(c) Technical assumptions** — Beliefs about feasibility, third-party dependencies, or infrastructure availability. Validation methods: proof-of-concept builds, API (Application Programming Interface — a set of rules that lets different software systems communicate) documentation review, vendor consultation.
  - **(d) Team/resource assumptions** — Beliefs about the founder's ability to execute (time, skills, funding, hiring). Validation methods: resource planning, hiring timeline analysis, funding runway calculation.
  Not every category will apply to every platform — but the AI must explicitly evaluate each category and either produce an assumption or state why the category doesn't apply. For each assumption: the assumption statement, why it matters (what breaks if it's wrong), the category, and the appropriate validation method. This list grows in subsequent phases — later phases append new assumptions to their own risk sections rather than modifying D1. Phase 9 consolidates all assumptions from all phases into a final registry for validation review.

---

**Section 6: Monetization Strategy**
*Consumer: Phase 3 (feature prioritization based on revenue model), Phase 4 (data architecture for billing), Phase 5 (infrastructure for payment processing), Phase 7 (billing build cards)*
*Target length: 600-1,200 words*
*Format: Narrative prose with structured comparison.*

Structure:
6.1. **Revenue Models Explored** — At least 2-3 models that were discussed, with real price points from competitor research (1.5). For each model: how it works, what it would look like for this platform, and its pros/cons.
6.2. **Current Preference** — The founder's preferred revenue model and why. Stated as a working hypothesis, not a final decision — Phase 3 may refine it based on feature analysis.
6.3. **Unit Economics Intuition** — The rough math of whether the business model works at a basic level. Express all monetary estimates as ranges no wider than 3x (e.g., $10-30/month, not $5-50/month). A range wider than 3x provides no directional value — if the answer could be $5 or $50, the founder hasn't learned anything useful. **Enterprise B2B / opaque-pricing markets:** If competitor pricing is not publicly available (common in enterprise B2B markets where pricing requires "contact sales"), the 3x constraint applies to the founder's TARGET pricing range, not to the competitive benchmark range. State the competitive pricing observation separately ("Enterprise competitors use custom pricing in the estimated range of $X-$Y based on third-party sources") from the founder's intended price point range (which must meet the 3x constraint). If neither can meet the 3x constraint, document the uncertainty explicitly and flag Phase 5 to resolve it during infrastructure cost analysis. If the available data genuinely doesn't support a 3x range, state what's known and identify what Phase 3 or Phase 5 must resolve to narrow it. The unit economics analysis must address both sides of the equation:
  - **Revenue per customer:** Expected price point or range (from research 1.5 benchmarks), billing frequency (monthly/annual/per-transaction), and whether the model includes tiers or usage-based scaling.
  - **Cost to serve per customer:** Identify the major cost categories that apply to this platform. Common categories: infrastructure/hosting, AI processing (if applicable), payment processing fees (typically 2.9% + $0.30 per transaction), support burden, and third-party API costs. **Aggregate vs. per-customer:** If the conversation produced aggregate scenario modeling (total revenue vs. total costs at projected scale) rather than per-customer unit breakdowns, derive per-customer figures from the aggregate data — divide total costs by projected customer count to produce per-customer estimates. Both levels must appear in the deliverable: aggregate scenarios show viability at scale; per-customer figures reveal margin health and identify which customer segments are profitable vs. subsidized. Do not present aggregate scenarios alone without the per-customer derivation. **For platforms where AI processing is the core value delivery mechanism** (not a supplementary feature), AI processing costs are typically the dominant cost-to-serve category and should be analyzed with proportionate depth — including model inference costs, training/retraining costs, data pipeline processing, and model monitoring infrastructure. Do not bury this as one line item among equals; surface it as the primary cost driver with its own sub-breakdown. For platforms with real-time data ingestion (IoT, streaming, sensor networks, grid management), also consider: data pipeline processing costs, time-series or event storage (which may grow linearly with usage and never decrease), real-time alerting infrastructure, and device/sensor fleet management costs. For platforms in regulated industries where research point 1.6 fired, also consider: compliance-grade hosting premiums (validated infrastructure required by FDA, GxP, SOC2-certified environments may cost 3-10x standard cloud hosting), regulatory audit costs, and compliance monitoring tools. For each category, provide a rough estimate or state "deferred to Phase 5 for infrastructure sizing." The goal is completeness of categories, not precision of numbers.
  Example: "If the platform charges $25-35/month per team (based on competitor benchmarks from research 1.5) and serves 500 paying teams, that's $150K-210K annual revenue. Estimated cost per team: ~$3-5/month infrastructure (hosting + database), ~$1-2/month AI processing, ~$0.75-1/month payment processing fees. At ~$5-8/month total cost to serve versus $25-35/month revenue, the gross margin appears healthy at 70-80%."
  **For platforms with a significant free tier** (freemium, ecosystem adoption, or mission-driven pricing where a substantial portion of users generate cost without generating revenue), model unit economics at two levels: (a) per-paying-customer economics (revenue vs. cost for paying users only) and (b) blended economics (total revenue vs. total cost including free-tier users). Present both — per-paying-customer economics show margin health; blended economics show sustainability at scale. Example: "60 paying districts × $5,000/year = $300K revenue. 100 total districts × $2,000/year cost-to-serve = $200K costs. Per-paying-district margin is healthy ($3,000), but blended margin (33%) is tighter due to 40 free-tier districts generating costs without revenue." The viability statement must address both levels. **Mission-driven free tiers (permanent commitment, not conversion funnel):** When the free tier is a mission-driven commitment where free users will never convert to paid (e.g., Title I districts receiving free access by policy), model blended economics with zero conversion assumption — the viability statement must demonstrate that paying customers generate sufficient margin to subsidize permanent free users at the projected ratio. State the maximum free-to-paid ratio the model can sustain. Do not design conversion workflows for mission-committed free segments.
  Conclude with a directional viability statement: "At these ranges, the unit economics appear viable/marginal/concerning because [reason]." This is Phase 1 intuition, not Phase 5 analysis — but the founder should leave this section knowing whether the basic business math has obvious problems. For B2B2B or multi-tier business models where the paying customer and the cost-generating user are different entities, model unit economics at BOTH tiers: (a) per-intermediary economics (what each bank/reseller/partner pays vs. the marginal cost of supporting their deployment), and (b) per-end-user economics (the marginal infrastructure cost per end user, which the intermediary's pricing must cover). **For white-label or multi-tier models where 3+ economic tiers exist** (e.g., vendor → reseller → client → end user), model unit economics at EACH tier where a distinct pricing or cost relationship exists. Identify the tier at which the business model's viability is most sensitive (typically the middle tier in a three-tier model) and provide the most detailed analysis at that tier. The viability assessment considers all tiers: "At [intermediary price] with [average end users per intermediary], the per-end-user revenue is [calculated figure] vs. per-end-user cost of [figure]."
6.4. **Business Model Dependencies** — Anything the revenue model requires from downstream phases. Examples: "If we go marketplace, we need transaction processing infrastructure," "If we go freemium, we need to define the free vs. paid feature boundary." Each dependency listed here must also appear as a D-55 decision ledger entry with explicit Binds — the D-55 entry captures the phase-specific bind; the D1 text describes the dependency in founder-readable language. **Upstream dependencies:** If the revenue model itself requires external regulatory approval before it's legally viable (e.g., financial trading licenses, energy market authorization, healthcare billing certification), document the regulatory requirement as both a Section 6.4 dependency AND a Section 5 risk entry with Regulatory/Legal category. The dependency binds Phase 5 (regulatory authorization pathway in technical architecture). The risk captures the timeline and uncertainty of approval. Note: The phase-specific bind references in this specification paragraph (e.g., "binds Phase 5") are spec-level annotations showing where to track dependencies in the D-55 ledger. They do not appear in the founder-facing D1 text — the D1 text describes the dependency in plain language; the D-55 entry captures the phase binding.
<!-- XREF: foundation → decision_ledger_contextualization → D-55 3-line schema --> — this is an application of the universal downstream-obligation rule stated in `<synthesis_formatting_rules>`. *(If this rule is updated here, update `<synthesis_formatting_rules>` to match, and vice versa.)*

---

**Additional Artifacts Initialized (not numbered deliverables — not tracked by Phase 9 manifests):**

- **GLOSSARY.md** — A structured glossary of domain-specific terms identified during this phase. Every industry has jargon, and this glossary ensures consistent terminology across all 20 deliverables. Grows throughout all phases. **Minimum: 5 domain-specific terms from the founder's industry, plus TAM, SAM, and SOM as universal business planning terms.** Domain-specific terms are words or phrases that meet any of these criteria: (a) unique to the founder's industry (e.g., "escrow" in real estate, "triage" in healthcare, "ticket time" in restaurant operations), (b) general terms with specialized meaning in this context (e.g., "listing" means a property for sale in real estate, not a generic list — include the specialized definition), or (c) terms the founder uses that their customers would need defined (e.g., if the founder's platform serves restaurants, "ticket time" might be obvious to restaurant owners but not to their staff or to developers building the platform). Exclude general business terms (subscription, revenue, user, customer) unless the founder's domain gives them a meaning that differs from common usage. Examples by industry — Healthcare: "HIPAA" (a US law governing medical data privacy), "EHR" (Electronic Health Record), "care pathway." Real estate: "escrow," "MLS" (Multiple Listing Service), "cap rate" (capitalization rate). E-commerce: "SKU" (Stock Keeping Unit), "fulfillment," "cart abandonment." These are illustrative — every industry has its own vocabulary. The pre-flight verification confirms at least 5 domain-specific terms were identified before synthesis begins. Format per entry:
  - **Term:** The word or phrase
  - **Definition:** Plain-English explanation (1-3 sentences — long enough to be useful, short enough to scan quickly). Contextualize to this specific platform: not just "what does this term mean generally" but "what does this term mean in the context of THIS platform." Example: "IND" for a clinical trial platform should not just define "Investigational New Drug application" but note "the regulatory submission that determines whether TrialForge's sponsor users can begin their clinical trials — a key workflow trigger in the platform."
  - **First Appeared:** Phase number where the term was first used
  - **Related Deliverables:** Which deliverables reference this term
  - **Technical Equivalent (if applicable):** The technical term that maps to this domain concept (e.g., "Customer" → "tenant" in multi-tenant architecture — a system design where one platform serves many separate organizations, each seeing only their own data)

  **GLOSSARY.md document format:** File header: `# GLOSSARY — [Platform Name]` followed by a one-sentence description: "Domain-specific terminology identified during the PlatformForge planning process. This glossary ensures consistent language across all deliverables." Entries sorted alphabetically by term — universal business planning terms (TAM, SAM, SOM) are intermixed alphabetically alongside industry-specific terms, not separated into a subsection. Each entry separated by a blank line. File ends with `<!-- EOF: GLOSSARY.md -->`.

- **demo-requirements-flag.md** — A structured flag capturing the demo environment decision from Conversation Area 6. This is a standalone artifact, separate from D1. D1 may reference the demo strategy in three specific places only: Section 1.2 (The Platform — the elevator pitch) may include one sentence referencing the demonstration approach if it's central to the platform's value proposition — e.g., "The platform's value is best demonstrated through [brief description of aha moment]." Section 1.5 (Ambition Level) may note whether a demo environment is needed as a scope consideration. Section 4.2 (The Growth Path) may reference how the demo or showcase strategy evolves across growth stages — e.g., "Stage 2 transitions from demo data to real user data." No other D1 sections should reference demo details. All demo-specific operational details (scenarios, downstream binds, aha moment, data requirements) live exclusively in the Demo Requirements Flag to avoid duplication. Format: Each field as a bold label followed by its value. Single-value fields appear on the same line as the label (e.g., `**Demo Environment Needed:** Yes`). Multi-value fields (Demonstration Flow, Key Demo Scenarios) use a bulleted or numbered list on lines immediately following the label. Fields separated by line breaks. File header: `# Demo Requirements Flag — [Platform Name]`. Target length: 200-600 words (scales with number of demo audiences: ~200 words for single audience, ~350-400 for two audiences, ~500-600 for three audiences). For platforms where the buyer and end user are distinct entities (B2B2C, B2B2B, white-label), capture separate demo flows: (a) Buyer Demo — what the purchaser/intermediary needs to see, (b) User Demo — what the end user needs to see. Each has its own Demonstration Flow, Aha Moment, and Key Demo Scenarios. If only one demo is needed, note "Single audience — buyer and user are the same." **Buyer-user overlap:** When the buyer is also a primary user type and additional user types exist with different demo needs (e.g., a GC who both purchases and uses the platform, plus subcontractors and owners who use it differently), create per-audience blocks for each distinct user type that requires a different demo flow. The buyer's block serves dual purpose (purchasing evaluation + operational evaluation). **For grant-funded platforms:** capture a third demo audience: (c) Grant Funder Demo — what the funding body needs to see. Grant funders evaluate against specific deliverables (prototype readiness, pilot partner count, compliance validation), not against market appeal or growth potential. Capture the grant deliverables as demo success criteria in the demo-requirements-flag. **Grant-buyer overlap:** When the grant funder's evaluation criteria overlap significantly with the buyer's criteria (common in domains like education technology, where funders want to see the same working product and impact evidence that buyers evaluate), differentiate the grant funder block by emphasizing the mission/equity angle and the grant-specific deliverables (pilot plan, timeline, impact metrics) rather than duplicating the buyer's feature walkthrough. The grant funder demo flow should show the same platform but through the lens of "does this deserve continued funding" rather than "should my organization adopt this." **For platforms where ai_dependency is Core or Feature:** include an **AI Model Requirements for Demo** field: Does the demo require a pre-trained AI model (not just populated data)? If yes, what training data source — historical partner data, synthetic data, or other? For Feature-level AI, include this field only if the demo must demonstrate the AI capability to achieve its aha moment. This is distinct from seed data: a populated database shows the platform's interface, but an AI demo must show the AI's predictions or recommendations actually working. Log the model requirement as a Phase 7 bind: "Build sequencing must include model pre-training before demo readiness." File ends with `<!-- EOF: demo-requirements-flag.md -->`.
  - **Demo Environment Needed:** Yes / No
  - **Rationale:** 1-2 sentences explaining why
  - **Demo Audiences:** Single audience (buyer and user are the same) / Multiple audiences (list: Buyer, User, Grant Funder — as applicable)
  - **Per-audience blocks** (repeat for each audience when Demo Audiences is "Multiple audiences"):
    - **Audience:** [Buyer / User / Grant Funder]
    - **Demonstration Flow:** The sequence for showing the platform to this audience (3-5 steps)
    - **Aha Moment:** The specific point where this audience's eyes light up — stated in a single sentence specific enough to design a demo around
    - **Key Demo Scenarios:** What needs to be demonstrated for this audience (2-4 bullet points)
  - **Single-audience fields** (use when Demo Audiences is "Single audience" — these replace the per-audience blocks):
    - **Demonstration Flow:** The sequence the founder described for showing the platform to prospects/investors (3-5 steps)
    - **Aha Moment:** The specific point in the demo where the prospect's eyes light up. Must be stated in a single sentence specific enough to design a demo around — "the prospect sees the value" is too vague; "the prospect sees their own data organized in a way they've never been able to achieve before" is specific enough.
    - **Key Demo Scenarios:** If yes, what the founder wants to demonstrate (2-4 bullet points)
  - **Downstream Binds:** If yes: "Phase 4 must design demo tenant (a separate, self-contained data environment for demonstration purposes) data architecture. Phase 7 must include seed data generation and demo provisioning in build cards."
  - **Decision Ledger Reference:** The D-55 entry number where this decision is recorded
  - **AI Model Requirements for Demo:** [Yes/No — include when ai_dependency is Core, or when ai_dependency is Feature AND the demo's aha moment depends on AI output. If Yes: training data source (historical partner data / synthetic data / other). Phase 7 bind: model pre-training before demo readiness. Omit field entirely when ai_dependency is None.]
  - **"No" case values:** If Demo Environment Needed is No, set Demonstration Flow to "N/A", Key Demo Scenarios to "N/A — platform can be demonstrated with production data from launch", and Downstream Binds to "None". Rationale, Aha Moment, and Decision Ledger Reference are still required.

---

**Cross-Reference Manifest for D1**

After synthesizing D1, append the cross-reference manifest in the D-60 format. The manifest uses YAML (a structured data format that uses indentation and simple punctuation to organize information in a human-readable way). Generate it during the same synthesis pass — you have maximum context about what you just produced. Only include facts that actually appear in the synthesized D1. Do not pre-fill placeholder values — every export must correspond to real content in the deliverable.

```yaml
<!-- CROSS-REFERENCE MANIFEST: D1 — Platform Vision & Opportunity Analysis -->
phase: 1
deliverable: D1
produced_by: Phase 1
version: v1.0

exports:
  platform_identity:
    - name: "[Platform name]"
    - category: "[Platform category]"
    - tagline: "[One-line description]"
    - web_domain: "[Web domain — omit if not discussed]"
    - business_domain: "[Industry/vertical]"
    - differentiator_status: "[confirmed / candidate / deferred to Phase 3]"
    - white_label: "[Yes / No — omit for standard branded platforms]"
    - deployed_identity_pattern: "[Include only if white_label is Yes]"
    - multi_concept: "[Yes / No — omit for single-concept platforms]"
    - scoping_status: "[confirmed / deferred to Phase 3 — include only if multi_concept is Yes]"
  target_market:
    - primary: "[Primary audience]"
    - secondary: "[Secondary/adjacent audiences]"
    - geography: "[Geographic scope]"
    - primary_language: "[Primary language, or 'English only']"
    - localization_required: "[Yes / No / Not discussed]"
    - user_types:
      - count: "[Number of distinct user types]"
      - primary_user: "[Role name — adopts first]"
      - buyer: "[Role name — purchasing decision-maker, or 'Same as primary_user']"
      - types: # "Role name | 1-sentence description"
        - "[Role 1] | [Brief description]"
  competitors:
    - primary_competitor: "[Most relevant competitor by feature overlap]"
    - competitor_count: "[Total identified]"
    - entries: # "Name | Positioning | Key weakness"
      - "[Competitor] | [Positioning] | [Primary gap]"
    - unclaimed_space: "[Opportunity gap — 1 sentence]"
  revenue_model:
    - preferred: "[Subscription/freemium/marketplace/usage-based]"
    - competitor_price_range: "[Lowest–highest found in research]"
    - founder_pricing_preference: "[Intended price point or range]"
    - unit_economics_signal: "[Viable / Marginal / Concerning]"
  risk_profile:
    # Include competitive_risk, technical_risk, market_risk always.
    # Include regulatory_risk when regulated_industry is Yes.
    # Include funding_risk when governance_model present or non-commercial funding.
    # "Top" = highest severity; tiebreak by broadest downstream impact.
    - competitive_risk: "[1 sentence]"
    - technical_risk: "[1 sentence]"
    - market_risk: "[1 sentence]"
    - regulatory_risk: "[1 sentence — conditional]"
    - funding_risk: "[1 sentence — conditional]"
  vision_scope:
    - ambition_level: "[Lifestyle / growth / venture / experiment / community-institutional / founder-defined]"
    - long_term_scale: "[3+ year scale — 1 sentence]"
    - data_asset: "[Unique data that accumulates — 1 sentence]"
    - growth_stages_count: "[Number of stages in Section 4.2]"
    - growth_stages_names: "[Comma-separated stage labels]"
    - growth_stages_horizon: "[e.g., 0-36 months]"
  network_effects:
    - type: "[two-sided marketplace / multi-sided marketplace / same-side social / data-driven / cross-network coordination / none]"
    - regulatory_constraint: "[Description or 'None']"
    - strength: "[Strong / moderate / weak / none]"
    - growth_implication_type: "[Drives viral acquisition / Increases retention / Enables marketplace flywheel / Strengthens data moat / N/A]"
    - growth_implication_detail: "[1 sentence]"
    - commercial_constraint: "[Description or 'None']"
  governance_model: # Optional — omit for standard single-source commercial platforms.
    - type: "[Commercial / Social Enterprise / Consortium / Government / Foundation]"
    - data_ownership: "[Platform-owned / Participant-owned / Shared-with-withdrawal-rights / Client-owned]"
    - funding_source: "[Venture / Grant / Self-funded / Institutional-membership / Mixed]"
  demo_requirements:
    - needed: "[Yes/No]"
    - key_scenarios: "[2-4 scenarios semicolon-separated if yes; 'N/A' if no]"
    - demo_audience_count: "[Number of distinct demo audiences]"
    - demo_audience_types: "[Comma-separated list]"
  regulatory_flags:
    - regulated_industry: "[Yes/No]"
    - key_considerations: "[1-2 sentences if yes, 'N/A' if no]"
    - regulatory_jurisdictions: "[Count of distinct authorities. '0' if unregulated.]"
    - regulatory_variation_type: "[international-agency / US-state-variation / hybrid / single-jurisdiction / N/A]"
    - state_variation_scope: "[Omit unless US-state-variation or hybrid]"
  assumptions:
    - count: "[Number of key assumptions in Section 5]"
    - highest_impact: "[Most consequential assumption — 1 sentence]"
    - highest_impact_validation: "[How to validate]"
    - highest_impact_category: "[Competitive / Technical / Market / Regulatory / Funding-Sustainability / Team-Resource]"
    - categories_covered: "[Comma-separated list with entries]"
    - categories_absent: "[Categories with NO entries, or 'None — all covered']"
  infrastructure_constraints: # Optional — omit for platforms with no unusual constraints.
    - offline_capability: "[Required / Not required / Not discussed]"
    - offline_detail: "[Brief description — include only if Required]"
    - device_connectivity: "[Required / Not required / Not discussed — include for IoT/edge/hardware platforms only]"
    - device_connectivity_detail: "[Device profile, max latency, connectivity loss impact]"
    - real_time_requirements: "[Required / Not required / Not discussed]"
    - real_time_detail: "[Latency requirements — include only if Required]"
    - data_residency: "[Required / Not required / Not discussed]"
    - data_residency_detail: "[Geographic constraints — include only if Required]"
    - other: "[Any constraint binding 3+ downstream phases]"
    - ai_dependency: "[Core / Feature / None]"
    - ai_cold_start: "[Initial data strategy. 'N/A' if ai_dependency is None]"
    - ai_harm_profile: "[Safety-critical / Decision-support / Informational / N/A]"
  decision_ledger:
    - count: "[Number of D-55 entries]"
    - categories_covered: "[Comma-separated required categories covered]"

imports: none (Phase 1 is the origin)

sections:
  1: "Platform Vision"
  2: "Market Opportunity"
  3: "Competitive Landscape"
  4: "Long-Term Vision Statement"
  5: "Risk & Assumption Registry (v1)"
  6: "Monetization Strategy"

references_out: none

references_in:
  - from: D2
    context: "User personas derived from target_market exports"
  - from: D3
    context: "Feature priorities informed by competitors, revenue_model, risk_profile"
  - from: D4
    context: "Data architecture from vision_scope.data_asset, demo_requirements, regulatory_flags"
  - from: D5
    context: "Technical architecture from vision_scope.long_term_scale, regulatory_flags, revenue_model"
  - from: D6
    context: "Design system from platform_identity exports"
  - from: D7
    context: "Build sequencing from ambition_level, growth stages, demo_requirements"
  - from: D8
    context: "Operations planning from risk_profile, demo_requirements"
  - from: D9
    context: "Phase 9 loads full D1 manifest for cross-deliverable consistency checks"
  - from: D10 (Cost Estimation & Budget Projection)
    context: "Cost model from revenue_model price data"
  - from: D13 (Terms of Service)
    context: "Service description from platform_identity"
  - from: D14 (Accessibility Compliance Spec)
    context: "Accessibility scope from platform_identity.category, target_market.primary"
  - from: D15 (SEO & Marketing Pages)
    context: "SEO meta from platform_identity.tagline, target_market.primary"
  # D11, D12, D16-D20 do not reference D1 directly — derive from Phase 5/7/8 specs.
<!-- END MANIFEST -->
```

<!-- MANIFEST FIELD REFERENCE (AI reference only — consult when generating manifest values, do not reproduce in output):
- platform_identity.white_label: Include only if platform is offered as white-label. deployed_identity_pattern describes how it appears to end users.
- platform_identity.multi_concept: When Yes, Phase 9 should flag for extra scrutiny during cross-deliverable validation.
- target_market.localization_required: Include if non-English market identified OR regulatory mandates content in other languages.
- network_effects.type options: multi-sided marketplace = 3+ participant types transacting/matching through platform. cross-network coordination = different user types benefit from each other without transacting through platform.
- governance_model: Social Enterprise = commercially structured with mission-driven constraints on pricing/access/deployment. funding_source is the only manifest field capturing non-commercial funding info.
- infrastructure_constraints inclusion rule: When included, include all sub-fields with explicit value options using "Not required" or "Not discussed" values. Omit only sub-fields whose inclusion conditions are not met.
- ai_dependency tiebreaker: If core workflow functions without AI but market positioning depends on AI → Core. Test: remove AI entirely, does platform still have defensible market position? Yes → Feature. No → Core.
- ai_harm_profile: Safety-critical = AI errors create immediate risk WITHOUT mandatory human review. Decision-support = AI errors affect outcomes through human-mediated decisions. A safety-critical domain where AI provides analytics reviewed by humans = Decision-support. When ambiguous, default to more cautious level.
- risk_profile "top" selection: When multiple risks share highest severity, select broadest downstream impact (binds most phases).
- references_out note: D1 Section 6.4 forward dependency statements tracked in D-55 ledger, not references_out. references_out is for backward citations only.
-->

**Manifest target size:** 1,500-3,000 bytes. Over 4,000 bytes means exports are too detailed — consolidate by shortening descriptions to dependent clauses, removing optional fields that weren't discussed, and merging related fields. **Note:** D1's manifest target exceeds the master prompt's general 500-2,000 byte guideline because D1 is the origin deliverable referenced by all 19 subsequent deliverables, requiring more export categories than typical mid-process deliverables with narrower cross-deliverable scope.

**Manifest generation rules for deferred or absent values:** If a field's value was explicitly deferred to a later phase during the conversation, state "Deferred to Phase [N]" rather than leaving it empty or guessing. If a field was never discussed (e.g., geography wasn't mentioned), state "Not specified — default: Global" or the most reasonable default. Fields marked with "include only if known" in the template above (such as web_domain) should be omitted entirely if the topic was not discussed — absence is cleaner than placeholder text for manifest parsing. Every non-optional export field must have a value — no empty fields. The `version` field must match the Phase Version stated in the D1 document header.

**Manifest field extensibility:** Bracketed options in export fields (e.g., "[Lifestyle / growth / venture / ...]") are illustrative, not exhaustive. If the platform's characteristics don't map to the listed options, use a descriptive value that accurately represents the platform. Phase 9 validation should accept custom values and verify them against D1 content rather than validating against a fixed enum.

**Manifest completeness standard (applies to all phases):** Every phase's manifest must: (a) list all deliverables that reference it in `references_in` with export-field specificity showing which export fields each consumer uses, (b) explicitly note which deliverables do NOT reference it and why (as a comment), (c) omit optional exports if unpopulated rather than using "TBD" placeholders.

**EOF sentinel:** Append `<!-- EOF: D1-platform-vision.md -->` as the final line of D1, after the manifest. GLOSSARY.md ends with `<!-- EOF: GLOSSARY.md -->`. demo-requirements-flag.md ends with `<!-- EOF: demo-requirements-flag.md -->`. These are the standard end-of-file markers required by the master system prompt's output standards.

</phase_outputs>


<!-- EOF: phase-1-synthesis.md -->
