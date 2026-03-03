"""Step 8 integration tests — cross-module wiring verification.

All tests use real module instances with ONLY the LLM gateway mocked
at the external boundary. No imports from archive/.

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.6 Step 8
"""

from __future__ import annotations

import json
import logging
import os
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from src.contracts import (
    CallUsage,
    MessageJob,
    MessageResult,
    PhaseKey,
    RoleName,
    RunSummary,
)
from src.orchestrator import Orchestrator, load_template_cached
from src.phase_service import FOUNDER_COMPLETE_MARKER, GUIDE_COMPLETE_MARKER
from src.review_pipeline import REENGAGEMENT_COMPLETE_MARKER
from src.run_store import CostLedger, RunStore, StateRegistry
from src.settings import AppConfig, load_app_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_HAIKU_MODEL_ID: str = "claude-haiku-4-5-20251001"

_MINIMAL_DELIVERABLE_P1: str = """\
# Phase 1: Vision & Opportunity

## 1.1 Platform Overview

Ocean Golf is a luxury golf concierge platform in Cabo San Lucas.

## 1.2 Target Audience

Golf course operators and event coordinators.

## 1.3 Business Model

B2B2C model with subscription pricing.

## 1.4 Competitive Landscape

Limited competition in the luxury golf concierge space.

## 1.5 Risk Assessment

Market entry risks include seasonal demand and local competition."""

_MINIMAL_DELIVERABLE_P2: str = """\
# Phase 2: User Universe Mapping

## 2.1 User Roles

Admin, Operator, Concierge, Guest.

## 2.2 Permission Matrix

RBAC controls with hierarchical permissions.

## 2.3 User Lifecycles

Each role follows onboarding, active, and offboarding stages."""


# ---------------------------------------------------------------------------
# Response Factories
# ---------------------------------------------------------------------------


def _make_usage(
    role: RoleName = RoleName.GUIDE,
    cost: str = "0.001",
) -> CallUsage:
    """Build a realistic CallUsage with minimal token counts."""
    return CallUsage(
        role=role,
        model_id=_HAIKU_MODEL_ID,
        input_tokens=500,
        output_tokens=200,
        cache_read_tokens=0,
        cache_write_tokens=0,
        cost_usd=Decimal(cost),
    )


def _make_result(
    role: RoleName,
    phase: PhaseKey,
    label: str,
    text: str,
    cost: str = "0.001",
    stop_reason: str = "end_turn",
) -> MessageResult:
    """Build a MessageResult with realistic usage stats."""
    return MessageResult(
        role=role,
        phase=phase,
        label=label,
        text=text,
        usage=_make_usage(role=role, cost=cost),
        stop_reason=stop_reason,
    )


# ---------------------------------------------------------------------------
# Gateway Response Router
# ---------------------------------------------------------------------------


class GatewayRouter:
    """Routes mock gateway calls based on MessageJob.role.

    Tracks call counts per role to control conversation termination.
    Each test creates its own router instance for isolation.
    """

    def __init__(
        self,
        *,
        max_exchanges: int = 3,
        deliverable_p1: str = _MINIMAL_DELIVERABLE_P1,
        deliverable_p2: str = _MINIMAL_DELIVERABLE_P2,
        l1_pass: bool = True,
        l2_findings_xml: str = "<findings>NONE</findings>",
        l3_findings_xml: str = "<findings>NONE</findings>",
        l4_findings_xml: str = "<findings>NONE</findings>",
        correction_xml: str = "<corrections></corrections>",
        consistency_json: str = '{"issues": [], "summary": "No conflicts"}',
        fact_json: str = "[]",
        founder_memory_delta: str = "### Phase 1\n- Platform: Ocean Golf",
        fail_on_role: RoleName | None = None,
    ) -> None:
        self._max_exchanges = max_exchanges
        self._deliverable_p1 = deliverable_p1
        self._deliverable_p2 = deliverable_p2
        self._l1_first_pass = l1_pass
        self._l2_xml = l2_findings_xml
        self._l3_xml = l3_findings_xml
        self._l4_xml = l4_findings_xml
        self._correction_xml = correction_xml
        self._consistency_json = consistency_json
        self._fact_json = fact_json
        self._founder_memory_delta = founder_memory_delta
        self._fail_on_role = fail_on_role

        # Per-phase counters for conversation loop
        self._guide_count: dict[str, int] = {}
        self._founder_count: dict[str, int] = {}
        self._l1_count: int = 0

    def __call__(self, job: MessageJob) -> MessageResult:
        """Route a MessageJob to the appropriate handler."""
        if self._fail_on_role and job.role == self._fail_on_role:
            raise RuntimeError(f"Simulated {job.role.value} failure")

        if job.role == RoleName.GUIDE:
            return self._guide(job)
        if job.role == RoleName.FOUNDER:
            return self._founder(job)
        if job.role == RoleName.SYNTHESIS:
            return self._synthesis(job)
        if job.role == RoleName.L1:
            return self._l1(job)
        if job.role == RoleName.L2:
            return self._l2(job)
        if job.role == RoleName.L3:
            return self._l3(job)
        if job.role == RoleName.L4:
            return self._l4(job)
        if job.role == RoleName.CORRECTION:
            return self._correction(job)
        if job.role == RoleName.CONSISTENCY:
            return self._consistency(job)
        return _make_result(job.role, job.phase, job.label, "OK")

    def _guide(self, job: MessageJob) -> MessageResult:
        phase_val = job.phase.value
        count = self._guide_count.get(phase_val, 0) + 1
        self._guide_count[phase_val] = count

        text = (
            f"Guide response phase {phase_val} exchange {count}. "
            "Let me explore your platform vision. "
        )
        if count >= self._max_exchanges:
            text += (
                "We have covered everything needed. "
                f"{GUIDE_COMPLETE_MARKER}"
            )
        return _make_result(RoleName.GUIDE, job.phase, job.label, text)

    def _founder(self, job: MessageJob) -> MessageResult:
        phase_val = job.phase.value
        count = self._founder_count.get(phase_val, 0) + 1
        self._founder_count[phase_val] = count

        text = (
            f"Founder response phase {phase_val} exchange {count}. "
            "The platform is called Ocean Golf. "
        )
        if count >= self._max_exchanges:
            text += (
                "That covers everything. "
                f"{FOUNDER_COMPLETE_MARKER}"
            )
        return _make_result(RoleName.FOUNDER, job.phase, job.label, text)

    def _synthesis(self, job: MessageJob) -> MessageResult:
        deliverable = (
            self._deliverable_p2
            if job.phase == PhaseKey.P2
            else self._deliverable_p1
        )
        return _make_result(
            RoleName.SYNTHESIS, job.phase, job.label,
            deliverable, cost="0.005",
        )

    def _l1(self, job: MessageJob) -> MessageResult:
        self._l1_count += 1
        if self._l1_count == 1 and not self._l1_first_pass:
            text = json.dumps({
                "pass": False,
                "missing_items": [
                    {
                        "section": "1.3 Business Model",
                        "detail": "Missing pricing details",
                    },
                ],
            })
        else:
            text = '{"pass": true, "missing_items": []}'
        return _make_result(RoleName.L1, job.phase, job.label, text)

    def _l2(self, job: MessageJob) -> MessageResult:
        # L2 is also used for reengagement guide
        if "reengagement" in job.label:
            return _make_result(
                RoleName.L2, job.phase, job.label,
                f"Thank you, that clarifies everything. {REENGAGEMENT_COMPLETE_MARKER}",
            )
        return _make_result(
            RoleName.L2, job.phase, job.label, self._l2_xml,
        )

    def _l3(self, job: MessageJob) -> MessageResult:
        return _make_result(
            RoleName.L3, job.phase, job.label, self._l3_xml,
        )

    def _l4(self, job: MessageJob) -> MessageResult:
        return _make_result(
            RoleName.L4, job.phase, job.label, self._l4_xml,
        )

    def _correction(self, job: MessageJob) -> MessageResult:
        # CORRECTION is used for both correction synthesis and targeted update
        if "targeted" in job.label:
            return _make_result(
                RoleName.CORRECTION, job.phase, job.label,
                self._deliverable_p1, cost="0.003",
            )
        return _make_result(
            RoleName.CORRECTION, job.phase, job.label,
            self._correction_xml, cost="0.003",
        )

    def _consistency(self, job: MessageJob) -> MessageResult:
        label_lower = job.label.lower()
        if "fact" in label_lower:
            return _make_result(
                RoleName.CONSISTENCY, job.phase, job.label,
                self._fact_json,
            )
        if "memory" in label_lower:
            return _make_result(
                RoleName.CONSISTENCY, job.phase, job.label,
                self._founder_memory_delta,
            )
        return _make_result(
            RoleName.CONSISTENCY, job.phase, job.label,
            self._consistency_json,
        )


# ---------------------------------------------------------------------------
# Fixture Helpers
# ---------------------------------------------------------------------------


def _load_test_config(tmp_path: Path) -> AppConfig:
    """Load real AppConfig from project config.json."""
    config_path = Path(__file__).parent.parent.parent / "config.json"
    config = load_app_config(config_path)
    config.runtime.publish_after_each_phase = False
    return config


def _setup_templates(store: RunStore) -> None:
    """Place minimal fixture templates in the store's template cache."""
    fixtures_dir = Path(__file__).parent / "fixtures" / "templates"

    # Phase 1 templates (separate conversation + synthesis)
    p1_conv = fixtures_dir / "phase-1-conversation.md"
    p1_synth = fixtures_dir / "phase-1-synthesis.md"
    if p1_conv.exists():
        store.cache_template(
            "phase-1-conversation.md",
            p1_conv.read_text(encoding="utf-8"),
        )
    else:
        store.cache_template(
            "phase-1-conversation.md",
            (
                "# PlatformForge \u2014 Phase 1: Vision & Opportunity\n\n"
                "<phase_conversation_structure>\n"
                "Talk about the idea.\n"
                "</phase_conversation_structure>\n"
            ),
        )

    if p1_synth.exists():
        store.cache_template(
            "phase-1-synthesis.md",
            p1_synth.read_text(encoding="utf-8"),
        )
    else:
        store.cache_template(
            "phase-1-synthesis.md",
            (
                "# PlatformForge \u2014 Phase 1: Synthesis & Output\n\n"
                "<phase_completion_gate>\n"
                "- [ ] **Core problem defined.** Description here.\n"
                "</phase_completion_gate>\n\n"
                "<phase_outputs>\n"
                "**1. Platform Vision Document**\n"
                "The master document.\n"
                "</phase_outputs>\n"
            ),
        )

    # Phase 2 template (combined file)
    p2_file = fixtures_dir / "phase-2-users.md"
    if p2_file.exists():
        store.cache_template(
            "phase-2-users.md",
            p2_file.read_text(encoding="utf-8"),
        )
    else:
        store.cache_template(
            "phase-2-users.md",
            (
                "# PlatformForge \u2014 Phase 2: User Universe Mapping\n\n"
                "<phase_conversation_structure>\n"
                "Map users.\n"
                "</phase_conversation_structure>\n"
                "<!-- CONVERSATION_END -->\n"
                "<!-- SYNTHESIS_START: Phase 2 synthesis -->\n\n"
                "<phase_completion_gate>\n"
                "- [ ] **User roles mapped.** All roles identified.\n"
                "</phase_completion_gate>\n\n"
                "<phase_outputs>\n"
                "**1. User Role Matrix**\n"
                "The complete matrix.\n"
                "</phase_outputs>\n"
            ),
        )


def _build_orchestrator(
    tmp_path: Path,
    router: GatewayRouter,
    *,
    ceiling: Decimal = Decimal("100.00"),
) -> tuple[Orchestrator, RunStore, StateRegistry, CostLedger, MagicMock]:
    """Build real Orchestrator with mocked gateway.

    Returns (orchestrator, store, state, ledger, gateway_mock).
    """
    config = _load_test_config(tmp_path)
    config.runtime.hard_cost_ceiling_usd = ceiling

    store = RunStore(root=tmp_path)
    _setup_templates(store)

    gateway: MagicMock = MagicMock()
    type(gateway).model_id = PropertyMock(return_value=_HAIKU_MODEL_ID)
    gateway.run.side_effect = router
    gateway.run_parallel.side_effect = (
        lambda jobs: [router(j) for j in jobs]
    )
    gateway.estimate_cost.return_value = Decimal("0.01")

    state = StateRegistry()
    ledger = CostLedger(hard_ceiling_usd=ceiling)

    orch = Orchestrator(
        config=config,
        store=store,
        gateway=gateway,
        state=state,
        ledger=ledger,
        master_prompt="Master system prompt content.",
        persona="You are Rafael Delgado, founder of Ocean Golf.",
        review_personas={"l2": {}, "l3": {}, "l4": "", "config": ""},
    )

    # No-op publish to avoid real GitHub calls
    store.publish_to_github = MagicMock(  # type: ignore[method-assign]
        return_value={"pushed": 0, "skipped": 0, "failed": 0},
    )

    return orch, store, state, ledger, gateway


# ===================================================================
# 8.3.1 Single-Phase Happy Path
# ===================================================================


class TestSinglePhaseEndToEnd:
    """Run Orchestrator with a single phase (Phase 1) — all clean."""

    def test_single_phase_end_to_end(self, tmp_path: Path) -> None:
        router = GatewayRouter(max_exchanges=3)
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1])

        assert summary.phases_completed == ["1"]
        assert Decimal(summary.total_cost_usd) > Decimal("0.00")
        assert summary.halted_at_phase == ""

        # Deliverable file exists
        loaded = store.load_deliverable(PhaseKey.P1)
        assert loaded is not None
        assert len(loaded) > 0

        # Conversation JSON exists
        conv = store.load_conversation(PhaseKey.P1)
        assert conv is not None
        assert len(conv) > 0

        # Phase metrics JSON exists
        metrics_path = store.metrics_dir / "phase-1-metrics.json"
        assert metrics_path.exists()

        # No consistency check ran (only 1 phase)
        assert summary.consistency_check_run is False


# ===================================================================
# 8.3.2 Multi-Phase Sequential
# ===================================================================


class TestTwoPhaseSequential:
    """Run Orchestrator with phases [P1, P2] — consistency check runs."""

    def test_two_phase_sequential(self, tmp_path: Path) -> None:
        router = GatewayRouter(
            max_exchanges=2,
            consistency_json=json.dumps({
                "issues": [],
                "summary": "No conflicts found",
            }),
        )
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.phases_completed == ["1", "2"]

        # Consistency check DID run (2 phases completed)
        assert summary.consistency_check_run is True

        # Consistency report saved to store
        consistency_path = (
            store.metrics_dir / "cross-phase-consistency.json"
        )
        assert consistency_path.exists()

        # Both deliverables exist on disk
        assert store.load_deliverable(PhaseKey.P1) is not None
        assert store.load_deliverable(PhaseKey.P2) is not None

        # Cost is cumulative across both phases
        assert Decimal(summary.total_cost_usd) > Decimal("0.00")

        # Timing waterfall saved
        waterfall_path = store.metrics_dir / "timing-waterfall.json"
        assert waterfall_path.exists()


# ===================================================================
# 8.3.3 Review Correction Flow
# ===================================================================


class TestReviewFindsAndCorrects:
    """L1 finds issues, correction patches apply successfully."""

    def test_review_finds_and_corrects(self, tmp_path: Path) -> None:
        correction_xml = (
            "<corrections>\n"
            '<patch id="L1-1">\n'
            "  <action>replace</action>\n"
            "  <anchor>## 1.3 Business Model</anchor>\n"
            "  <search_text>B2B2C model with subscription pricing.</search_text>\n"
            "  <new_text>B2B2C model with subscription pricing "
            "at $99/month for operators.</new_text>\n"
            "</patch>\n"
            "</corrections>"
        )

        router = GatewayRouter(
            max_exchanges=2,
            l1_pass=False,
            correction_xml=correction_xml,
        )
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1])

        assert summary.phases_completed == ["1"]

        # Final deliverable differs from initial synthesis
        final = store.load_deliverable(PhaseKey.P1)
        assert final is not None
        assert "$99/month" in final

        # Review pipeline summary saved
        pipeline_path = (
            store.metrics_dir / "phase-1-review-pipeline.json"
        )
        assert pipeline_path.exists()


# ===================================================================
# 8.3.4 Cost Ceiling Halt
# ===================================================================


class TestCostCeilingHaltsRun:
    """Low cost ceiling halts run before or during phase execution."""

    def test_cost_ceiling_halts_run(self, tmp_path: Path) -> None:
        router = GatewayRouter(max_exchanges=2)
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router, ceiling=Decimal("0.001"),
        )

        # Pre-exhaust budget so the run can't start
        ledger.record(
            PhaseKey.P1,
            _make_usage(cost="0.001"),
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert len(summary.phases_completed) <= 1
        assert summary.halted_at_phase != ""
        halt_lower = summary.halt_reason.lower()
        assert "cost" in halt_lower or "ceiling" in halt_lower


# ===================================================================
# 8.3.5 Resume After Interruption
# ===================================================================


class TestResumeSkipsCompletedPhases:
    """Pre-populated Phase 1 artifacts simulate a prior run."""

    def test_resume_skips_completed_phases(self, tmp_path: Path) -> None:
        router = GatewayRouter(max_exchanges=2)
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        # Pre-populate store with Phase 1 deliverable
        store.save_deliverable(PhaseKey.P1, _MINIMAL_DELIVERABLE_P1)
        store.save_conversation(PhaseKey.P1, [
            {"role": "guide", "text": "Question"},
            {"role": "founder", "text": "Answer"},
        ])

        # Run from P2 only (simulating resume)
        summary = orch.run([PhaseKey.P2])

        # Phase 2 ran normally
        assert "2" in summary.phases_completed

        # Phase 2 has a deliverable
        p2_deliverable = store.load_deliverable(PhaseKey.P2)
        assert p2_deliverable is not None

        # Phase 1 deliverable is still intact (loaded as prior context)
        p1_deliverable = store.load_deliverable(PhaseKey.P1)
        assert p1_deliverable == _MINIMAL_DELIVERABLE_P1


# ===================================================================
# 8.3.6 Phase Failure Propagation
# ===================================================================


class TestPhaseFailureHaltsGracefully:
    """Simulated API failure during Phase 1 conversation."""

    def test_phase_failure_halts_gracefully(self, tmp_path: Path) -> None:
        router = GatewayRouter(
            max_exchanges=2,
            fail_on_role=RoleName.GUIDE,
        )
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.halted_at_phase == "1"
        assert summary.halt_reason != ""

        # Phase 2 did NOT execute (sequential dependency)
        assert "2" not in summary.phases_completed

        # No unhandled exception — we got a RunSummary back
        assert isinstance(summary, RunSummary)


# ===================================================================
# 8.3.7 Cross-Phase Consistency Check
# ===================================================================


class TestConsistencyCheckDetectsConflicts:
    """Consistency check returns 2 conflicts across phases."""

    def test_consistency_check_detects_conflicts(
        self, tmp_path: Path,
    ) -> None:
        consistency_response = json.dumps({
            "issues": [
                {
                    "phases": ["1", "2"],
                    "type": "naming_inconsistency",
                    "description": (
                        "Phase 1 uses 'Ocean Golf', "
                        "Phase 2 uses 'OceanGolf'"
                    ),
                },
                {
                    "phases": ["1", "2"],
                    "type": "technology_contradiction",
                    "description": (
                        "Phase 1 says React, Phase 2 says Vue"
                    ),
                },
            ],
            "summary": "2 conflicts found",
        })

        router = GatewayRouter(
            max_exchanges=2,
            consistency_json=consistency_response,
        )
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.phases_completed == ["1", "2"]
        assert summary.consistency_check_run is True

        # Consistency report saved and contains the 2 conflicts
        report_path = (
            store.metrics_dir / "cross-phase-consistency.json"
        )
        assert report_path.exists()

        report: dict[str, Any] = json.loads(
            report_path.read_text(encoding="utf-8"),
        )
        assert len(report.get("issues", [])) == 2


# ===================================================================
# 8.3.8 Founder Memory Persistence
# ===================================================================


class TestFounderMemoryFlowsAcrossPhases:
    """Facts extracted in Phase 1 flow into Phase 2 context."""

    def test_founder_memory_flows_across_phases(
        self, tmp_path: Path,
    ) -> None:
        router = GatewayRouter(
            max_exchanges=2,
            fact_json=json.dumps([
                {
                    "namespace": "naming",
                    "subject": "platform",
                    "attribute": "name",
                    "value": "Ocean Golf",
                    "confidence": 1.0,
                },
            ]),
            founder_memory_delta=(
                "### Phase 1\n"
                "- You decided the platform name is Ocean Golf."
            ),
        )
        orch, store, state, ledger, gw = _build_orchestrator(
            tmp_path, router,
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.phases_completed == ["1", "2"]

        # Founder memory file exists after Phase 1
        memory = store.load_founder_memory()
        assert memory is not None
        assert len(memory) > 0

        # StateRegistry contains facts (Phase 2 supersedes Phase 1's
        # identical fact key, so query all facts rather than by phase)
        assert state.fact_count() > 0
        all_facts = state.all_facts()
        assert any(f.value == "Ocean Golf" for f in all_facts)


# ===================================================================
# 8.3.9 Template Caching
# ===================================================================


class TestTemplateFetchAndCache:
    """First fetch hits GitHub, subsequent calls use cache."""

    def test_template_fetch_and_cache(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)

        with patch(
            "src.orchestrator.fetch_github_file",
            return_value="# Template Content\n\nSome text.",
        ) as mock_fetch:
            # First call fetches from GitHub
            result = load_template_cached(store, "test-template.md")
            assert result == "# Template Content\n\nSome text."
            mock_fetch.assert_called_once()

            # Second call uses cache — no re-fetch
            result2 = load_template_cached(store, "test-template.md")
            assert result2 == "# Template Content\n\nSome text."
            mock_fetch.assert_called_once()

            # Verify cached via store
            cached = store.load_cached_template("test-template.md")
            assert cached == "# Template Content\n\nSome text."


# ===================================================================
# 8.3.10 Dry-Run Mode
# ===================================================================


class TestDryRunMode:
    """--dry-run exits without making any gateway calls."""

    def test_dry_run_mode(self, tmp_path: Path) -> None:
        with patch("src.orchestrator.RunStore") as mock_store_cls:
            mock_store: MagicMock = MagicMock()
            mock_store.root = tmp_path
            mock_store.templates_dir = tmp_path / "templates"
            mock_store.load_cached_template.return_value = "# Master Prompt"
            mock_store_cls.return_value = mock_store

            persona_path = tmp_path / "persona.md"
            persona_path.write_text(
                "# Persona\nRafael Delgado",
                encoding="utf-8",
            )

            config = _load_test_config(tmp_path)

            with patch(
                "src.orchestrator.load_app_config",
                return_value=config,
            ):
                mock_gw: MagicMock = MagicMock()
                type(mock_gw).model_id = PropertyMock(
                    return_value=_HAIKU_MODEL_ID,
                )

                with patch(
                    "src.orchestrator.AnthropicGateway",
                    return_value=mock_gw,
                ):
                    with patch(
                        "src.orchestrator.load_review_personas",
                        return_value={
                            "l2": {},
                            "l3": {},
                            "l4": "",
                            "config": "",
                        },
                    ):
                        with patch(
                            "src.orchestrator.load_all_phase_templates",
                        ):
                            with patch(
                                "sys.argv",
                                ["orchestrator.py", "--dry-run"],
                            ):
                                env = {
                                    "ANTHROPIC_API_KEY": "test-key",
                                }
                                with patch.dict(os.environ, env):
                                    from src.orchestrator import main

                                    main()

                # No gateway calls made
                mock_gw.run.assert_not_called()
