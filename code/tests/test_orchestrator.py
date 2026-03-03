"""Tests for orchestrator.py — Step 7."""

from __future__ import annotations

import json
import os
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.contracts import (
    CallUsage,
    MessageResult,
    PhaseKey,
    PhaseOutcome,
    PhaseResult,
    PhaseTemplateSpec,
    ReviewPipelineResult,
    RoleName,
    RunSummary,
    phase_key,
)
from src.orchestrator import (
    DEFAULT_MAX_EXCHANGES,
    GITHUB_REPO,
    MASTER_PROMPT_FILENAME,
    TEMPLATES_PATH,
    Orchestrator,
    check_research_capabilities,
    fetch_github_file,
    load_all_phase_templates,
    load_persona,
    load_template_cached,
    main,
    _load_dotenv,
)
from src.phase_service import PHASE_ORDER
from src.run_store import CostCeilingExceeded, CostLedger, RunStore, StateRegistry
from src.settings import AppConfig, load_app_config


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

class _FakeHTTPResponse:
    """Minimal mock for urllib response as context manager."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self._body = body
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeHTTPResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _make_usage(cost: str = "0.01") -> CallUsage:
    return CallUsage(
        role=RoleName.GUIDE,
        model_id="claude-haiku-4-5-20251001",
        input_tokens=100,
        output_tokens=50,
        cost_usd=Decimal(cost),
    )


def _make_phase_result(phase: PhaseKey = PhaseKey.P1) -> PhaseResult:
    return PhaseResult(
        outcome=PhaseOutcome(
            phase=phase,
            status="completed",
            deliverable_path=f"output/deliverables/deliverable-{phase.value}.md",
            exchange_count=5,
            deliverable_chars=500,
            cost_usd=Decimal("0.50"),
            elapsed_seconds=30.0,
        ),
        deliverable_text=f"# Phase {phase.value} Deliverable\n\nContent here.",
        transcript=[
            {"role": "guide", "text": "Question"},
            {"role": "founder", "text": "Answer"},
        ],
        template_spec=PhaseTemplateSpec(
            phase=phase,
            deliverable_name=f"Phase {phase.value}",
            synthesis_instructions="Synthesis template text",
        ),
    )


def _make_review_result(deliverable: str = "") -> ReviewPipelineResult:
    return ReviewPipelineResult(
        deliverable_text=deliverable or "# Reviewed deliverable",
        review_notes="",
        l1_initial_missing=0,
        total_must_fix=0,
        total_should_improve=0,
        total_consider=0,
        reengagement_triggered=False,
        pipeline_elapsed_seconds=5.0,
    )


def _app_config() -> AppConfig:
    """Load config from the project config.json."""
    config_path = Path(__file__).parent.parent.parent / "config.json"
    if config_path.exists():
        return load_app_config(config_path)
    return load_app_config()


def _make_orchestrator(
    tmp_path: Path,
    gateway: Any = None,
    phase_service: Any = None,
    review_pipeline: Any = None,
    ceiling: Decimal = Decimal("200"),
    publish: bool = False,
) -> tuple[Orchestrator, MagicMock, MagicMock]:
    """Create an Orchestrator with mocked services.

    Returns (orchestrator, phase_service_mock, review_pipeline_mock).
    """
    if gateway is None:
        gateway = MagicMock()
        type(gateway).model_id = PropertyMock(return_value="claude-haiku-4-5-20251001")

    config = _app_config()
    config.runtime.publish_after_each_phase = publish
    store = RunStore(root=tmp_path)
    state = StateRegistry()
    ledger = CostLedger(hard_ceiling_usd=ceiling)

    orch = Orchestrator(
        config=config,
        store=store,
        gateway=gateway,
        state=state,
        ledger=ledger,
        master_prompt="Master prompt content",
        persona="You are a test founder.",
        review_personas={"l2": {}, "l3": {}, "l4": "", "config": ""},
    )

    # Replace internal services with mocks
    ps_mock = phase_service or MagicMock()
    rp_mock = review_pipeline or MagicMock()
    orch._phase_service = ps_mock
    orch._review_pipeline = rp_mock

    return orch, ps_mock, rp_mock


# ===================================================================
# Utility Function Tests
# ===================================================================


class TestCheckResearchCapabilities:
    def test_all_present(self) -> None:
        with patch.dict(
            os.environ,
            {"PERPLEXITY_API_KEY": "pk-test", "GROK_API_KEY": "gk-test"},
        ):
            caps = check_research_capabilities()
            assert caps["web_search"] is True
            assert caps["perplexity"] is True
            assert caps["grok"] is True

    def test_none(self) -> None:
        env = dict(os.environ)
        env.pop("PERPLEXITY_API_KEY", None)
        env.pop("GROK_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            caps = check_research_capabilities()
            assert caps["web_search"] is True
            assert caps["perplexity"] is False
            assert caps["grok"] is False


class TestLoadPersona:
    def test_success(self, tmp_path: Path) -> None:
        persona_path = tmp_path / "persona.md"
        persona_path.write_text("# Founder\nRafael Delgado", encoding="utf-8")
        result = load_persona(tmp_path)
        assert "Rafael Delgado" in result

    def test_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError, match="persona.md not found"):
            load_persona(tmp_path)


class TestFetchGithubFile:
    def test_mocked(self) -> None:
        fake_resp = _FakeHTTPResponse(b"# Template Content\n\nSome text.")

        with patch(
            "src.orchestrator.urllib.request.urlopen",
            return_value=fake_resp,
        ):
            result = fetch_github_file("owner/repo", "path/file.md")
            assert result == "# Template Content\n\nSome text."

    def test_with_pat(self) -> None:
        fake_resp = _FakeHTTPResponse(b"content")
        captured_req: list[Any] = []

        def mock_urlopen(req: Any) -> _FakeHTTPResponse:
            captured_req.append(req)
            return fake_resp

        with patch.dict(os.environ, {"GITHUB_PAT": "test-token"}):
            with patch(
                "src.orchestrator.urllib.request.urlopen",
                side_effect=mock_urlopen,
            ):
                fetch_github_file("owner/repo", "path/file.md")
                assert captured_req[0].get_header("Authorization") == "token test-token"


class TestLoadTemplateCached:
    def test_cache_hit(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.cache_template("test.md", "# Cached Content")

        with patch("src.orchestrator.fetch_github_file") as mock_fetch:
            result = load_template_cached(store, "test.md")
            assert result == "# Cached Content"
            mock_fetch.assert_not_called()

    def test_cache_miss(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)

        with patch(
            "src.orchestrator.fetch_github_file",
            return_value="# Fetched Content",
        ) as mock_fetch:
            result = load_template_cached(store, "test.md")
            assert result == "# Fetched Content"
            mock_fetch.assert_called_once()
            # Verify it was cached
            cached = store.load_cached_template("test.md")
            assert cached == "# Fetched Content"


class TestLoadAllPhaseTemplates:
    def test_all_cached(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        fetch_count = 0

        def mock_fetch(repo: str, path: str) -> str:
            nonlocal fetch_count
            fetch_count += 1
            return f"# Template {fetch_count}"

        with patch("src.orchestrator.fetch_github_file", side_effect=mock_fetch):
            load_all_phase_templates(store)

        # Should have fetched all templates
        from src.template_parser import TEMPLATE_FILE_MAP

        total_files = sum(len(v) for v in TEMPLATE_FILE_MAP.values())
        assert fetch_count == total_files

        # All should now be cached
        for filenames in TEMPLATE_FILE_MAP.values():
            for filename in filenames:
                assert store.load_cached_template(filename) is not None


class TestLoadDotenv:
    def test_basic(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text(
            "TEST_KEY_ORCH=test_value\n"
            "# comment\n"
            "\n"
            "ANOTHER_KEY_ORCH=another\n",
            encoding="utf-8",
        )
        # Make sure keys don't already exist
        os.environ.pop("TEST_KEY_ORCH", None)
        os.environ.pop("ANOTHER_KEY_ORCH", None)

        _load_dotenv(tmp_path)

        assert os.environ.get("TEST_KEY_ORCH") == "test_value"
        assert os.environ.get("ANOTHER_KEY_ORCH") == "another"

        # Cleanup
        os.environ.pop("TEST_KEY_ORCH", None)
        os.environ.pop("ANOTHER_KEY_ORCH", None)

    def test_no_env_file(self, tmp_path: Path) -> None:
        # Should not raise
        _load_dotenv(tmp_path)

    def test_does_not_overwrite(self, tmp_path: Path) -> None:
        env_file = tmp_path / ".env"
        env_file.write_text("EXISTING_ORCH_KEY=new_val\n", encoding="utf-8")

        os.environ["EXISTING_ORCH_KEY"] = "original"
        try:
            _load_dotenv(tmp_path)
            assert os.environ["EXISTING_ORCH_KEY"] == "original"
        finally:
            os.environ.pop("EXISTING_ORCH_KEY", None)


# ===================================================================
# RunStore Extension Tests
# ===================================================================


class TestLoadAllDeliverables:
    def test_empty(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.load_all_deliverables() == {}

    def test_with_data(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.save_deliverable(PhaseKey.P1, "d1")
        store.save_deliverable(PhaseKey.P3, "d3")
        store.save_deliverable(PhaseKey.P5, "d5")
        result = store.load_all_deliverables()
        assert len(result) == 3
        assert result[PhaseKey.P1] == "d1"
        assert result[PhaseKey.P3] == "d3"
        assert result[PhaseKey.P5] == "d5"


# ===================================================================
# Orchestrator Tests
# ===================================================================


class TestOrchestratorSinglePhase:
    def test_single_phase(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        phase_result = _make_phase_result(PhaseKey.P1)
        ps_mock.run_phase.return_value = phase_result
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result(
            phase_result.deliverable_text
        )

        summary = orch.run([PhaseKey.P1])

        assert isinstance(summary, RunSummary)
        assert summary.phases_completed == ["1"]
        assert summary.halted_at_phase == ""
        assert summary.halt_reason == ""
        ps_mock.run_phase.assert_called_once()

        # Verify deliverable was saved
        store = orch._store
        loaded = store.load_deliverable(PhaseKey.P1)
        assert loaded is not None


class TestOrchestratorCostCeiling:
    def test_cost_ceiling_halt(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(
            tmp_path, ceiling=Decimal("0.01")
        )

        # First phase succeeds but uses budget
        phase_result = _make_phase_result(PhaseKey.P1)
        ps_mock.run_phase.return_value = phase_result
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result(
            phase_result.deliverable_text
        )

        # Exhaust the budget after first phase
        orch._ledger.record(PhaseKey.P1, _make_usage(cost="0.01"))

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        # P1 should not complete because budget was exhausted before run starts
        # Actually, the budget is checked at the top of the loop
        # The ledger already has 0.01 used and ceiling is 0.01
        # remaining = 0.01 - 0.01 = 0.00, which is <= 0
        assert summary.halted_at_phase == "1"
        assert "cost" in summary.halt_reason.lower() or "ceiling" in summary.halt_reason.lower()

    def test_cost_ceiling_during_phase(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(
            tmp_path, ceiling=Decimal("1.00")
        )

        def run_phase_with_cost(phase: PhaseKey, max_exchanges: int = 75) -> PhaseResult:
            # Simulate exceeding cost during phase
            raise CostCeilingExceeded(
                Decimal("0.90"), Decimal("0.20"), Decimal("1.00")
            )

        ps_mock.run_phase.side_effect = run_phase_with_cost

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.halted_at_phase == "1"
        assert "cost ceiling" in summary.halt_reason.lower()


class TestOrchestratorPhaseError:
    def test_phase_error_halts_run(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        call_count = 0

        def run_phase_side_effect(
            phase: PhaseKey, max_exchanges: int = 75
        ) -> PhaseResult:
            nonlocal call_count
            call_count += 1
            if phase == PhaseKey.P2:
                raise RuntimeError("Phase 2 synthesis failed")
            return _make_phase_result(phase)

        ps_mock.run_phase.side_effect = run_phase_side_effect
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result("reviewed")

        summary = orch.run([PhaseKey.P1, PhaseKey.P2, PhaseKey.P3])

        assert "1" in summary.phases_completed
        assert summary.halted_at_phase == "2"
        assert "RuntimeError" in summary.halt_reason
        # P3 should never have been attempted
        assert "3" not in summary.phases_completed


class TestOrchestratorPublish:
    def test_publishes_after_each_phase(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(
            tmp_path, publish=True
        )

        ps_mock.run_phase.return_value = _make_phase_result(PhaseKey.P1)
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result("reviewed")

        # Mock the store's publish method
        orch._store.publish_to_github = MagicMock(  # type: ignore[method-assign]
            return_value={"pushed": 1, "skipped": 0, "failed": 0}
        )

        with patch.dict(os.environ, {"GITHUB_PAT": "test-pat"}):
            summary = orch.run([PhaseKey.P1])

        # Should have been called at least once (per-phase + final)
        assert orch._store.publish_to_github.call_count >= 1


class TestCrossPhaseConsistency:
    def test_basic(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        # Pre-save deliverables
        orch._store.save_deliverable(PhaseKey.P1, "# Phase 1\n\nContent 1")
        orch._store.save_deliverable(PhaseKey.P2, "# Phase 2\n\nContent 2")

        # Mock gateway for consistency check
        consistency_json = json.dumps({
            "issues": [],
            "summary": "No conflicts found",
        })
        consistency_result = MessageResult(
            role=RoleName.CONSISTENCY,
            phase=PhaseKey.P2,
            label="cross-phase consistency",
            text=consistency_json,
            usage=_make_usage("0.05"),
        )
        orch._gateway.run.return_value = consistency_result

        report = orch.run_cross_phase_consistency(
            [PhaseKey.P1, PhaseKey.P2]
        )

        assert "issues" in report
        # Check report was saved
        report_path = (
            tmp_path / "output" / "metrics" / "cross-phase-consistency.json"
        )
        assert report_path.exists()

    def test_insufficient_deliverables(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        # Only save one deliverable
        orch._store.save_deliverable(PhaseKey.P1, "# Phase 1\n\nContent")

        report = orch.run_cross_phase_consistency([PhaseKey.P1])

        assert report.get("skipped") is True

    def test_unparseable_response(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        orch._store.save_deliverable(PhaseKey.P1, "d1")
        orch._store.save_deliverable(PhaseKey.P2, "d2")

        bad_result = MessageResult(
            role=RoleName.CONSISTENCY,
            phase=PhaseKey.P2,
            label="cross-phase consistency",
            text="This is not JSON at all",
            usage=_make_usage("0.01"),
        )
        orch._gateway.run.return_value = bad_result

        report = orch.run_cross_phase_consistency(
            [PhaseKey.P1, PhaseKey.P2]
        )
        assert report.get("error") == "unparseable"


class TestRunSummaryStructure:
    def test_all_fields(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        ps_mock.run_phase.return_value = _make_phase_result(PhaseKey.P1)
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result("reviewed")

        summary = orch.run([PhaseKey.P1])

        assert isinstance(summary, RunSummary)
        assert isinstance(summary.phases_requested, list)
        assert isinstance(summary.phases_completed, list)
        assert isinstance(summary.total_cost_usd, str)
        assert isinstance(summary.total_elapsed_seconds, float)
        assert isinstance(summary.consistency_check_run, bool)
        assert isinstance(summary.halted_at_phase, str)
        assert isinstance(summary.halt_reason, str)

    def test_phases_requested_populated(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        ps_mock.run_phase.return_value = _make_phase_result(PhaseKey.P1)
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result("reviewed")

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.phases_requested == ["1", "2"]


class TestOrchestratorMultiPhase:
    def test_two_phases_with_consistency(self, tmp_path: Path) -> None:
        orch, ps_mock, rp_mock = _make_orchestrator(tmp_path)

        def run_phase_side_effect(
            phase: PhaseKey, max_exchanges: int = 75
        ) -> PhaseResult:
            return _make_phase_result(phase)

        ps_mock.run_phase.side_effect = run_phase_side_effect
        ps_mock.load_prior_deliverables.return_value = ""
        rp_mock.run.return_value = _make_review_result("reviewed")

        # Mock consistency check
        consistency_json = json.dumps({
            "issues": [], "summary": "Clean"
        })
        orch._gateway.run.return_value = MessageResult(
            role=RoleName.CONSISTENCY,
            phase=PhaseKey.P2,
            label="consistency",
            text=consistency_json,
            usage=_make_usage("0.01"),
        )

        summary = orch.run([PhaseKey.P1, PhaseKey.P2])

        assert summary.phases_completed == ["1", "2"]
        assert summary.consistency_check_run is True

        # Verify timing waterfall was saved
        waterfall_path = tmp_path / "output" / "metrics" / "timing-waterfall.json"
        assert waterfall_path.exists()

        # Verify cost report was saved
        cost_path = tmp_path / "output" / "metrics" / "cost-report.json"
        assert cost_path.exists()


# ===================================================================
# CLI Tests
# ===================================================================


class TestMainDryRun:
    def test_dry_run(self, tmp_path: Path) -> None:
        """--dry-run should exit without making API calls."""
        with patch("src.orchestrator.RunStore") as mock_store_cls:
            mock_store = MagicMock()
            mock_store.root = tmp_path
            mock_store.templates_dir = tmp_path / "templates"
            mock_store.load_cached_template.return_value = "# Master Prompt"
            mock_store_cls.return_value = mock_store

            # Create persona.md
            persona_path = tmp_path / "persona.md"
            persona_path.write_text("# Persona", encoding="utf-8")

            with patch("src.orchestrator.load_app_config") as mock_config:
                mock_config.return_value = _app_config()
                with patch("src.orchestrator.AnthropicGateway"):
                    with patch("src.orchestrator.load_review_personas", return_value={
                        "l2": {}, "l3": {}, "l4": "", "config": ""
                    }):
                        with patch("src.orchestrator.load_all_phase_templates"):
                            with patch(
                                "sys.argv",
                                ["orchestrator.py", "--dry-run"],
                            ):
                                with patch.dict(os.environ, {
                                    "ANTHROPIC_API_KEY": "test"
                                }):
                                    # Should not raise, should return cleanly
                                    main()
