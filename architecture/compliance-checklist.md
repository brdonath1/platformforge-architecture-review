# D-193 Layer 1: Template Compliance Checklist

> **Purpose:** Machine-checkable pass/fail assertions for every deliverable produced by a 10-phase orchestrator run. Applied identically across all D-192 model tiers (Haiku → Sonnet 4.5 → Sonnet 4.6 standard → Sonnet 4.6 high). No subjective quality judgments. Compliant with G-10/D-77.
>
> **How to use:** For each deliverable, check every assertion. Mark PASS or FAIL. A deliverable passes Layer 1 if all assertions pass. Aggregate results per phase and per run.
>
> **What this does NOT measure:** Whether content is *good*, *accurate*, or *useful*. That's Layer 2 (Cross-Tier Diff Analysis) + human judgment.

---

## Run Metadata

| Field | Value |
|-------|-------|
| Run Date | |
| Model Tier | |
| Model String | |
| Total Cost | |
| Total Runtime | |
| Phases Completed | /10 |
| Deliverables Produced | /23 |

---

## Phase 1: Vision & Opportunity Exploration

### D1 — Platform Vision (d01-platform-vision.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Contains 6 numbered sections (Section 1 through Section 6)
- [ ] Section 1: Platform Vision — subsections 1.1 (The Problem), 1.2 (The Platform), 1.3 (Target Audience), 1.4 (Adjacent Opportunities), 1.5 (Ambition Level), 1.6 (Defensible Differentiator) present
- [ ] Section 2: Market Opportunity — subsections 2.1 (TAM), 2.2 (SAM), 2.3 (SOM), 2.4 (Market Timing) present
- [ ] Section 3: Competitive Landscape — at least 3 competitors analyzed + Competitive Synthesis subsection (3.N+1)
- [ ] Section 4: Long-Term Vision — subsections 4.1 (Maturity Vision), 4.2 (Growth Path with 3-5 stages) present
- [ ] Section 5: Risk & Assumption Registry — at least 3 risks from distinct categories, each with severity and mitigation
- [ ] Section 6: Monetization Strategy — subsections 6.1 (Model), 6.2 (Pricing), 6.3 (Unit Economics), 6.4 (Business Model Dependencies) present
- [ ] Appendix A: Decision Ledger present (D-55 entries)
- [ ] Cross-reference manifest present (YAML block at end)

**Content substance:**
- [ ] Section 1.3 identifies primary audience + at least 3 adjacent market segments
- [ ] Section 2 contains numeric TAM/SAM/SOM estimates (not just labels)
- [ ] Section 4.2 growth stages each have: defining shift, transition trigger, what it unlocks, time horizon
- [ ] Section 5 risks each have: severity level (High/Medium/Low), mitigation approach
- [ ] Section 6.3 contains both aggregate scenarios AND per-customer figures
- [ ] Research citations present with engine name and date

**Format compliance:**
- [ ] Document header metadata block present (platform name, version, date, phase)
- [ ] No PlatformForge methodology internals in Sections 1-6 (no phase numbers, no D55-P1-xxx, no template names, no AI model names)
- [ ] Uses ## for section headers, ### for subsections
- [ ] EOF sentinel present

### GLOSSARY.md

- [ ] File exists and is non-empty
- [ ] Header: `# GLOSSARY — [Platform Name]`
- [ ] At least 5 domain-specific terms
- [ ] TAM, SAM, SOM included as entries
- [ ] Each entry has: Term, Definition, Related Deliverables
- [ ] Entries sorted alphabetically
- [ ] EOF sentinel present

### demo-requirements-flag.md

- [ ] File exists and is non-empty
- [ ] Header: `# Demo Requirements Flag — [Platform Name]`
- [ ] Demo Environment Needed field present (Yes/No)
- [ ] If Yes: Demonstration Flow, Aha Moment, Key Demo Scenarios, Downstream Binds present
- [ ] Word count within 200-600 range
- [ ] EOF sentinel present

---

## Phase 2: User Personas & Journey Maps

### D2 — User Persona & Journey Maps (d02-user-personas.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] User Role Matrix present (table format with all identified user types)
- [ ] Permission Matrix present (role × capability grid)
- [ ] Individual persona sections for each user type (minimum 4 personas)
- [ ] Journey map for each primary persona
- [ ] Multi-tenant sections present if D1 indicates multi-tenant potential
- [ ] Decision ledger appendix present (D55-P2-xxx entries)
- [ ] Cross-reference manifest present

**Content substance:**
- [ ] Each persona has: name/archetype, demographics, goals, pain points, technical proficiency
- [ ] Each journey map has: stages, touchpoints, emotions, opportunities
- [ ] Permission matrix covers CRUD operations per entity per role
- [ ] Research citations present for behavioral patterns and regulatory landscape

**Supplementary outputs:**
- [ ] Risk & Assumption Registry update present (new risks/assumptions from user exploration)
- [ ] GLOSSARY.md updated with user role names and workflow terminology
- [ ] Compliance & Accessibility Requirements Flag present (if regulatory research fired)
- [ ] Methodology Feedback section present in conversation output

---

## Phase 3: Feature Definition & Prioritization

### D3 — Feature Registry & Priority Matrix (d03-feature-registry.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Feature registry table present with unique feature IDs (F-xxx format)
- [ ] Priority tiers defined: MVP, Phase 2, Phase 3, Future
- [ ] Each feature has: ID, name, description, user roles served, priority tier, complexity estimate
- [ ] Feature dependency map present
- [ ] Decision ledger appendix present (D55-P3-xxx entries)
- [ ] Cross-reference manifest present

**Content substance:**
- [ ] Monetization-implied features present (billing, subscription management, tier gating per D1 Section 6)
- [ ] At least 1 feature per user role from D2
- [ ] MVP tier produces a coherent, deployable product (not just fragments)
- [ ] Research citations present for competitive feature analysis

**Supplementary outputs:**
- [ ] ANALYTICS-EVENT-CATALOG.md created (event categories per feature)
- [ ] NOTIFICATION-TEMPLATE-CATALOG.md created (triggers per feature)
- [ ] GLOSSARY.md updated with feature names and module names

---

## Phase 4: Data Architecture

### D4 — Database Schema & Data Architecture (d04-database-schema.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Complete table definitions with column names, types, constraints
- [ ] Every table has: id (uuid), created_at (timestamptz), updated_at (timestamptz)
- [ ] Foreign key relationships specified with ON DELETE behavior
- [ ] RLS (Row Level Security) policy document present
- [ ] Index recommendations present
- [ ] Migration strategy or ordering present
- [ ] Decision ledger appendix present (D55-P4-xxx entries)
- [ ] Cross-reference manifest present

**Content substance:**
- [ ] Tables cover all entities implied by D2 user roles and D3 features
- [ ] Multi-tenant isolation present if D2 flagged multi-tenancy (organizations table, tenant-scoped FKs)
- [ ] Demo tenant architecture present if demo-requirements-flag says Yes
- [ ] Personal data tables explicitly identified (feeds D12 privacy policy)
- [ ] GDPR/privacy considerations documented
- [ ] Research citations present for schema patterns and Supabase-specific guidance

**Supplementary outputs:**
- [ ] GLOSSARY.md updated with database terminology
- [ ] ANALYTICS-EVENT-CATALOG.md updated if schema revealed new events

---

## Phase 5: Technical Architecture

### D5 — Technical Architecture Specification (d05-technical-architecture.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Tech stack selection with specific versions and rationale
- [ ] Authentication and authorization architecture
- [ ] API design patterns and conventions
- [ ] Deployment architecture (hosting, CI/CD, environments)
- [ ] File upload security pipeline (if applicable)
- [ ] Third-party integration specifications
- [ ] Decision ledger appendix present (D55-P5-xxx entries)
- [ ] Cross-reference manifest present

### D6 — API Specification (d06-api-specification.md)

- [ ] File exists and is non-empty
- [ ] Endpoint definitions for all D3 MVP features
- [ ] Each endpoint has: method, path, request schema, response schema, auth requirements, error codes
- [ ] Endpoints respect D4 RLS policies
- [ ] Rate limiting strategy specified
- [ ] Cross-reference manifest present

**Content substance (D5 + D6):**
- [ ] Every D3 MVP feature has corresponding technical implementation path
- [ ] Cost estimates per service present (feeds D10)
- [ ] Monitoring and observability strategy specified (feeds D18)
- [ ] Research citations present with current pricing and version numbers

**Supplementary outputs:**
- [ ] GLOSSARY.md updated with technical terminology
- [ ] ANALYTICS-EVENT-CATALOG.md updated with API-level events

---

## Phase 6: Design System & UI Architecture

### D7 — UI/UX Decision Record (d07-design-system.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Design token system (colors, typography, spacing, breakpoints)
- [ ] Component specifications (from design system)
- [ ] Page inventory table (every screen with URL route, layout, components, role visibility, priority)
- [ ] Navigation architecture
- [ ] Onboarding and first-run experience
- [ ] Notification design system
- [ ] Accessibility standards (Section 14)
- [ ] Decision ledger appendix present (D55-P6A/P6B/P6C entries)
- [ ] Cross-reference manifest present

**Content substance:**
- [ ] Color tokens include full specification (primary, secondary, semantic, dark mode if applicable)
- [ ] Every D3 MVP feature maps to at least one page in the inventory
- [ ] Error boundary strategy specified (global-error, per-route)
- [ ] Legal/consent UI locations documented (cookie consent, privacy settings, TOS acceptance)
- [ ] Responsive breakpoints defined

### D14 — Accessibility Compliance Spec (d14-accessibility-spec.md)

- [ ] File exists and is non-empty
- [ ] Section 1: Standard and Scope (WCAG level specified)
- [ ] Section 2: Color and Visual Accessibility
- [ ] Section 3: Component-Level Accessibility Checklist (covers every component from D7 Section 3)
- [ ] Section 4: Page-Level Accessibility Requirements (covers every page from D7 Section 6)
- [ ] Section 5: Form Accessibility
- [ ] Section 6: Navigation Accessibility
- [ ] Section 7: Motion and Animation Policy
- [ ] Section 8: Testing Protocol
- [ ] Section 9: Remediation Process
- [ ] Cross-reference manifest present

**Supplementary outputs:**
- [ ] GLOSSARY.md updated with design and accessibility terminology
- [ ] ANALYTICS-EVENT-CATALOG.md updated with UI-level events

---

## Phase 7: Build Planning

### D8 — Sequenced Build Cards (d08-build-sequence.md)

**Structural completeness:**
- [ ] File exists and is non-empty
- [ ] Build cards use FC-[NNN] format
- [ ] Each card has: title, description, spec references (exact deliverable + section), tool routing (Cursor/Claude Code), dependencies, verification criteria
- [ ] Cards sequenced for progressive functionality (not grouped by file type)
- [ ] MVP tier produces a deployable platform at completion
- [ ] Scaffold specification present
- [ ] Decision ledger appendix present (D55-P7-xxx entries)
- [ ] Cross-reference manifest present

**Content substance:**
- [ ] Every D3 MVP feature has at least one build card
- [ ] Spec references are exact: "Deliverable N, Section X.Y" (not vague "see the API spec")
- [ ] Verification criteria are observable behaviors (not "should work")
- [ ] Accessibility references present (pointing to D14, not D7 Section 14)
- [ ] Auth vertical precedes feature verticals in sequence
- [ ] Credential Sequencing Map present (partial D9 input)

**Supplementary outputs:**
- [ ] GLOSSARY.md updated

---

## Phase 8: Lifecycle & Operations

### D9 — Credential & Account Setup Guide (d09-credential-guide.md)
- [ ] File exists and is non-empty
- [ ] Organized by setup phase (pre-build / during-build / post-build)
- [ ] Every third-party service from D5 has setup instructions
- [ ] Cross-reference manifest present

### D10 — Cost Estimation & Budget Projection (d10-cost-model.md)
- [ ] File exists and is non-empty
- [ ] Monthly costs at 3 tiers (launch, growth, scale)
- [ ] Per-service cost breakdown
- [ ] Break-even analysis
- [ ] Cross-reference manifest present

### D11 — Domain & DNS Configuration Guide (d11-domain-dns-guide.md)
- [ ] File exists and is non-empty
- [ ] Domain registration steps
- [ ] DNS record specifications (A, CNAME, MX, TXT/SPF/DKIM/DMARC)
- [ ] Cross-reference manifest present

### D12 — Privacy Policy (d12-privacy-policy.md)
- [ ] File exists and is non-empty
- [ ] "Not legal advice" disclaimer present
- [ ] Data collection disclosure covers all personal data tables from D4
- [ ] GDPR and CCPA sections present
- [ ] Cross-reference manifest present

### D13 — Terms of Service (d13-terms-of-service.md)
- [ ] File exists and is non-empty
- [ ] "Not legal advice" disclaimer present
- [ ] Content ownership terms present
- [ ] Cross-reference manifest present

### D15 — SEO Configuration Spec (d15-seo-spec.md)
- [ ] File exists and is non-empty
- [ ] Meta tag specifications
- [ ] Sitemap strategy
- [ ] Cross-reference manifest present

### D16 — Analytics & Tracking Spec (d16-analytics-spec.md)
- [ ] File exists and is non-empty
- [ ] Consolidates ANALYTICS-EVENT-CATALOG.md from Phases 3-6
- [ ] Event definitions with trigger, data captured, question answered
- [ ] Cross-reference manifest present

### D17 — Email System Spec (d17-email-spec.md)
- [ ] File exists and is non-empty
- [ ] Consolidates NOTIFICATION-TEMPLATE-CATALOG.md from Phase 3
- [ ] Each notification: trigger, channel, recipient, content summary
- [ ] DNS records cross-referenced with D11
- [ ] Cross-reference manifest present

### D18 — Monitoring & Alerting Spec (d18-monitoring-spec.md)
- [ ] File exists and is non-empty
- [ ] Monitoring tool selection with thresholds
- [ ] Alert routing configuration
- [ ] Cross-reference manifest present

### D19 — Backup & Recovery Plan (d19-backup-recovery.md)
- [ ] File exists and is non-empty
- [ ] Backup strategy (frequency, retention, testing)
- [ ] Recovery procedures
- [ ] Cross-reference manifest present

### D20 — Maintenance Playbook (d20-maintenance-playbook.md)
- [ ] File exists and is non-empty
- [ ] Produced LAST (after D9-D19)
- [ ] Weekly, monthly, quarterly maintenance tasks
- [ ] Incident response procedures
- [ ] Cross-references to all other operational deliverables (D9-D19) with exact sections
- [ ] Every references_out entry resolves to an actual section in target deliverable
- [ ] Cross-reference manifest present

**Phase 8 global checks:**
- [ ] All 11 deliverables produced (D9-D13, D15-D20)
- [ ] Every deliverable has EOF sentinel
- [ ] Research citations present with current pricing data

---

## Phase 9: Review & Validation

### Validation Report

- [ ] Report exists and is non-empty
- [ ] All 20+ deliverables audited
- [ ] Cross-deliverable consistency checks performed (manifest comparisons)
- [ ] D14 chain of custody validated (D7 → D14 → D8)
- [ ] D3 ↔ D8 feature coverage verified (every MVP feature has build cards)
- [ ] D4 personal data tables ↔ D12 data collection disclosure verified
- [ ] D5 auth data ↔ D12 collection disclosure verified
- [ ] D20 cross-references all resolve
- [ ] Issues categorized by severity (CRITICAL / MAJOR / MINOR / INFO)
- [ ] Corrections applied to deliverables where possible

---

## Phase 10: Packaging & Handoff

### Build Handoff Document (README.md)

- [ ] File exists and is non-empty
- [ ] Repository structure documented
- [ ] "Read this first" orientation for development team
- [ ] Deliverable directory matches expected structure (specifications/, build/, operations/, legal/)
- [ ] All 23 deliverables present in package
- [ ] Price freshness gate passed (D10 costs verified against current pricing)
- [ ] EOF sentinel present

---

## Run Summary

| Metric | Value |
|--------|-------|
| Total assertions checked | |
| Assertions PASS | |
| Assertions FAIL | |
| Pass rate | % |
| Phases with 100% pass | /10 |
| Deliverables with 100% pass | /23 |
| Most common failure type | |

---

## Layer 2 Readiness

When this checklist is complete for two or more model tiers, proceed to D-193 Layer 2: Cross-Tier Diff Analysis. Focus diff analysis on deliverables where both tiers passed Layer 1 (structural completeness matched) — the interesting differences are in substance, not in missing sections.

<!-- EOF: compliance-checklist.md -->
