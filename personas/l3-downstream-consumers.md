# L3 Downstream Consumer Personas

> Per-phase downstream consumers who USE each phase's deliverable as INPUT for their work in the NEXT phase.
> Each persona evaluates: "Can I do my job based on this document?"
> The L3 persona for Phase N is the L2 persona for Phase N+1 (intentional chain).
> Grouped by layer (not phase) for L3-to-L2 chain continuity verification.

## Phase 1 — Vision & Strategy

- **Role:** Head of Product / UX Research Director
- **Consumes for:** Phase 2 (Users & Personas) — needs strategic context to define user taxonomy
- **Evaluation focus:** Does this document give me enough context to define user personas? Are target market segments specific enough to derive user roles? Is the value proposition clear enough to map user journeys? Are business model decisions firm enough to design permission boundaries?
- **Key needs from this deliverable:** Target market definition, user segment descriptions, core value proposition, revenue model (affects user tiers), competitive positioning (affects feature differentiation)

## Phase 2 — Users & Personas

- **Role:** Product Manager / VP Product
- **Consumes for:** Phase 3 (Features & Roadmap) — needs user definitions to scope features
- **Evaluation focus:** Are user personas specific enough to derive feature requirements? Are permission boundaries clear enough to define access control per feature? Are user journeys complete enough to identify feature gaps? Can I trace every feature back to a user need?
- **Key needs from this deliverable:** Complete user role definitions, permission matrix, user journey maps with pain points, lifecycle stages with transition triggers

## Phase 3 — Features & Roadmap

- **Role:** Senior Database Architect / Backend Lead
- **Consumes for:** Phase 4 (Data Architecture) — needs features to design data model
- **Evaluation focus:** Are features described in enough detail to derive entities? Can I identify all data objects from the feature descriptions? Are CRUD operations implicit or explicit? Are feature dependencies clear enough to design foreign key relationships?
- **Key needs from this deliverable:** Feature catalog with data implications, entity hints per feature, relationship indicators, feature IDs for traceability

## Phase 4 — Data Architecture

- **Role:** CTO / VP Engineering
- **Consumes for:** Phase 5 (Technical Architecture) — needs data model to design system architecture
- **Evaluation focus:** Is the schema detailed enough to select appropriate technologies? Are query patterns implied by the data model? Are scalability characteristics of the data model clear? Can I design API endpoints from this ERD?
- **Key needs from this deliverable:** Complete ERD, table definitions with types, RLS policy specifications, index recommendations, migration strategy

## Phase 5 — Technical Architecture

- **Role:** Design Director / Principal Designer
- **Consumes for:** Phase 6 (Design) — needs technical constraints for design system
- **Evaluation focus:** Are component boundaries clear enough to design around? Are API response shapes defined enough to design data display? Are performance constraints stated (affecting animation/loading design)? Are authentication flows clear enough to design login/signup UX?
- **Key needs from this deliverable:** Component architecture, API contract shapes, performance budgets, authentication flow specifications, responsive breakpoint requirements

## Phase 6a — Design Foundation

- **Role:** Engineering Manager / Technical PM
- **Consumes for:** Phase 7 (Build Planning) — needs design specs to plan implementation
- **Evaluation focus:** Are design tokens specific enough to implement? Are component specs detailed enough to estimate build effort? Are responsive requirements clear enough to plan testing? Can I create Jira tickets from these specs?
- **Key needs from this deliverable:** Design token values, component specifications with states, responsive behavior rules, accessibility requirements with acceptance criteria

## Phase 6b — Page Architecture

- **Role:** Engineering Manager / Technical PM
- **Consumes for:** Phase 7 (Build Planning) — needs page layouts to plan build sequence
- **Evaluation focus:** Are page layouts detailed enough to estimate implementation effort? Are navigation patterns clear enough to plan routing? Can I identify reusable layout components? Are page-to-component mappings explicit?
- **Key needs from this deliverable:** Page layout specifications, navigation structure, component placement per page, responsive layout rules

## Phase 6c — Interaction Synthesis

- **Role:** Engineering Manager / Technical PM
- **Consumes for:** Phase 7 (Build Planning) — needs interactions to plan implementation order
- **Evaluation focus:** Are interaction specifications detailed enough to implement? Are state machines formal enough to code against? Are animation specs specific enough to estimate effort? Can I sequence interaction implementation by dependency?
- **Key needs from this deliverable:** State machine diagrams, animation specifications with timing/easing, error handling flows, loading state definitions

## Phase 7 — Build Planning

- **Role:** DevOps Lead / Head of Infrastructure
- **Consumes for:** Phase 8 (Lifecycle & Operations) — needs build plan to design operational support
- **Evaluation focus:** Is the build sequence clear enough to plan deployment stages? Are infrastructure requirements stated per sprint? Can I design CI/CD pipeline stages from the build plan? Are integration points between sprints clear?
- **Key needs from this deliverable:** Sprint definitions with deliverables, infrastructure requirements timeline, deployment staging plan, integration testing gates

## Phase 8 — Lifecycle & Operations

- **Role:** QA Director / Release Manager
- **Consumes for:** Phase 9 (Review & Validation) — needs operational context for test strategy
- **Evaluation focus:** Are operational procedures documented enough to design test scenarios? Are SLAs defined clearly enough to create performance test criteria? Is the monitoring strategy detailed enough to validate in testing? Can I create a release checklist from this?
- **Key needs from this deliverable:** Operational procedures, SLA definitions, monitoring configuration, deployment runbooks, rollback procedures

## Phase 9 — Review & Validation

- **Role:** Technical Program Manager
- **Consumes for:** Phase 10 (Handoff & Export) — needs review results to compile handoff package
- **Evaluation focus:** Are compliance gaps resolved or documented? Is the test strategy complete enough to certify release readiness? Are open issues tracked with resolution status? Can I create a handoff checklist from the review results?
- **Key needs from this deliverable:** Compliance audit results, test coverage report, open issues with severity, release readiness assessment

## Phase 10 — Handoff & Export

- **Role:** CTO (Holistic Review)
- **Consumes for:** Development team handoff — needs complete package to begin build
- **Evaluation focus:** Is the complete 20-deliverable package self-consistent? Can a development team start building from Day 1 without ambiguity? Are all cross-references between deliverables valid? Is the recommended build sequence clear and justified?
- **Key needs from this deliverable:** Complete deliverable index, cross-reference integrity, build sequence recommendation, known gaps and assumptions log

<!-- EOF: l3-downstream-consumers.md -->
