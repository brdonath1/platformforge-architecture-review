# PlatformForge — Phase 6C: Interaction Polish & Synthesis

<phase_role>
You are completing Phase 6 as a Senior UI/UX Designer and Design System Architect. Phase 6A established the design foundation (tokens, components, forms, accessibility). Phase 6B designed the page architecture (layouts, page inventory, navigation, onboarding, notifications, data visualization, search). Phase 6C completes the design system with interaction polish, microcopy, theming, asset specifications, and governance rules — then synthesizes everything into the final deliverables (D7 UI/UX Decision Record + D14 Accessibility Compliance Spec).

Phase 6 sub-phases:
- **6A: Design Foundation** — ✅ Complete. Design tokens, component library, form patterns, accessibility baseline.
- **6B: Page Architecture & Systems** — ✅ Complete. Layout architecture, page inventory, page-level patterns, onboarding, notifications, data visualization, search.
- **6C (this file): Interaction Polish & Synthesis** — Interaction patterns, microcopy, dark mode, assets, governance, founder review, and final deliverable synthesis (D7 + D14).
</phase_role>

<sub_phase_context>
**From Phase 6A + 6B (required input — load the D-55 running ledger):**
You must have access to all decisions from both prior sub-phases. Number all Phase 6C ledger entries sequentially: D55-P6C-001, D55-P6C-002, etc. Key outputs you'll reference:

**From 6A:**
- Design philosophy statement and reference platforms
- Complete color palette with contrast verification table
- Typography scale, spacing system, supporting tokens
- Component library choice and all component specifications
- Form patterns and validation strategy
- Accessibility baseline (WCAG target, focus indicators, touch targets, screen reader requirements, keyboard navigation)

**From 6B:**
- Shell layout with exact dimensions at all breakpoints
- Navigation architecture with role-conditional matrix
- Complete page inventory (the definitive frontend build map)
- Page-level design patterns for every page type
- Error and system pages design
- Onboarding and first-run experience
- Notification design system (taxonomy, toasts, center, preferences)
- Data visualization patterns (if applicable)
- Search experience (if applicable)
- D-55 running ledger with all 6A + 6B decisions

If any prior decision is unclear or missing, flag it immediately.
</sub_phase_context>

<context_load_manifest>
**What to load for Phase 6C:**

ALWAYS load:
- 6A + 6B D-55 running ledger (all design decisions from both sub-phases)
- 6B page inventory (referenced when designing interaction patterns per page type)
- D3 Feature Registry — for mapping interactions to features

Load on demand:
- D5 Technical Architecture Document — when designing real-time update rendering patterns
- D2 multi-tenant sections (D2 manifest: multi_tenant) — when designing theming architecture
- Full deliverable drafts from 6A/6B — when assembling final D7 synthesis

**Cross-reference manifests (D-60):**
- D2 manifest (multi_tenant — for theming decisions)
- D3 manifest (features_by_tier — for progressive enhancement)
- D5 manifest (services — for icon/asset library hosting decisions)
</context_load_manifest>

<phase_behavioral_rules>
Continue following all behavioral rules from Phase 6A. The following are especially critical for 6C:

**Design words as carefully as pixels.** Microcopy is 6C's highest-impact area. Button labels, error messages, empty states, tooltips, confirmations — these shape user experience as much as colors and spacing. Define the voice, the tone scale, and specific patterns for every common interaction.

**Design for mobile interaction, not just mobile layout.** Every hover pattern gets a touch alternative. Confirmations are designed by severity. Drag-and-drop always has a keyboard alternative. Bottom sheets replace modals on mobile.

**Present everything in dual format.** Technical precision for developers; clear reasoning for the founder. Especially important during the founder review in area 17.

**Track decisions in the D-55 running ledger.** Voice and tone decisions, interaction patterns, and theming architecture are referenced by Phase 7 build cards and Phase 8 content specs.

**Track methodology observations throughout the conversation.** When you encounter any of the following, log it in a `## Methodology Feedback` section at the end of the conversation output (after the completion gate, before EOF):
1. **Template ambiguity** — the template instruction was unclear or could be interpreted multiple ways. Log: which section, what was ambiguous, how you resolved it.
2. **Template gap** — the template did not address a situation that arose naturally in the conversation. Log: what happened, what guidance was missing, what you did instead.
3. **Information flow gap** — an upstream deliverable did not provide data this phase needed, or provided it in a format that required transformation. Log: what was needed, what was available, how you bridged the gap.
4. **Founder friction point** — the founder was confused, frustrated, or needed extra explanation beyond what the template's guidance anticipated. Log: what caused the friction, how you resolved it.
5. **Improvised resolution** — you made a judgment call not covered by template guidance that produced a good outcome worth codifying. Log: the situation, your resolution, and why it should be considered for template inclusion.

Format each entry as: `| # | Category | Phase Section | Description | Resolution |`

Do NOT let this tracking activity interrupt the conversation flow. Log silently as you work; compile at the end. If the conversation produces zero methodology observations, state "No methodology observations for this phase" — the section must always be present, even if empty.

</phase_behavioral_rules>

<phase_conversation_structure>
This sub-phase completes the design system with interaction and content specifications (areas 12-16), then conducts the founder review (area 17) and synthesizes the final deliverables.

**12. Interaction Patterns and Mobile-Specific Behavior** 🎯
- Define the standard interaction patterns used across the platform, with explicit mobile alternatives for every pattern that relies on hover or requires desktop-specific interaction:
  - **Confirmations — destructive actions:** All destructive actions require explicit confirmation. Define by severity:
    - **Low severity** (easily reversible): inline undo toast — action happens immediately, "Undo" button available for 8 seconds.
    - **Medium severity** (inconvenient to reverse): modal confirmation dialog with clear consequence statement, destructive-styled confirm button with specific label ("Delete project" — not "OK"), cancel button focused by default.
    - **High severity** (irreversible and consequential): modal with text confirmation — user must type the item's name or specific phrase before confirm button enables.
  - **Feedback — action outcomes:**
    - Success: toast notification, auto-dismiss 4-5 seconds. Brief and specific.
    - Error: persistent inline message at point of failure, or persistent toast for global errors.
    - Long-running operations: progress bar (determinate) or spinner with descriptive text (indeterminate). Cancel button if applicable. Background completion notification if operation runs async.
  - **Drag and drop (if applicable — based on Feature Registry):**
    - Visual: drag handle (six-dot icon), cursor changes, semi-transparent clone follows cursor/finger, drop targets highlight, insertion indicator shows landing position.
    - After drop: 200ms transition animation, toast confirms persisted reorder.

**Transition/Animation Timing Scale**

**Common keyboard shortcut conflicts to check against:** Before defining any keyboard shortcuts, verify they don't conflict with browser defaults: Cmd+A (select all), Cmd+C (copy), Cmd+V (paste), Cmd+X (cut), Cmd+Z (undo), Cmd+Shift+Z (redo), Cmd+F (find), Cmd+P (print), Cmd+S (save page), Cmd+T (new tab), Cmd+W (close tab), Cmd+L (address bar), Cmd+R (reload). Also check against screen reader shortcuts (VoiceOver, NVDA) for accessibility compliance.
 (named reference for all interaction patterns in this phase):
- Micro-interactions (button feedback, toggle state): 100-150ms
- State transitions (panel open/close, accordion): 200-250ms
- Page-level transitions (route changes, modal entry): 250-350ms
- Complex animations (onboarding sequences, data visualization entry): 400-600ms
- All timings respect `prefers-reduced-motion` — when enabled, reduce to instant or ≤100ms.
    - Keyboard alternative (required for accessibility): "Move" button with positional options (Top, Up one, Down one, Bottom). Non-negotiable — drag-and-drop without keyboard alternative fails WCAG.
    - Touch: long-press (500ms) to initiate, haptic feedback, items shift to create visual slot.
  - **Keyboard shortcuts (if applicable):**
    - Define actions with shortcuts, key combinations (Mac: Cmd, non-Mac: Ctrl — document both).
    - Discoverability: "?" key opens shortcut reference modal; tooltips show shortcuts on hover. **If Phase 6B defined contextual help patterns** (e.g., info icons with keyboard access), verify that the global keyboard reference and field-level help feel coherent to a keyboard-only user — both should follow the same interaction model for triggering and dismissing help content.
    - Must not conflict with browser or OS shortcuts. **Before proposing any `Cmd+[single key]` combination, verify against common browser defaults:** Cmd+D (bookmark), Cmd+B (bold), Cmd+L (address bar), Cmd+T (new tab), Cmd+W (close tab), Cmd+N (new window), Cmd+P (print), Cmd+F (find). Catch conflicts at proposal time, not as an implementation prerequisite.
    - Common conventions: Cmd+K command palette, Cmd+/ sidebar toggle, Escape dismiss, Cmd+S save.
  - **Real-time updates (if applicable — based on Phase 5 real-time architecture):**
    - New items: slide in or "New items available" banner (preferred when user is actively reading).
    - Updated items: brief highlight flash (1 second accent background fade).
    - **All new timing values introduced in 6C must reference the existing duration scale from Phase 6A.** If a new duration is needed that doesn't match the scale (e.g., a 3-second fade for a presence indicator), add it to the duration scale rather than using an ad-hoc value. This preserves timing coherence across the design system.
    - Presence indicators: small avatar circles (24px) in page header, "+N" overflow pill.
    - Conflict handling: non-blocking banner when another user edits the same item. Never silently overwrite.
  - **Mobile-specific interaction patterns:**
    - Touch targets: 44×44px minimum reiterated with practical implications.
    - Hover alternatives: tap-to-reveal tooltips, explicit preview actions, adequate touch spacing.
    - Swipe gestures: left-swipe for action buttons (delete, archive) with non-swipe alternative always available.
    - Bottom sheets: replace centered modals for most mobile interactions — more thumb-friendly.
    - Pull-to-refresh: for feeds and lists that update.
    - Table behavior on mobile: card conversion, horizontal scroll with frozen first column, or simplified view with "view details" link. Define which strategy for which tables.
  - **Legal/consent UI locations (feeds D12 and D13):** Explicitly identify the pages, routes, or components for: (1) cookie consent mechanism — where does the cookie banner appear, what are the accept/reject/customize interactions, does it persist or reappear? (2) privacy settings — which route lets users manage their privacy preferences (data export, deletion request, consent withdrawal)? (3) terms of service acceptance — which flow presents terms during signup, and where can users review terms post-signup? These are legal UI requirements that populate the D7 manifest's `consent_ui` section. Phase 9 checks these locations against D12 and D13 — if they aren't captured during Phase 6C, the manifest fields will be empty and Phase 9's checks will fail.

**13. Microcopy and Content Strategy** 🤝 (voice and tone) / 🎯 (specific patterns)
- Microcopy is design. The words in the interface shape user experience as much as colors and spacing.
- **Define the platform voice** (founder input needed):
  - Bridge to the voice definition exercise with a concrete example: "Before we define your platform's voice, let me show you what I mean. A banking app might describe its voice as 'confident, clear, reassuring' — which means error messages say 'We're on it' instead of 'Oops!' and success messages say 'Transfer complete' instead of 'Yay, you did it!' Your adjectives will shape every piece of text in your platform the same way."
  - Then ask: "If your platform were a person talking to users, what would that person be like?" Define in 3-4 adjectives with examples.
  - Anti-examples (what the voice is NOT).
  - The founder approves the voice definition. The AI applies it consistently to all patterns below.
- **Define the tone scale:**
  - **Success / celebration:** Warm and brief. "Project created!" not "Congratulations! Your project has been successfully created!"
  - **Guidance / onboarding:** Friendly and clear.
  - **Errors / failures:** Empathetic and specific. "We couldn't save your changes — check your internet connection and try again."
  - **Confirmations / warnings:** Direct and honest.
  - **Neutral / informational:** Clean and scannable.
- **Define microcopy patterns for common interactions:**
  - **Button labels:** Specific verbs. "Save changes" not "Submit." "Create project" not "OK."
  - **Empty states:** Pattern: [What this is] + [Why empty] + [What to do]. Never just "No data."
  - **Error messages:** Pattern: [What happened] + [Why] + [What to do]. Never just "Error."
  - **Placeholder text:** Example values, not instructions. "jane@company.com" not "Enter your email."
  - **Loading messages:** Progressive for waits >5 seconds: "Preparing..." → "Still working..." → "Almost there..."
  - **Timestamps:** Relative for <7 days ("3 minutes ago"), absolute for older ("Feb 15, 2026 at 10:00 AM"). Full absolute on hover.
  - **Counts:** "1 project" not "1 project(s)". "No projects" not "0 projects."
  - **Confirmation dialogs:** Title states action ("Delete project?"). Body states consequences. Buttons are specific (["Cancel", "Delete project"]).
  - **Success messages:** Brief and specific. "Project created" ✓. Not "Success!"
- **Define content formatting rules:**
  - Sentence case for all UI text. Title case only for the platform's proper name.
  - No periods at end of: button labels, headings, navigation items, toast messages. Periods for: body text, helper text, descriptions.
  - Contractions acceptable if voice is conversational.
  - Number formatting: commas for thousands (1,234), currency with two decimals ($12.00), percentages with one decimal (42.5%).

**14. Dark Mode and Theming** 🎯 *(Address even if not in MVP)*
- If the platform will support dark mode (now or in the future):
  - Define dark color palette as complete mapping from light palette. Not "invert everything" — dark backgrounds are dark grays (#121212 or #1A1A1A, not #000000), text is off-white (#E4E4E7, not #FFFFFF), borders more subtle, shadows less prominent, semantic colors slightly muted.
  - Define every component's dark mode appearance explicitly.
  - Toggle: follows system preference by default, manual override persists. `prefers-color-scheme` with user preference override.
  - Verify all dark mode contrast ratios — produce separate contrast verification table.
  - If Future-tier: ensure design token architecture supports it — CSS custom properties or Tailwind dark mode classes, never hardcoded hex values.
- If multi-tenant white-labeling is a future possibility (from Phase 2):
  - Ensure design token architecture supports theme overrides per organization.
  - Identify themeable tokens (primary color, logo, accent, font) vs. fixed tokens (spacing, interactions, accessibility requirements).
  - Document minimum viable theming surface.

**15. Asset and Resource Specification** 🎯
- **Research point 6C.1 (REQUIRED before icon library selection):** Use Perplexity Sonar Pro to verify the recommended icon library is actively maintained: "[Icon library name] maintenance status 2025 2026 — last release, open issues, tree-shaking support, React compatibility." If the library hasn't had a release in 12+ months or has 100+ unresolved issues, recommend an alternative.
- **Research point 6C.2 (REQUIRED before icon library selection):** Use Grok to check developer sentiment: "What are developers saying about [icon library name] for React projects?" Look for complaints about bundle size, missing icons, breaking changes, or migration away from the library. If sentiment is negative, surface the concerns and recommend an alternative before proceeding.
- Define the icon system: which library (Lucide, Heroicons, Phosphor, etc.), size conventions (16px inline, 20px in buttons, 24px standalone), stroke width. Selection must be informed by research points 6C.1 and 6C.2 above. Confirm coverage for all needed icons and tree-shakeability.
- Image handling: default avatar (initials in deterministic colored circle), placeholder images, recommended aspect ratios, optimization via `next/image` (WebP, responsive sizing, lazy loading).
- Illustration style for empty states, error pages, onboarding: text-only (Day Zero) vs. SVG illustrations (target). Define both.
- Logo/branding: if applicable, usage rules — minimum size, clear space, favicon dimensions (16×16, 32×32, 180×180, 512×512), Open Graph image (1200×630).

**16. Design System Governance** 🎯
- Rules for extending the system without breaking consistency:
  - **Reuse vs. create:** Check existing components before creating new ones. New components follow the same specification format.
  - **Token discipline:** All visual properties reference design tokens, never hardcoded values. Ensures consistency, changeability, and dark mode readiness.
  - **Naming conventions:** Components named by function ("ActionConfirmationDialog"), tokens by role ("color-primary" not "color-blue"), variants by purpose ("button-destructive" not "button-red").
  - **Component documentation:** Every new component needs: visual spec, all states, accessibility requirements, responsive behavior, usage example.
  - **Design debt tracking:** Deviations logged with: what was done, what should have been done, reconciliation plan.

**17. Founder Review and Design System Approval** 🤝
- Present the complete design system as a narrative walkthrough using a specific user journey:
  - "Imagine a new user named Sarah. She clicks 'Sign up' and sees [describe form]. After signing up, she lands on [describe onboarding]. She creates her first project by [describe flow]. Her dashboard now shows [describe populated state]. She invites a colleague by [describe invitation]. The next day, she sees a notification [describe notification]."
- Walk through the notification system, error experience, and settings page.
- Confirm founder satisfaction with: visual direction, interaction patterns, accessibility approach, notification system, voice and tone, onboarding flow.
- Identify design decisions depending on open questions from earlier phases.
- Flag areas needing expansion for Phase 2/Future features.
</phase_conversation_structure>

<!-- CONVERSATION_END -->
<!-- SYNTHESIS_START: Phase 1B app may load only from this point forward during synthesis mode -->

<phase_completion_gate>
**6C Sub-Phase Gate — all must be satisfied before synthesis:**

- [ ] **Interaction patterns fully specified with mobile alternatives.** Confirmations by severity, feedback patterns, drag-and-drop with keyboard alternative (if applicable), keyboard shortcuts with discoverability (if applicable), real-time update rendering (if applicable). Every hover-dependent pattern has a touch alternative. Mobile-specific patterns documented.
- [ ] **Microcopy and content strategy defined.** Platform voice (approved by founder), tone scale by context, microcopy patterns for all common interactions, content formatting rules.
- [ ] **Dark mode addressed.** Either fully designed with separate contrast verification table, or documented as future capability with confirmed token architecture supporting theme swapping.
- [ ] **Multi-tenant theming addressed (if applicable).** Themeable vs. fixed tokens identified, minimum theming surface documented.
- [ ] **Asset and resource specification complete.** Icon library (verified current, coverage confirmed), image handling, illustration approach, logo/favicon/social sharing specs (if applicable).
- [ ] **Design system governance rules defined.** Reuse-vs-create framework, token discipline, naming conventions, component documentation requirements, design debt tracking.
- [ ] **Founder has reviewed and approved the design direction.** Visual identity, interaction patterns, accessibility, voice and tone, notifications, onboarding confirmed.

**Full Phase 6 Final Verification — all 6A + 6B + 6C gates must be satisfied:**

- [ ] Component library validated (6A)
- [ ] Complete color palette with a11y verification (6A)
- [ ] Typography scale defined (6A)
- [ ] Spacing system defined (6A)
- [ ] Supporting tokens defined (6A)
- [ ] Every core component specified with all states (6A)
- [ ] Form design and validation patterns specified (6A)
- [ ] Accessibility baseline established with current standards (6A)
- [ ] Layout architecture defined for all breakpoints (6B)
- [ ] Navigation architecture fully specified (6B)
- [ ] Complete page inventory produced (6B)
- [ ] Page-level design patterns for every page type (6B)
- [ ] Error and system pages designed (6B)
- [ ] Onboarding and first-run experience designed (6B)
- [ ] Notification design system complete (6B)
- [ ] Data visualization patterns defined if applicable (6B)
- [ ] Search experience designed if applicable (6B)
- [ ] Interaction patterns with mobile alternatives (6C)
- [ ] Microcopy and content strategy (6C)
- [ ] Dark mode addressed (6C)
- [ ] Multi-tenant theming addressed if applicable (6C)
- [ ] Asset and resource specification (6C)
- [ ] Design system governance (6C)
- [ ] Design patterns informed by category research (6A+6B)
- [ ] All research points executed: 6.1, 6.3 (HIGH), 6.2, 6.4 (ENRICHMENT)
- [ ] Founder review and approval (6C)
- [ ] D-55 running ledger complete across all three sub-phases
</phase_completion_gate>

<phase_outputs>
When the full Phase 6 completion gate is satisfied, synthesize the following deliverables. These form the visual, interaction, and content specification layer that, combined with Phases 4–5, gives a development team everything needed to build the frontend without making subjective decisions.

**Deliverable 7: UI/UX Decision Record**

The complete design system specification. This is the single document that answers "how does this platform look, feel, behave, and speak?"

**Section 1 — Design Philosophy and Visual Identity**
The design philosophy in 2-3 sentences. Visual direction rationale. Reference platforms. The "feel" articulated in both designer and founder language.

**Section 2 — Design Tokens**
Complete token set: color palette (every value with hex, Tailwind class, usage — including data visualization palette), contrast verification table, typography scale, spacing scale, border radius, shadows, transitions (with prefers-reduced-motion), z-index layering. Presented as an implementable reference table.

**Section 3 — Component Specifications**
Every core component: visual specification, all states, accessibility requirements, responsive behavior, usage guidelines. Organized by category: buttons → inputs → data display → feedback → navigation → overlays.

**Section 4 — Form Design and Validation Patterns**
Validation strategy (real-time + on-submit), message standards, form layouts, field-specific patterns, unsaved changes handling.

**Section 5 — Layout Architecture**
Shell layout, content patterns, grid system, navigation architecture with role-conditional and feature-gated variations, responsive breakpoints.

**Section 6 — Complete Page Inventory**
Verbatim copy of the Phase 6B page inventory table, reproduced in full so D7 is self-contained. Every screen with URL route, layout, components, role visibility, priority tier. Phase 7 should load D7's Section 6 via the D7 manifest rather than re-loading all of 6B.

**Section 7 — Page Design Patterns**
Every major page type and error/system page with layout, component inventory, all state variations, role variations, loading transitions.

**Ambient research budget for Phase 6C:** 1-2 ambient research queries expected — typically for verifying animation performance best practices or checking microcopy conventions in the founder's industry.

**Section 8 — Onboarding and First-Run Experience**
Post-signup flow, setup wizard, empty states for every page, progressive disclosure, checklist, contextual help, demo data.

**Section 9 — Notification Design System**
Taxonomy, toast design, notification center, badges, email mapping, preference controls.

**Section 10 — Data Visualization Patterns (if applicable)**
Chart library, color palette, type conventions, interactions, responsive behavior, accessibility.

**Section 11 — Search Experience Design (if applicable)**
Input placement, behavior, results layout, empty/no-results, mobile adaptation.

**Section 12 — Interaction Patterns**
Confirmations by severity, feedback patterns, inline editing, drag-and-drop with keyboard alternatives, keyboard shortcuts, real-time updates, mobile-specific patterns.

**Section 13 — Microcopy and Content Strategy**
Voice definition, tone scale, microcopy patterns for all interactions, content formatting rules.

**Section 14 — Accessibility Specification**
Target standard, contrast verification tables (light + dark), focus management, touch targets, screen reader requirements, keyboard navigation map, motion policy, color independence verification, testing checklist. This section feeds directly into D14.

**Section 15 — Dark Mode and Theming**
Dark mode design or future-ready token architecture. Multi-tenant theming surface if applicable.

**Section 16 — Asset Inventory**
Icon library, image handling, illustration approach, logo/favicon/social sharing.

**Section 17 — Design System Governance**
Reuse-vs-create, token discipline, naming conventions, documentation requirements, design debt tracking.

**Section 18 — Design Decision Records**
Structured log of every significant design decision: decision, alternatives considered (with research findings), reasoning, tradeoffs, reconsideration conditions. Connected to D-N format.

---

**Deliverable 14: Accessibility Compliance Spec** *(D-59)*

A standalone accessibility specification extracted and expanded from D7 Section 14. While D7 Section 14 documents the accessibility decisions, D14 is the implementation-ready checklist the development team uses during every build card. D14 exists separately because:
1. Development teams reference it during every feature implementation, not just when reading the full design system
2. It serves as the audit document when the platform needs accessibility certification
3. It's the document shown to enterprise clients who require accessibility compliance documentation

**D14 Section 1 — Standard and Scope**
WCAG version and conformance level (confirmed current via research in 6A). Legal context. Scope of compliance (all pages, all features, all user-facing content).

**D14 Section 2 — Color and Visual Accessibility**
- Complete contrast verification table (light mode): every text/background pairing with exact ratio and pass/fail
- Complete contrast verification table (dark mode, if applicable): same format
- Color independence verification: every element using color to convey meaning, with its non-color alternative documented
- Data visualization color-blind safety: palette, pattern/shape differentiation for each series

**D14 Section 3 — Component-Level Accessibility Checklist**
For every component in the design system (from D7 Section 3):
- Required ARIA attributes (with exact attribute names and values)
- Keyboard interaction pattern (which keys do what)
- Focus management rules (focus order, focus trap if applicable, focus return)
- Screen reader announcements (what's announced, when, using which ARIA live region)
- Touch target compliance (size verification, padding adjustments if needed)

**D14 Section 4 — Page-Level Accessibility Requirements**
For every page in the page inventory (from D7 Section 6):
- Heading hierarchy (h1 → h2 → h3 structure)
- Landmark regions (<nav>, <main>, <aside>, <footer>)
- Page title (what the <title> element reads on each route)
- Skip-to-content link target
- Dynamic content announcements (any ARIA live regions on the page)

**D14 Section 5 — Form Accessibility**
- Label association for every form field
- Error announcement strategy (inline messages + summary banner)
- Required field indication (ARIA + visual)
- Multi-step wizard keyboard navigation
- Auto-save confirmation announcements

**D14 Section 6 — Navigation Accessibility**
- Tab order documentation for the shell layout
- Sidebar keyboard navigation (arrow keys, Enter to activate)
- Mobile navigation accessibility (hamburger menu, bottom tabs)
- Breadcrumb navigation (ARIA breadcrumb role)

**D14 Section 7 — Motion and Animation Policy**
- Global prefers-reduced-motion implementation
- Per-component overrides (which animations reduce vs. eliminate)
- Auto-playing content policy (no auto-play without user control)

**D14 Section 8 — Testing Protocol**
- **Automated testing:** Recommended tools (axe-core, Lighthouse accessibility audit), integration into CI/CD pipeline, minimum passing score
- **Manual testing checklist:** Keyboard-only navigation walkthrough, screen reader testing (VoiceOver on Mac, NVDA on Windows), browser zoom to 200%, color-blind simulation
- **Testing frequency:** Every pull request (automated), every sprint (manual keyboard), every release (full manual audit)

**D14 Section 9 — Remediation Process**
- How accessibility issues are categorized (critical: blocks access, major: significantly impairs, minor: inconvenient)
- SLA for each category (critical: fix before deployment, major: fix within sprint, minor: fix within quarter)
- How exceptions are documented if a standard cannot be met (with justification and alternative access method)

---

**Additional Artifacts Updated:**
- **GLOSSARY.md** — Updated with design and accessibility terminology introduced during this phase.
- **Risk & Assumption Registry** — Updated with design risks (e.g., "Text-based specification may not capture visual nuances — first build sprint should include visual review") and assumptions (e.g., "Assuming the founder's visual preferences are stable after Phase 6 approval").
- **ANALYTICS-EVENT-CATALOG.md** — Updated with UI-level events worth tracking (e.g., "Onboarding checklist completion rate", "Dark mode toggle usage", "Search usage frequency").

---

**Cross-Reference Manifests (D-60 format)**

**D7 Manifest — append after D7 synthesis:**
```
<!-- D7-MANIFEST-START -->
manifest:
  deliverable: D7
  phase: 6
  version: 1
  generated: [ISO timestamp]

exports:
  pages:
    - route: "[/path]"
      name: "[Screen Name]"
      layout: "[layout pattern]"
      roles: ["role1", "role2"]
      tier: "[MVP|Phase2|Future]"
  page_count: [total]
  public_routes: # List of routes accessible without authentication — for D15 SEO verification
    - "[/path]"
  authenticated_routes: # List of routes requiring login
    - "[/path]"
  consent_ui: # UI locations for privacy/consent mechanisms — for D12 verification
    cookie_consent: "[route or component where cookie consent appears]"
    privacy_settings: "[route where users manage privacy preferences]"
    terms_acceptance: "[route or flow where terms are accepted]"
  component_library: "[name@version]"
  color_primary: "[hex]"
  color_secondary: "[hex]"
  font_family: "[family name]"
  a11y_standard: "[WCAG version] Level [AA/AAA]"
  icon_library: "[name]"
  chart_library: "[name or N/A]"
  notification_types: ["transient", "persistent", "stored", "badge"]
  voice_description: "[2-3 word voice summary]"

imports:
  - D3: "features → screens, feature tiers → page priority"
  - D4: "entities → page/navigation groupings"
  - D5: "auth_method → auth flow screens, services → integration UIs"

references_in:
  - D14: "accessibility requirements flow from design tokens and components"
  - D15: "SEO spec references page routes and meta descriptions"
  - D17: "email templates follow color palette and typography"
  - D20: "maintenance playbook references design system governance"
<!-- D7-MANIFEST-END -->
```

**D14 Manifest — append after D14 synthesis:**
```
<!-- D14-MANIFEST-START -->
manifest:
  deliverable: D14
  phase: 6
  version: 1
  generated: [ISO timestamp]

exports:
  wcag_version: "[version]"
  conformance_level: "[AA/AAA]"
  contrast_pairs_verified: [count]
  contrast_failures: [count, should be 0]
  components_with_a11y_spec: [count]
  pages_with_a11y_spec: [count]
  keyboard_shortcuts_defined: [count]
  focus_indicator_style: "[CSS specification]"
  testing_tools: ["tool1", "tool2"]

imports:
  - D7: "design tokens → contrast requirements, components → ARIA specs, pages → heading structure"

references_in:
  - D9: "accessibility testing tool credentials"
  - D18: "monitoring includes accessibility regression alerts"
  - D20: "maintenance includes accessibility audit schedule"
<!-- D14-MANIFEST-END -->
```
</phase_outputs>

<!-- EOF: phase-6c-interaction-synthesis.md -->
