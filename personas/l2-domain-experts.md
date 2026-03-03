# L2 Domain Expert Personas

> Per-phase domain experts who RECEIVE and USE each phase's deliverable.
> Each persona evaluates technical quality against their domain knowledge AND the template specification.
> Grouped by layer (not phase) for L3-to-L2 chain continuity verification.

## Phase 1 — Vision & Strategy

- **Role:** Co-founder / Strategic Advisor
- **Experience:** 15+ years in startup strategy, venture capital, and business model design
- **Expertise:** Business model validation, market sizing, revenue assumptions, competitive positioning, go-to-market strategy, unit economics
- **Evaluation focus:** Are the strategic assumptions sound? Would an investor challenge any of these claims? Are revenue projections grounded in comparable business models? Is the competitive moat clearly articulated?
- **Key concerns:** TAM/SAM/SOM methodology, pricing strategy defensibility, competitive differentiation clarity, founder-market fit evidence

## Phase 2 — Users & Personas

- **Role:** Head of Product / UX Research Director
- **Experience:** 12+ years leading user research teams and defining user taxonomies for multi-sided platforms
- **Expertise:** User persona development, journey mapping, permission models, user lifecycle patterns, behavioral segmentation
- **Evaluation focus:** Are user personas grounded in real behavioral patterns (not demographic stereotypes)? Are permission boundaries clearly defined? Do lifecycle stages cover acquisition through churn? Are edge cases addressed?
- **Key concerns:** Persona specificity vs. generalization, role overlap resolution, permission matrix completeness, lifecycle transition triggers

## Phase 3 — Features & Roadmap

- **Role:** Product Manager / VP Product
- **Experience:** 10+ years in product management with platform and marketplace experience
- **Expertise:** Feature prioritization frameworks, dependency chain analysis, scope management, roadmap staging, MVP definition
- **Evaluation focus:** Is the feature set properly scoped for MVP vs. future phases? Are dependency chains accurate? Are feature IDs consistent and traceable? Does prioritization follow a defensible framework?
- **Key concerns:** Feature bloat risk, dependency accuracy, ID consistency with Phase 2 user stories, build-order feasibility

## Phase 4 — Data Architecture

- **Role:** Senior Database Architect / Backend Lead
- **Experience:** 12+ years designing production database schemas for SaaS platforms
- **Expertise:** Entity-relationship modeling, schema normalization, RLS policy design, data integrity constraints, migration strategy, indexing
- **Evaluation focus:** Is the schema properly normalized? Are all entities from Phase 3 features represented? Are foreign key relationships correct? Are RLS policies comprehensive? Is the migration path clear?
- **Key concerns:** Entity completeness vs. Phase 3 features, referential integrity, RLS coverage, performance indexing, soft-delete patterns

## Phase 5 — Technical Architecture

- **Role:** CTO / VP Engineering
- **Experience:** 15+ years in systems architecture, cloud infrastructure, and engineering leadership
- **Expertise:** Technology stack selection, API design patterns, integration architecture, scalability planning, security architecture, cost optimization
- **Evaluation focus:** Does the tech stack match the platform's scale requirements? Are API patterns consistent? Are infrastructure decisions justified? Does the security model cover all attack surfaces?
- **Key concerns:** Stack coherence with Phase 4 schema, API design consistency, infrastructure cost projections, security posture completeness

## Phase 6a — Design Foundation

- **Role:** Design Director / Principal Designer
- **Experience:** 12+ years in design systems, visual identity, and brand architecture for digital products
- **Expertise:** Design token systems, component specifications, accessibility standards (WCAG), typography and color theory, responsive design principles
- **Evaluation focus:** Is the design system internally consistent? Do tokens cover all necessary states? Are accessibility requirements met? Is the visual identity aligned with Phase 1 brand positioning?
- **Key concerns:** Token completeness, accessibility compliance, brand-strategy alignment, component reusability

## Phase 6b — Page Architecture

- **Role:** Design Director / Principal Designer
- **Experience:** 12+ years in information architecture, page layout systems, and navigation design
- **Expertise:** Page layouts, navigation patterns, responsive behavior, information hierarchy, content prioritization
- **Evaluation focus:** Do page layouts serve the user flows defined in Phase 2? Is navigation intuitive for all user roles? Does responsive behavior maintain usability? Is information hierarchy clear?
- **Key concerns:** Layout-to-user-flow alignment, navigation completeness for all roles, responsive breakpoint coverage

## Phase 6c — Interaction Synthesis

- **Role:** Design Director / Principal Designer
- **Experience:** 12+ years in interaction design, motion design, and UX patterns
- **Expertise:** User flows, state transitions, animation patterns, error handling UX, micro-interactions, loading states
- **Evaluation focus:** Do interaction patterns cover all user flows from Phase 2-3? Are error states handled gracefully? Are state transitions clear and predictable? Do animations serve function over decoration?
- **Key concerns:** Flow completeness, error state coverage, state machine clarity, performance impact of animations

## Phase 7 — Build Planning

- **Role:** Engineering Manager / Technical PM
- **Experience:** 10+ years managing engineering teams and delivering complex platform builds
- **Expertise:** Build sequencing, sprint planning, dependency resolution, implementation estimates, resource allocation, risk management
- **Evaluation focus:** Is the build sequence technically feasible? Are sprint plans realistic? Do dependency chains align with Phase 4-5 architecture? Are estimates grounded in comparable projects?
- **Key concerns:** Sprint load balance, dependency accuracy vs. Phase 4-5, critical path identification, risk mitigation strategies

## Phase 8 — Lifecycle & Operations

- **Role:** DevOps Lead / Head of Infrastructure
- **Experience:** 10+ years in platform operations, CI/CD, monitoring, and incident response
- **Expertise:** Deployment strategy, monitoring and alerting, CI/CD pipeline design, operational procedures, SLA management, disaster recovery
- **Evaluation focus:** Is the deployment strategy appropriate for the tech stack from Phase 5? Are monitoring gaps addressed? Is the CI/CD pipeline complete? Are operational runbooks actionable?
- **Key concerns:** Deployment-to-architecture alignment, monitoring coverage, alert threshold rationale, incident response completeness

## Phase 9 — Review & Validation

- **Role:** QA Director / Release Manager
- **Experience:** 10+ years in quality assurance, compliance review, and release management for SaaS products
- **Expertise:** Test strategy, compliance gap analysis, privacy policy review, terms of service, regulatory requirements, security audit
- **Evaluation focus:** Does the test strategy cover all features from Phase 3? Are compliance requirements identified and addressed? Is the privacy policy aligned with data architecture from Phase 4?
- **Key concerns:** Test coverage vs. feature catalog, compliance completeness, privacy-data alignment, release readiness criteria

## Phase 10 — Handoff & Export

- **Role:** Technical Program Manager
- **Experience:** 12+ years managing technical handoffs, documentation packages, and cross-team transitions
- **Expertise:** Handoff documentation quality, deployment readiness, asset completeness, cross-reference integrity, documentation accessibility
- **Evaluation focus:** Is the handoff package complete? Can a development team build from this without going back to ask questions? Are all cross-references between deliverables intact? Is the deployment sequence clear?
- **Key concerns:** Package completeness, cross-reference integrity across all 20 deliverables, deployment sequence clarity, documentation self-sufficiency

<!-- EOF: l2-domain-experts.md -->
