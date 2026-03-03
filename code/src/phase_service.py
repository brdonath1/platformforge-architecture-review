"""
PlatformForge Orchestrator — Phase Service (phase_service.py)

Executes a single phase: conversation + synthesis + fact extraction.

Owns: Guide-Founder conversation loop, deliverable generation,
prior deliverable loading, founder memory management, fact extraction.

Does NOT own: review pipeline (Step 6), cross-phase orchestration (Step 7),
GitHub publishing (RunStore).

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.6 Step 5
"""

from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timezone

from .contracts import (
    CanonicalFact,
    MessageJob,
    MessageResult,
    PhaseKey,
    PhaseOutcome,
    PhaseResult,
    PhaseTemplateSpec,
    RoleName,
)
from .llm_gateway import AnthropicGateway
from .run_store import CostLedger, RunStore, StateRegistry
from .settings import AppConfig
from .template_parser import load_phase_template, parse_phase_template

logger = logging.getLogger("platformforge.phase_service")


# ---------------------------------------------------------------------------
# 5.1.1 Completion Markers
# ---------------------------------------------------------------------------

GUIDE_COMPLETE_MARKER: str = "[READY_FOR_SYNTHESIS]"
FOUNDER_COMPLETE_MARKER: str = "[PHASE_COMPLETE]"


# ---------------------------------------------------------------------------
# 5.1.2 Guide Simulation Preamble
# ---------------------------------------------------------------------------

GUIDE_PREAMBLE: str = """<simulation_context>
IMPORTANT — READ BEFORE PROCEEDING:

You are running inside an automated methodology validation simulation. The "founder" you are
speaking with is another AI playing the role of Rafael Delgado, founder of Ocean Golf (a luxury
golf concierge platform in Cabo San Lucas). Treat them as you would a real founder — ask probing
questions, challenge assumptions, surface risks, expand their thinking.

BEHAVIORAL ADJUSTMENTS FOR THIS SIMULATION:
1. Use the web_search tool for all live research instead of Perplexity, Grok, or Deep Research
   (those engines are not available). The web_search tool is your only research tool.
2. Skip any instructions about phone calls, voice mode, or Retell AI — this is text-only.
3. When you believe the phase conversation is complete and you are ready to move to deliverable
   synthesis, include the marker [READY_FOR_SYNTHESIS] at the END of your final message.
4. Follow the phase template's conversation structure and completion gates rigorously.
5. Do not rush — explore each conversation area thoroughly before moving to the next.
6. The founder will confirm phase completion with [PHASE_COMPLETE] — wait for this before ending.
</simulation_context>

"""


# ---------------------------------------------------------------------------
# 5.1.3 Synthesis Preamble
# ---------------------------------------------------------------------------

SYNTHESIS_PREAMBLE: str = """<role>
You are a professional document generation engine for PlatformForge, an AI-guided
platform planning service. Your sole task is to produce complete, publication-ready
deliverable documents from completed phase conversations.

You are NOT a conversation agent. You do not discuss, summarize, or explain.
You generate the full deliverable document as specified in the synthesis template below.
</role>

<generation_rules>
1. Produce the COMPLETE deliverable with every section specified in the template.
   A table of contents, summary, or index is NOT a deliverable — the actual content is.
2. Every required section must contain substantive prose content, not placeholders or stubs.
3. Include all appendices, manifests, and structured data specified in the template.
4. Use evidence from the conversation transcript and research data provided.
   Quote specific data points (market sizes, competitor names, pricing) from the research.
5. The deliverable must be self-contained — a reader who was not in the conversation
   should fully understand the platform's vision from this document alone.
6. Output as a complete markdown document beginning with a level-1 heading (#).
7. Do not include preamble text like "I'll now generate..." — start directly with the document.
8. Do not truncate or abbreviate any section. If you are running out of output space,
   prioritize completing the current section fully before starting the next.
</generation_rules>
"""


# ---------------------------------------------------------------------------
# 5.1.4 Phase Openings
# ---------------------------------------------------------------------------

PHASE_OPENINGS: dict[str, str] = {
    "1": "Hello! I'm here to plan my software platform. I'm excited to start from the very beginning — let's define the vision and strategy.",
    "2": "We've finished defining the platform vision and strategy. Now I'd like to work on the user roles and personas — who will actually use this platform.",
    "3": "We've mapped out the vision and user roles. Now I'm ready to define the features and prioritize what gets built first.",
    "4": "The vision, users, and features are all defined. Let's work on the data model — the entities, relationships, and structure behind the scenes.",
    "5": "We've completed vision, users, features, and data modeling. Now let's tackle the technical architecture — the technology stack and infrastructure.",
    "6a": "The core technical planning is done. Let's move into design — starting with the design foundation: colors, typography, and the component system.",
    "6b": "The design foundation is set. Now let's define the page architecture — every page, its layout, navigation, and content structure.",
    "6c": "Design foundation and page architecture are done. Let's bring it all together with the interaction patterns and UX flows.",
    "7": "All the design and technical planning is complete. Let's build the implementation roadmap — what gets built when, and in what order.",
    "8": "The build plan is ready. Now let's define how this platform will run in production — deployment, monitoring, operations, and maintenance.",
    "9": "We've been through the entire planning process. Let's do a comprehensive review — cross-checking everything for consistency and completeness.",
    "10": "The review is complete. Let's finalize everything and prepare the deliverable package for handoff to the development team.",
}


# ---------------------------------------------------------------------------
# 5.1.5 Phase Navigation Preambles
# ---------------------------------------------------------------------------

PHASE_PREAMBLES: dict[str, str] = {
    "1": "PLATFORM VISION — Contains: platform name, market positioning, target audience, competitive landscape, founder background, core value proposition, business model, revenue strategy, key differentiators, and initial scope boundaries. Key references for downstream: platform identity, market context, pricing approach, competitive gaps to exploit.",
    "2": "USER ROLES & PERSONAS — Contains: all user roles with permissions and capabilities, detailed personas, user journey maps, onboarding flows, pain points, and success metrics. Key references for downstream: role names and IDs, permission matrices, journey stages, user-facing terminology.",
    "3": "FEATURES & PRIORITIES — Contains: complete feature registry with IDs, descriptions, priority rankings (P0-P3), user role assignments, acceptance criteria, and feature dependencies. Key references for downstream: feature IDs, MVP vs future scope, feature-to-role mappings, interaction requirements.",
    "4": "DATA MODEL & ARCHITECTURE — Contains: all entities with fields, types, relationships, constraints, indexes, validation rules, and data flow diagrams. Key references for downstream: entity names, field specifications, relationship cardinality, data validation rules, storage requirements.",
    "5": "TECHNICAL ARCHITECTURE — Contains: technology stack selections with rationale, infrastructure topology, API endpoint specifications, integration patterns, authentication/authorization design, third-party service selections, and performance targets. Key references for downstream: tech stack decisions, API contracts, vendor selections, architecture constraints, security model.",
    "6a": "DESIGN FOUNDATION — Contains: design system (colors, typography, spacing, component library), brand identity, accessibility standards, responsive breakpoints, and design tokens. Key references for downstream: design token values, component specifications, accessibility requirements, visual language.",
    "6b": "PAGE ARCHITECTURE — Contains: page inventory, wireframe specifications, navigation structure, layout patterns, content hierarchy, and URL structure. Key references for downstream: page names and routes, navigation model, layout templates, content zones.",
    "6c": "INTERACTION SYNTHESIS — Contains: interaction patterns, state transitions, animation specs, error handling UX, loading states, micro-interactions, and cross-page flows. Key references for downstream: interaction IDs, state machine definitions, error message catalog, UX flow sequences.",
    "7": "BUILD PLANNING — Contains: implementation roadmap, sprint/phase breakdown, dependency graph, MVP scope definition, resource estimates, and risk mitigations. Key references for downstream: build sequence, MVP feature set, dependency order, milestone definitions.",
    "8": "LIFECYCLE & OPERATIONS — Contains: deployment strategy, CI/CD pipeline, monitoring/alerting, scaling triggers, backup/recovery, support workflows, and maintenance procedures. Key references for downstream: infrastructure requirements, operational constraints, SLA targets, incident response procedures.",
    "9": "REVIEW & VALIDATION — Contains: cross-phase consistency audit, gap analysis, requirement traceability, risk assessment, and methodology feedback observations. Key references for downstream: identified gaps, unresolved issues, cross-reference verification results.",
    "10": "GITHUB PUSH & HANDOFF — Contains: final deliverable package manifest, repository structure, handoff documentation, and implementation notes. Key references for downstream: package inventory, delivery format.",
}


# ---------------------------------------------------------------------------
# 5.1.6 Research Adaptation Strings
# ---------------------------------------------------------------------------

_RESEARCH_SECTION_WEBSEARCH_ONLY: str = """<research_architecture>
**Orchestrator Research Mode — Web Search Only**

In this automated orchestrator environment, you have ONE research tool: `web_search`.
It is a general-purpose internet search engine. You do NOT have access to Perplexity Sonar,
Perplexity Deep Research, or Grok (X Search). Those engines are referenced in the production
methodology but are not available in this simulation.

**How to maximize web_search effectiveness:**
- You can use up to 3 web searches per response. Use all 3 when research matters.
- For service comparisons: search each candidate separately ("Supabase pricing 2026",
  "PlanetScale pricing 2026") rather than one combined query.
- For competitive analysis: search for each competitor individually.
- For technology recommendations: search for "[tool] reviews 2026" and "[tool] alternatives".
- You CANNOT do real-time developer sentiment analysis. When the methodology calls for a
  "sentiment check" or "Grok check", note this as a research gap in the deliverable:
  "\u26a0 SENTIMENT CHECK UNAVAILABLE: Developer sentiment for [tool] could not be verified via
  real-time social media search. Recommend manual verification before committing."

**What must ALWAYS be live research (never training knowledge):**
- Pricing for any service, tool, or API \u2014 prices change constantly
- Competitive landscape \u2014 new competitors launch, existing ones pivot or die
- Library and framework versions \u2014 what's current, what's deprecated
- Regulatory requirements \u2014 laws and standards get updated

**What CAN use training knowledge:**
- Architectural patterns, general UX best practices, fundamental security principles
- Software design patterns that are stable over years

**Staleness thresholds still apply.** When any phase loads data from a prior phase's
deliverable, check the research date against these limits: pricing (30d), competitive (60d),
library versions (90d), regulatory (180d). If stale, re-verify with web_search.

**Stale recommendation protocol** still applies \u2014 see methodology instructions for full details.
When live research reveals a prior phase recommendation has materially changed, present the
change to the founder and follow the update protocol.
</research_architecture>"""

_RESEARCH_SECTION_FULL: str = """<research_architecture>
**Orchestrator Research Mode \u2014 Full Research Stack**

You have access to multiple research tools in this orchestrator environment:

**web_search** (server-side, always available) \u2014 General-purpose internet search. Fast,
up to 3 queries per response. Good for quick factual lookups, pricing checks, and targeted
queries. This is your default for simple research needs.

**perplexity_search** (client-side tool) \u2014 Grounded search with citations via Perplexity
Sonar API. Use for: market sizing, industry trends, regulatory requirements, integration
ecosystems, multi-source comparisons, and any factual question where you need current data
with source attribution. Returns cited answers. Available models:
- "sonar" (default): Fast general-purpose search. Use for straightforward queries.
- "sonar-pro": Deep multi-source synthesis. Use for service comparisons, competitive analysis,
  and complex questions requiring multiple sources.

**grok_sentiment** (client-side tool) \u2014 Developer/community sentiment analysis via Grok (xAI)
with real-time X/Twitter data access. Use for: what developers, users, and the tech community
are saying about a specific tool, service, competitor, or technology. Catches things no other
engine can: recent outages, community backlash, migrations, excitement about new launches.
Use as a community health check before recommending any technology or service.

**Engine selection rules:**
- Quick factual lookup, single source \u2192 web_search
- Factual question needing citations \u2192 perplexity_search (sonar)
- Multi-source comparison or synthesis \u2192 perplexity_search (sonar-pro)
- Community sentiment, recent events, developer reactions \u2192 grok_sentiment
- Service or technology recommendation \u2192 perplexity_search for the comparison, then
  grok_sentiment for the sentiment check. Always both.

**What must ALWAYS be live research (never training knowledge):**
- Pricing for any service, tool, or API \u2014 prices change constantly
- Competitive landscape \u2014 new competitors launch, existing ones pivot or die
- Library and framework versions \u2014 what's current, what's deprecated
- Regulatory requirements \u2014 laws and standards get updated
- Community sentiment \u2014 a tool beloved last year may be in crisis today

**What CAN use training knowledge:**
- Architectural patterns, general UX best practices, fundamental security principles
- Software design patterns that are stable over years

When in doubt, research it live. Stale data that the founder trusts is more dangerous than
a knowledge gap that's clearly labeled.

**Staleness thresholds apply.** Pricing (30d), competitive (60d), library versions (90d),
regulatory (180d), community sentiment (45d). When a phase references data from a prior
phase, check the research date against these thresholds before relying on it.

**Synthesis reconciliation protocol.** When perplexity_search and grok_sentiment return
complementary but divergent signals, produce a unified assessment: "Factual comparison favors
X (Perplexity). Developer sentiment is mixed (Grok: [summary]). Recommendation: [decision
with reasoning]." Never silently discard one engine's findings.

**Stale recommendation protocol** still applies \u2014 see methodology instructions for full details.
</research_architecture>"""

_HARD_BOUNDARY_9_WEBSEARCH: str = (
    "9. **Flag when sentiment checks are unavailable.** Before recommending any third-party "
    "tool, service, or technology, attempt to verify current developer sentiment via web search. "
    "If web search results are insufficient for a sentiment assessment, explicitly flag this "
    "in the deliverable as a gap requiring manual verification."
)

_HARD_BOUNDARY_9_FULL: str = (
    "9. **Never recommend a service without a sentiment check.** Before recommending any "
    "third-party tool, service, or technology to the founder, use the grok_sentiment tool to "
    "check current developer sentiment. A tool with great documentation but a community in "
    "revolt is not a safe recommendation. The founder is trusting you with their technology "
    "stack \u2014 verify that trust is warranted."
)


# ---------------------------------------------------------------------------
# 5.5 Phase Order
# ---------------------------------------------------------------------------

PHASE_ORDER: list[PhaseKey] = [
    PhaseKey.P1, PhaseKey.P2, PhaseKey.P3, PhaseKey.P4, PhaseKey.P5,
    PhaseKey.P6A, PhaseKey.P6B, PhaseKey.P6C,
    PhaseKey.P7, PhaseKey.P8, PhaseKey.P9, PhaseKey.P10,
]


# ---------------------------------------------------------------------------
# Max synthesis continuations
# ---------------------------------------------------------------------------

_MAX_SYNTHESIS_CONTINUATIONS: int = 3


# ---------------------------------------------------------------------------
# PhaseService
# ---------------------------------------------------------------------------

class PhaseService:
    """Executes a single phase: conversation + synthesis + fact extraction.

    Owns the Guide-Founder conversation loop, deliverable generation,
    prior deliverable loading, and founder memory management.

    Does NOT own:
    - Review pipeline (Step 6)
    - Cross-phase orchestration (Step 7)
    - GitHub publishing (RunStore)
    """

    def __init__(
        self,
        gateway: AnthropicGateway,
        store: RunStore,
        state: StateRegistry,
        ledger: CostLedger,
        config: AppConfig,
        master_prompt: str,
        persona: str,
    ) -> None:
        self._gateway = gateway
        self._store = store
        self._state = state
        self._ledger = ledger
        self._config = config
        self._master_prompt = master_prompt
        self._persona = persona
        self._adapted_prompt: str | None = None

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def run_phase(
        self, phase: PhaseKey, max_exchanges: int = 75
    ) -> PhaseResult:
        """Execute a single phase: conversation + synthesis + fact extraction.

        Returns PhaseResult with outcome, deliverable, transcript, and facts.
        Does NOT run the review pipeline.
        """
        started_at = datetime.now(tz=timezone.utc).isoformat()
        phase_start = time.monotonic()

        logger.info("Starting phase %s", phase.value)

        # 1. Load and parse template
        template_root = self._store.templates_dir
        bundle = load_phase_template(template_root, phase)
        spec = parse_phase_template(bundle)

        # 2. Load prior deliverables
        prior_deliverables = self.load_prior_deliverables(phase)

        # 3. Get founder memory
        founder_memory = self._get_founder_memory(phase)

        # 4. Adapt master prompt
        adapted_prompt = self._adapt_master_prompt()

        # 5. Run conversation
        transcript = self._run_conversation(
            phase, spec, prior_deliverables, founder_memory,
            adapted_prompt, max_exchanges,
        )

        # 6. Run synthesis
        deliverable_text = self._run_synthesis(
            phase, spec, transcript, prior_deliverables, adapted_prompt,
        )

        # 7. Extract facts
        extracted_facts = self._extract_facts(phase, transcript)

        # 8. Update founder memory
        self._update_founder_memory(phase, deliverable_text)

        # 9. Build outcome
        elapsed = time.monotonic() - phase_start
        completed_at = datetime.now(tz=timezone.utc).isoformat()

        exchange_count = sum(
            1 for t in transcript if t.get("role") == "founder"
        )

        outcome = PhaseOutcome(
            phase=phase,
            status="completed",
            deliverable_path=str(
                self._store.deliverables_dir
                / f"deliverable-{phase.value}.md"
            ),
            conversation_path=str(
                self._store.conversations_dir
                / f"conversation-{phase.value}.json"
            ),
            exchange_count=exchange_count,
            deliverable_chars=len(deliverable_text),
            cost_usd=self._ledger.phase_summary(phase).get(
                "cost_usd", "0"  # type: ignore[arg-type]
            ),
            elapsed_seconds=elapsed,
            started_at=started_at,
            completed_at=completed_at,
        )

        logger.info(
            "Phase %s completed: %d exchanges, %d chars, %.1fs",
            phase.value, exchange_count, len(deliverable_text), elapsed,
        )

        return PhaseResult(
            outcome=outcome,
            deliverable_text=deliverable_text,
            transcript=transcript,
            extracted_facts=extracted_facts,
            template_spec=spec,
        )

    def load_prior_deliverables(self, phase: PhaseKey) -> str:
        """Load prior phase deliverables for context.

        Orders chronologically (oldest first, most recent last = strongest attention).
        Applies Haiku context budget (200K chars) if active model is Haiku.
        """
        # Find phases before the current one
        prior_phases: list[PhaseKey] = []
        for pk in PHASE_ORDER:
            if pk == phase:
                break
            prior_phases.append(pk)

        if not prior_phases:
            return ""

        # Determine context budget
        tier_name = self._config.runtime.active_tier
        tier = self._config.tiers.get(tier_name)
        is_haiku = tier is not None and "haiku" in tier.model.model_id
        max_chars = 200_000 if is_haiku else 0  # 0 = unlimited

        # Load deliverables with preambles
        entries: list[tuple[PhaseKey, str]] = []
        for pk in prior_phases:
            content = self._store.load_deliverable(pk)
            if content is None:
                logger.warning(
                    "Prior deliverable for phase %s not found, skipping",
                    pk.value,
                )
                continue
            preamble = PHASE_PREAMBLES.get(pk.value, "")
            entry = f"--- Phase {pk.value}: {preamble} ---\n\n{content}"
            entries.append((pk, entry))

        if not entries:
            return ""

        # Apply context budget (truncate oldest first)
        if max_chars > 0:
            total = sum(len(e) for _, e in entries)
            if total > max_chars:
                budget_remaining = max_chars
                # Reserve space for most recent entries first
                result_entries: list[str] = [""] * len(entries)

                # Allocate from most recent to oldest
                for i in range(len(entries) - 1, -1, -1):
                    entry_text = entries[i][1]
                    if len(entry_text) <= budget_remaining:
                        result_entries[i] = entry_text
                        budget_remaining -= len(entry_text)
                    elif budget_remaining > 0:
                        result_entries[i] = entry_text[:budget_remaining] + "\n\n[... truncated for context budget ...]"
                        budget_remaining = 0
                    else:
                        result_entries[i] = f"--- Phase {entries[i][0].value}: [truncated — context budget exceeded] ---"

                return "\n\n".join(e for e in result_entries if e)

        return "\n\n".join(e for _, e in entries)

    # -------------------------------------------------------------------
    # Private: Conversation
    # -------------------------------------------------------------------

    def _run_conversation(
        self,
        phase: PhaseKey,
        spec: PhaseTemplateSpec,
        prior_deliverables: str,
        founder_memory: str,
        adapted_prompt: str,
        max_exchanges: int,
    ) -> list[dict[str, object]]:
        """Run the Guide-Founder conversation loop."""
        # Build system prompts
        guide_system = (
            GUIDE_PREAMBLE + adapted_prompt
            + "\n\n---\n\n" + spec.conversation_instructions
        )
        if prior_deliverables:
            guide_system += (
                "\n\n<prior_deliverables>\n"
                + prior_deliverables
                + "\n</prior_deliverables>"
            )

        founder_system = self._persona
        if founder_memory:
            founder_system += (
                "\n\n<founder_memory>\n"
                + founder_memory
                + "\n</founder_memory>"
            )

        # Message histories (separate for each role)
        guide_messages: list[dict[str, object]] = []
        founder_messages: list[dict[str, object]] = []
        transcript: list[dict[str, object]] = []

        # 1. Founder opens
        opening = PHASE_OPENINGS.get(phase.value, "Let's continue.")
        transcript.append({"role": "founder", "text": opening})
        guide_messages.append({"role": "user", "content": opening})

        logger.info("Phase %s: founder opening sent", phase.value)

        guide_signaled_ready = False

        for exchange in range(1, max_exchanges + 1):
            # Guide responds
            guide_result = self._gateway.run(MessageJob(
                role=RoleName.GUIDE,
                phase=phase,
                label=f"P{phase.value} guide exchange {exchange}",
                system_prompt=guide_system,
                messages=list(guide_messages),
                tools=[{"type": "web_search_20250305", "name": "web_search"}],
            ))

            if guide_result.usage is not None:
                self._ledger.record(phase, guide_result.usage)

            guide_text = guide_result.text
            if not guide_text:
                guide_text = "[The guide is processing research results and will continue the conversation.]"

            # Build transcript entry with optional research data
            guide_entry: dict[str, object] = {"role": "guide", "text": guide_text}
            if guide_result.tool_use_blocks:
                research_parts: list[str] = []
                for tub in guide_result.tool_use_blocks:
                    research_parts.append(str(tub.get("input", "")))
                for trb in guide_result.tool_result_blocks:
                    research_parts.append(str(trb.get("content", "")))
                if research_parts:
                    guide_entry["research"] = "\n".join(research_parts)

            transcript.append(guide_entry)

            # Build full content blocks for message history
            guide_content_for_history = guide_text
            guide_messages.append({"role": "assistant", "content": guide_content_for_history})
            founder_messages.append({"role": "user", "content": guide_text})

            # Check for guide completion marker
            if GUIDE_COMPLETE_MARKER in guide_text:
                guide_signaled_ready = True

            # Founder responds
            founder_result = self._gateway.run(MessageJob(
                role=RoleName.FOUNDER,
                phase=phase,
                label=f"P{phase.value} founder exchange {exchange}",
                system_prompt=founder_system,
                messages=list(founder_messages),
                tools=[],
                thinking_budget=0,
            ))

            if founder_result.usage is not None:
                self._ledger.record(phase, founder_result.usage)

            founder_text = founder_result.text or "[No response]"
            transcript.append({"role": "founder", "text": founder_text})

            founder_messages.append({"role": "assistant", "content": founder_text})
            guide_messages.append({"role": "user", "content": founder_text})

            # Check for founder completion marker
            if FOUNDER_COMPLETE_MARKER in founder_text:
                logger.info(
                    "Phase %s: founder signaled completion at exchange %d",
                    phase.value, exchange,
                )
                break

            # Periodic partial save
            if exchange % 5 == 0:
                self._store.save_conversation(phase, transcript)
                logger.debug("Partial conversation save at exchange %d", exchange)

        else:
            logger.warning(
                "Phase %s: max exchanges (%d) reached without completion",
                phase.value, max_exchanges,
            )

        # Save final conversation
        self._store.save_conversation(phase, transcript)
        return transcript

    # -------------------------------------------------------------------
    # Private: Synthesis
    # -------------------------------------------------------------------

    def _run_synthesis(
        self,
        phase: PhaseKey,
        spec: PhaseTemplateSpec,
        transcript: list[dict[str, object]],
        prior_deliverables: str,
        adapted_prompt: str,
    ) -> str:
        """Generate deliverable from completed conversation."""
        synth_system = (
            SYNTHESIS_PREAMBLE + adapted_prompt
            + "\n\n---\n\n<synthesis_template>\n"
            + spec.synthesis_instructions
            + "\n</synthesis_template>"
        )

        # Build user message (attention-optimized order)
        conversation_text = self._build_conversation_text(transcript)
        parts: list[str] = []
        if prior_deliverables:
            parts.append(
                f"<prior_deliverables>\n{prior_deliverables}\n</prior_deliverables>"
            )
        parts.append(
            f"<completed_conversation>\n{conversation_text}\n</completed_conversation>"
        )
        parts.append(
            "The phase conversation above is complete. Generate the COMPLETE deliverable document "
            "as specified in the synthesis template in your system prompt. Produce every section with "
            "full substantive content \u2014 not a summary, not an index, not a table of contents. The "
            "actual document. Begin directly with the markdown heading. Do not include any preamble."
        )
        synth_message = "\n\n".join(parts)

        # Initial synthesis call
        result = self._gateway.run(MessageJob(
            role=RoleName.SYNTHESIS,
            phase=phase,
            label=f"P{phase.value} synthesis",
            system_prompt=synth_system,
            messages=[{"role": "user", "content": synth_message}],
            tools=[],
        ))

        if result.usage is not None:
            self._ledger.record(phase, result.usage)

        deliverable_text = result.text or ""

        # Handle truncation continuations
        continuation_messages: list[dict[str, object]] = [
            {"role": "user", "content": synth_message},
            {"role": "assistant", "content": deliverable_text},
        ]

        for cont in range(_MAX_SYNTHESIS_CONTINUATIONS):
            if result.stop_reason != "max_tokens":
                break

            logger.info(
                "Phase %s synthesis truncated, continuation %d/%d",
                phase.value, cont + 1, _MAX_SYNTHESIS_CONTINUATIONS,
            )

            continuation_messages.append({
                "role": "user",
                "content": (
                    "Your output was truncated. Please continue EXACTLY where you "
                    "left off. Do not repeat any content \u2014 pick up from the last "
                    "incomplete sentence or section."
                ),
            })

            result = self._gateway.run(MessageJob(
                role=RoleName.SYNTHESIS,
                phase=phase,
                label=f"P{phase.value} synthesis cont {cont + 1}",
                system_prompt=synth_system,
                messages=list(continuation_messages),
                tools=[],
            ))

            if result.usage is not None:
                self._ledger.record(phase, result.usage)

            cont_text = result.text or ""
            deliverable_text += cont_text
            continuation_messages.append({"role": "assistant", "content": cont_text})

        if result.stop_reason == "max_tokens":
            logger.warning(
                "Phase %s synthesis still incomplete after %d continuations",
                phase.value, _MAX_SYNTHESIS_CONTINUATIONS,
            )

        # Strip preamble
        deliverable_text = _strip_synthesis_preamble(deliverable_text)

        # Save deliverable
        self._store.save_deliverable(phase, deliverable_text)
        logger.info(
            "Phase %s synthesis complete: %d chars",
            phase.value, len(deliverable_text),
        )

        return deliverable_text

    # -------------------------------------------------------------------
    # Private: Fact Extraction
    # -------------------------------------------------------------------

    def _extract_facts(
        self, phase: PhaseKey, transcript: list[dict[str, object]]
    ) -> list[CanonicalFact]:
        """Extract canonical facts from conversation transcript."""
        transcript_text = self._build_conversation_text(transcript)

        prompt = (
            "Given the following phase conversation transcript, extract all concrete decisions, "
            "names, values, and commitments made by the founder. Return ONLY a JSON array of "
            "fact objects with these fields:\n"
            '- namespace: domain area (e.g., "pricing", "architecture", "naming", "users", "features")\n'
            '- subject: the entity (e.g., "platform", "admin_role", "subscription_tier")\n'
            '- attribute: the specific property (e.g., "name", "monthly_price", "framework")\n'
            "- value: the decided value (string, number, or list of strings)\n"
            "- confidence: 1.0 if explicitly stated by founder, 0.8 if strongly implied, 0.6 if inferred\n"
            "\n"
            "Only include facts that are DECISIONS or COMMITMENTS \u2014 not questions, explorations, "
            "or hypotheticals. If the founder said \"maybe X\" or \"we could do X\", that is NOT a fact.\n"
            "\n"
            "Output ONLY the JSON array. No markdown fences, no explanation."
        )

        result = self._gateway.run(MessageJob(
            role=RoleName.CONSISTENCY,
            phase=phase,
            label=f"P{phase.value} fact extraction",
            system_prompt="You extract structured facts from conversations. Output only valid JSON.",
            messages=[{"role": "user", "content": prompt + "\n\n" + transcript_text}],
            tools=[],
            thinking_budget=0,
        ))

        if result.usage is not None:
            self._ledger.record(phase, result.usage)

        if result.error:
            logger.warning(
                "Phase %s fact extraction failed: %s", phase.value, result.error
            )
            return []

        # Parse JSON response
        raw_text = result.text.strip()
        # Strip markdown fences if present
        if raw_text.startswith("```"):
            lines = raw_text.split("\n")
            raw_text = "\n".join(
                line for line in lines
                if not line.strip().startswith("```")
            )

        try:
            facts_data: list[dict[str, object]] = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.warning(
                "Phase %s fact extraction JSON parse failed: %s",
                phase.value, e,
            )
            return []

        if not isinstance(facts_data, list):
            logger.warning("Phase %s fact extraction returned non-list", phase.value)
            return []

        registered: list[CanonicalFact] = []
        for fd in facts_data:
            try:
                fact = CanonicalFact(
                    namespace=str(fd.get("namespace", "")),
                    subject=str(fd.get("subject", "")),
                    attribute=str(fd.get("attribute", "")),
                    value=fd.get("value", ""),  # type: ignore[arg-type]
                    source_phase=phase,
                    confidence=float(fd.get("confidence", 1.0)),  # type: ignore[arg-type]
                )
                self._state.register(fact)
                registered.append(fact)
            except Exception as e:
                logger.debug("Skipping malformed fact: %s", e)

        logger.info(
            "Phase %s: extracted %d facts, registered %d",
            phase.value, len(facts_data), len(registered),
        )
        return registered

    # -------------------------------------------------------------------
    # Private: Founder Memory
    # -------------------------------------------------------------------

    def _get_founder_memory(self, phase: PhaseKey) -> str:
        """Load or generate founder memory."""
        # Phase 1 has no prior context
        if phase == PhaseKey.P1:
            return ""

        existing = self._store.load_founder_memory()
        if existing is not None:
            return existing

        # Generate initial memory from prior deliverables
        prior = self.load_prior_deliverables(phase)
        if not prior:
            return ""

        prompt = (
            "Below are deliverables from prior phases of a platform planning session. "
            "Generate a concise memory summary (2000-3000 characters) of all key decisions, "
            "names, values, and commitments. Use bullet points grouped by phase. "
            "This will be used to remind the founder of their prior decisions.\n\n"
            f"<prior_deliverables>\n{prior[:80000]}\n</prior_deliverables>"
        )

        result = self._gateway.run(MessageJob(
            role=RoleName.CONSISTENCY,
            phase=phase,
            label=f"P{phase.value} founder memory generation",
            system_prompt="You are a concise summarizer. Output ONLY the memory summary, no preamble.",
            messages=[{"role": "user", "content": prompt}],
            tools=[],
            thinking_budget=0,
        ))

        if result.usage is not None:
            self._ledger.record(phase, result.usage)

        memory_text = result.text or ""
        if memory_text:
            self._store.save_founder_memory(memory_text)

        return memory_text

    def _update_founder_memory(
        self, phase: PhaseKey, deliverable_text: str
    ) -> None:
        """Generate and append incremental memory delta for completed phase."""
        phase_label = f"Phase {phase.value}"

        delta_prompt = (
            f"A founder just completed {phase_label} of their platform planning. "
            f"Below is the deliverable produced for this phase.\n\n"
            "Generate a CONCISE MEMORY DELTA \u2014 a bullet-point summary of ONLY the new "
            "decisions, names, choices, and commitments made in THIS phase.\n\n"
            "Requirements:\n"
            "- 300-600 characters maximum\n"
            f"- Start with: '### {phase_label}'\n"
            "- Focus on decisions and specific names/values\n"
            "- Write in second person ('You decided...')\n"
            "- Do NOT repeat anything from prior phases\n\n"
            f"<deliverable>\n{deliverable_text[:50000]}\n</deliverable>"
        )

        result = self._gateway.run(MessageJob(
            role=RoleName.CONSISTENCY,
            phase=phase,
            label=f"P{phase.value} founder memory delta",
            system_prompt="You are a concise summarizer. Output ONLY the memory delta, no preamble.",
            messages=[{"role": "user", "content": delta_prompt}],
            tools=[],
            thinking_budget=0,
        ))

        if result.usage is not None:
            self._ledger.record(phase, result.usage)

        delta_text = result.text or ""
        if not delta_text:
            return

        existing = self._store.load_founder_memory() or ""
        updated = existing + "\n\n" + delta_text if existing else delta_text
        self._store.save_founder_memory(updated)

        logger.info(
            "Phase %s: founder memory updated (+%d chars, %d total)",
            phase.value, len(delta_text), len(updated),
        )

    # -------------------------------------------------------------------
    # Private: Master Prompt Adaptation
    # -------------------------------------------------------------------

    def _adapt_master_prompt(self) -> str:
        """Adapt master prompt research section based on available engines.

        Caches result for reuse within this PhaseService instance.
        """
        if self._adapted_prompt is not None:
            return self._adapted_prompt

        research = self._config.research
        has_full_research = research.perplexity_enabled or research.grok_enabled

        if has_full_research:
            research_section = _RESEARCH_SECTION_FULL
            hard_boundary_9 = _HARD_BOUNDARY_9_FULL
        else:
            research_section = _RESEARCH_SECTION_WEBSEARCH_ONLY
            hard_boundary_9 = _HARD_BOUNDARY_9_WEBSEARCH

        adapted = re.sub(
            r'<research_architecture>.*?</research_architecture>',
            research_section,
            self._master_prompt,
            flags=re.DOTALL,
        )

        adapted = re.sub(
            r'9\.\s+\*\*Never recommend a service without a sentiment check\.\*\*.*?(?=\n</hard_boundaries>)',
            hard_boundary_9,
            adapted,
            flags=re.DOTALL,
        )

        self._adapted_prompt = adapted
        return adapted

    # -------------------------------------------------------------------
    # Private: Utility
    # -------------------------------------------------------------------

    @staticmethod
    def _build_conversation_text(transcript: list[dict[str, object]]) -> str:
        """Convert transcript list to formatted text for synthesis input."""
        parts: list[str] = []
        for entry in transcript:
            speaker = "Guide" if entry.get("role") == "guide" else "Founder"
            text = f"{speaker}: {entry.get('text', '')}"
            research = entry.get("research")
            if research:
                text += f"\n\n[Research data from this exchange:]\n{research}"
            parts.append(text)
        return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _strip_synthesis_preamble(text: str) -> str:
    """Remove any AI preamble before the first markdown heading."""
    match = re.search(r'^# ', text, re.MULTILINE)
    if match:
        return text[match.start():]
    return text
