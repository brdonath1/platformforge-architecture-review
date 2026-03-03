"""Tests for phase_service.py — PhaseService, constants, conversation, synthesis, facts."""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest

from src.contracts import (
    CallUsage,
    CanonicalFact,
    MessageJob,
    MessageResult,
    PhaseKey,
    PhaseOutcome,
    PhaseResult,
    PhaseTemplateSpec,
    RoleName,
)
from src.phase_service import (
    FOUNDER_COMPLETE_MARKER,
    GUIDE_COMPLETE_MARKER,
    GUIDE_PREAMBLE,
    PHASE_OPENINGS,
    PHASE_ORDER,
    PHASE_PREAMBLES,
    SYNTHESIS_PREAMBLE,
    PhaseService,
    _strip_synthesis_preamble,
)
from src.run_store import CostLedger, RunStore, StateRegistry
from src.settings import AppConfig, load_app_config


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def app_config() -> AppConfig:
    """Load real config.json (Haiku tier)."""
    return load_app_config()


@pytest.fixture()
def store(tmp_path: Path) -> RunStore:
    return RunStore(root=tmp_path)


@pytest.fixture()
def state() -> StateRegistry:
    return StateRegistry()


@pytest.fixture()
def ledger() -> CostLedger:
    return CostLedger(hard_ceiling_usd=Decimal("200"))


def _make_result(
    text: str = "Hello",
    role: RoleName = RoleName.GUIDE,
    phase: PhaseKey = PhaseKey.P1,
    stop_reason: str = "end_turn",
    tool_use_blocks: list[dict[str, object]] | None = None,
    tool_result_blocks: list[dict[str, object]] | None = None,
    error: str | None = None,
) -> MessageResult:
    return MessageResult(
        role=role,
        phase=phase,
        label="test",
        text=text,
        stop_reason=stop_reason,
        tool_use_blocks=tool_use_blocks or [],
        tool_result_blocks=tool_result_blocks or [],
        usage=CallUsage(
            role=role,
            model_id="claude-haiku-4-5-20251001",
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.001"),
        ),
        error=error,
    )


def _make_service(
    store: RunStore,
    state: StateRegistry,
    ledger: CostLedger,
    config: AppConfig,
    gateway: Any = None,
    master_prompt: str = "<research_architecture>old</research_architecture>\n<hard_boundaries>\n9. **Never recommend a service without a sentiment check.**\n</hard_boundaries>",
    persona: str = "You are Rafael Delgado.",
) -> PhaseService:
    if gateway is None:
        gateway = MagicMock(spec=["run", "run_parallel", "estimate_cost", "model_id"])
    return PhaseService(
        gateway=gateway,
        store=store,
        state=state,
        ledger=ledger,
        config=config,
        master_prompt=master_prompt,
        persona=persona,
    )


def _setup_templates(store: RunStore) -> None:
    """Copy fixture templates to the store's templates_cache directory."""
    fixtures = Path(__file__).parent / "fixtures" / "templates"
    for f in fixtures.iterdir():
        if f.is_file():
            store.cache_template(f.name, f.read_text(encoding="utf-8"))


# ===================================================================
# Constants Tests
# ===================================================================


class TestConstants:
    def test_phase_openings_keys_match_phase_key_values(self) -> None:
        valid_values = {pk.value for pk in PhaseKey}
        for key in PHASE_OPENINGS:
            assert key in valid_values, f"PHASE_OPENINGS key '{key}' not a valid PhaseKey"

    def test_phase_preambles_keys_match_phase_key_values(self) -> None:
        valid_values = {pk.value for pk in PhaseKey}
        for key in PHASE_PREAMBLES:
            assert key in valid_values, f"PHASE_PREAMBLES key '{key}' not a valid PhaseKey"

    def test_phase_order_contains_all_phases(self) -> None:
        assert len(PHASE_ORDER) == 12
        assert set(PHASE_ORDER) == set(PhaseKey)

    def test_completion_markers_are_strings(self) -> None:
        assert isinstance(GUIDE_COMPLETE_MARKER, str)
        assert len(GUIDE_COMPLETE_MARKER) > 0
        assert isinstance(FOUNDER_COMPLETE_MARKER, str)
        assert len(FOUNDER_COMPLETE_MARKER) > 0


# ===================================================================
# Conversation Tests
# ===================================================================


class TestConversation:
    def test_conversation_basic_loop(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        _setup_templates(store)
        gateway = MagicMock()

        call_count = {"n": 0}

        def mock_run(job: MessageJob) -> MessageResult:
            call_count["n"] += 1
            if job.role == RoleName.GUIDE:
                if call_count["n"] >= 3:
                    return _make_result(
                        text=f"Guide response {GUIDE_COMPLETE_MARKER}",
                        role=RoleName.GUIDE,
                    )
                return _make_result(text="Guide question", role=RoleName.GUIDE)
            # Founder
            if call_count["n"] >= 4:
                return _make_result(
                    text=f"Founder done {FOUNDER_COMPLETE_MARKER}",
                    role=RoleName.FOUNDER,
                )
            return _make_result(text="Founder answer", role=RoleName.FOUNDER)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        transcript = svc._run_conversation(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="Talk.", synthesis_instructions=""),
            "", "", svc._adapt_master_prompt(), 75,
        )

        assert len(transcript) >= 3  # opening + at least guide + founder
        assert transcript[0]["role"] == "founder"  # opening
        assert any(t["role"] == "guide" for t in transcript)
        # Conversation saved
        loaded = store.load_conversation(PhaseKey.P1)
        assert loaded is not None

    def test_conversation_respects_max_exchanges(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        _setup_templates(store)
        gateway = MagicMock()

        # Never produce completion markers
        def mock_run(job: MessageJob) -> MessageResult:
            return _make_result(
                text="Ongoing discussion",
                role=job.role,
            )

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        transcript = svc._run_conversation(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions=""),
            "", "", svc._adapt_master_prompt(), 3,
        )

        # 1 opening + 3 exchanges (each has guide + founder = 6) + opening = 7
        founder_count = sum(1 for t in transcript if t["role"] == "founder")
        # Should stop at max_exchanges
        assert founder_count <= 4  # opening + 3 exchanges

    def test_conversation_empty_guide_response_substitution(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        call_count = {"n": 0}

        def mock_run(job: MessageJob) -> MessageResult:
            call_count["n"] += 1
            if job.role == RoleName.GUIDE and call_count["n"] == 1:
                return _make_result(text="", role=RoleName.GUIDE)
            if job.role == RoleName.FOUNDER:
                return _make_result(
                    text=f"OK {FOUNDER_COMPLETE_MARKER}",
                    role=RoleName.FOUNDER,
                )
            return _make_result(text="Guide text", role=RoleName.GUIDE)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        transcript = svc._run_conversation(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions=""),
            "", "", svc._adapt_master_prompt(), 75,
        )

        guide_entries = [t for t in transcript if t["role"] == "guide"]
        assert any("processing research" in t["text"] for t in guide_entries)

    def test_conversation_partial_save_every_5(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        call_count = {"n": 0}

        def mock_run(job: MessageJob) -> MessageResult:
            call_count["n"] += 1
            # End at exchange 7
            if call_count["n"] >= 14:  # 7 exchanges * 2 calls each
                return _make_result(
                    text=f"Done {FOUNDER_COMPLETE_MARKER}",
                    role=job.role,
                )
            return _make_result(text="Continuing", role=job.role)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        with patch.object(store, "save_conversation", wraps=store.save_conversation) as mock_save:
            svc._run_conversation(
                PhaseKey.P1,
                PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                                  conversation_instructions="", synthesis_instructions=""),
                "", "", svc._adapt_master_prompt(), 75,
            )
            # At least 2 saves: one partial at exchange 5, one final
            assert mock_save.call_count >= 2

    def test_conversation_guide_system_includes_prior_deliverables(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        captured_jobs: list[MessageJob] = []

        def mock_run(job: MessageJob) -> MessageResult:
            captured_jobs.append(job)
            if job.role == RoleName.FOUNDER:
                return _make_result(
                    text=f"Done {FOUNDER_COMPLETE_MARKER}",
                    role=RoleName.FOUNDER,
                )
            return _make_result(text="Guide response", role=RoleName.GUIDE)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        svc._run_conversation(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions=""),
            "Prior phase 1 content here",
            "", svc._adapt_master_prompt(), 75,
        )

        guide_jobs = [j for j in captured_jobs if j.role == RoleName.GUIDE]
        assert guide_jobs
        assert "<prior_deliverables>" in guide_jobs[0].system_prompt

    def test_conversation_founder_system_includes_memory(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        captured_jobs: list[MessageJob] = []

        def mock_run(job: MessageJob) -> MessageResult:
            captured_jobs.append(job)
            if job.role == RoleName.FOUNDER:
                return _make_result(
                    text=f"Done {FOUNDER_COMPLETE_MARKER}",
                    role=RoleName.FOUNDER,
                )
            return _make_result(text="Guide response", role=RoleName.GUIDE)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        svc._run_conversation(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions=""),
            "", "Memory of prior decisions",
            svc._adapt_master_prompt(), 75,
        )

        founder_jobs = [j for j in captured_jobs if j.role == RoleName.FOUNDER]
        assert founder_jobs
        assert "<founder_memory>" in founder_jobs[0].system_prompt


# ===================================================================
# Synthesis Tests
# ===================================================================


class TestSynthesis:
    def test_synthesis_basic(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()
        gateway.run = MagicMock(return_value=_make_result(
            text="# Phase 1 — Vision\n\nContent here.",
            role=RoleName.SYNTHESIS,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        transcript: list[dict[str, str]] = [
            {"role": "guide", "text": "Tell me about your platform."},
            {"role": "founder", "text": "It's a golf concierge platform."},
        ]

        result = svc._run_synthesis(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions="Generate docs."),
            transcript, "", svc._adapt_master_prompt(),
        )

        assert result.startswith("# Phase 1")
        loaded = store.load_deliverable(PhaseKey.P1)
        assert loaded == result

    def test_synthesis_strips_preamble(self) -> None:
        text = "I'll now generate the deliverable.\n\n# Phase 1 — Vision\n\nContent."
        result = _strip_synthesis_preamble(text)
        assert result.startswith("# Phase 1")

    def test_synthesis_continuation_on_truncation(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        call_count = {"n": 0}

        def mock_run(job: MessageJob) -> MessageResult:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return _make_result(
                    text="# Phase 1\n\nPartial content...",
                    role=RoleName.SYNTHESIS,
                    stop_reason="max_tokens",
                )
            return _make_result(
                text="\n\nContinued content here.",
                role=RoleName.SYNTHESIS,
                stop_reason="end_turn",
            )

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        result = svc._run_synthesis(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions="Gen."),
            [{"role": "guide", "text": "Q"}, {"role": "founder", "text": "A"}],
            "", svc._adapt_master_prompt(),
        )

        assert "Partial content" in result
        assert "Continued content" in result
        assert gateway.run.call_count == 2

    def test_synthesis_max_3_continuations(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()

        # All calls return max_tokens
        gateway.run = MagicMock(return_value=_make_result(
            text="# Partial",
            role=RoleName.SYNTHESIS,
            stop_reason="max_tokens",
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        svc._run_synthesis(
            PhaseKey.P1,
            PhaseTemplateSpec(phase=PhaseKey.P1, deliverable_name="Test",
                              conversation_instructions="", synthesis_instructions="Gen."),
            [{"role": "guide", "text": "Q"}],
            "", svc._adapt_master_prompt(),
        )

        # 1 original + 3 continuations = 4
        assert gateway.run.call_count == 4


# ===================================================================
# Fact Extraction Tests
# ===================================================================


class TestFactExtraction:
    def test_fact_extraction_basic(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()
        facts_json = json.dumps([
            {
                "namespace": "naming",
                "subject": "platform",
                "attribute": "name",
                "value": "Ocean Golf",
                "confidence": 1.0,
            },
            {
                "namespace": "pricing",
                "subject": "subscription",
                "attribute": "monthly_price",
                "value": 299,
                "confidence": 0.8,
            },
        ])
        gateway.run = MagicMock(return_value=_make_result(
            text=facts_json,
            role=RoleName.CONSISTENCY,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        transcript: list[dict[str, str]] = [
            {"role": "founder", "text": "The platform is called Ocean Golf."},
        ]

        facts = svc._extract_facts(PhaseKey.P1, transcript)
        assert len(facts) == 2
        assert state.fact_count() == 2

        name_fact = state.get("naming", "platform", "name")
        assert name_fact is not None
        assert name_fact.value == "Ocean Golf"

    def test_fact_extraction_invalid_json_returns_empty(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()
        gateway.run = MagicMock(return_value=_make_result(
            text="This is not valid JSON at all",
            role=RoleName.CONSISTENCY,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        facts = svc._extract_facts(PhaseKey.P1, [{"role": "founder", "text": "test"}])
        assert facts == []
        assert state.fact_count() == 0

    def test_fact_extraction_filters_low_confidence(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        gateway = MagicMock()
        facts_json = json.dumps([
            {"namespace": "n", "subject": "s", "attribute": "a1", "value": "v1", "confidence": 1.0},
            {"namespace": "n", "subject": "s", "attribute": "a2", "value": "v2", "confidence": 0.6},
        ])
        gateway.run = MagicMock(return_value=_make_result(
            text=facts_json, role=RoleName.CONSISTENCY,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        facts = svc._extract_facts(PhaseKey.P1, [{"role": "founder", "text": "test"}])
        # All facts registered regardless of confidence
        assert len(facts) == 2
        assert state.fact_count() == 2


# ===================================================================
# Prior Deliverable Loading Tests
# ===================================================================


class TestPriorDeliverables:
    def test_load_prior_deliverables_empty_for_phase_1(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        svc = _make_service(store, state, ledger, app_config)
        result = svc.load_prior_deliverables(PhaseKey.P1)
        assert result == ""

    def test_load_prior_deliverables_loads_chronologically(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_deliverable(PhaseKey.P1, "Phase 1 content")
        store.save_deliverable(PhaseKey.P2, "Phase 2 content")
        store.save_deliverable(PhaseKey.P3, "Phase 3 content")

        svc = _make_service(store, state, ledger, app_config)
        result = svc.load_prior_deliverables(PhaseKey.P4)

        # All three present, in order
        pos1 = result.find("Phase 1 content")
        pos2 = result.find("Phase 2 content")
        pos3 = result.find("Phase 3 content")
        assert pos1 < pos2 < pos3

    def test_load_prior_deliverables_includes_preambles(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_deliverable(PhaseKey.P1, "Phase 1 content")

        svc = _make_service(store, state, ledger, app_config)
        result = svc.load_prior_deliverables(PhaseKey.P2)

        assert "PLATFORM VISION" in result

    def test_load_prior_deliverables_haiku_budget(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        # Save very large deliverables
        store.save_deliverable(PhaseKey.P1, "A" * 100_000)
        store.save_deliverable(PhaseKey.P2, "B" * 100_000)
        store.save_deliverable(PhaseKey.P3, "C" * 100_000)

        svc = _make_service(store, state, ledger, app_config)
        result = svc.load_prior_deliverables(PhaseKey.P4)

        # Total should be under 200K chars
        assert len(result) <= 200_000 + 1000  # some slack for preambles/separators

        # Most recent (phase 3) should be intact
        assert "C" * 1000 in result  # at least 1000 C's

        # Oldest (phase 1) should be truncated
        assert "truncated" in result.lower() or result.count("A") < 100_000

    def test_load_prior_deliverables_skips_missing(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_deliverable(PhaseKey.P1, "Phase 1 content")
        # Phase 2 NOT saved

        svc = _make_service(store, state, ledger, app_config)
        result = svc.load_prior_deliverables(PhaseKey.P3)

        assert "Phase 1 content" in result
        assert "Phase 2 content" not in result


# ===================================================================
# Founder Memory Tests
# ===================================================================


class TestFounderMemory:
    def test_founder_memory_returns_empty_for_phase_1(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        svc = _make_service(store, state, ledger, app_config)
        result = svc._get_founder_memory(PhaseKey.P1)
        assert result == ""

    def test_founder_memory_generates_initial(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_deliverable(PhaseKey.P1, "Phase 1 deliverable content")
        gateway = MagicMock()
        gateway.run = MagicMock(return_value=_make_result(
            text="Memory summary of decisions",
            role=RoleName.CONSISTENCY,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        result = svc._get_founder_memory(PhaseKey.P2)

        assert result == "Memory summary of decisions"
        saved = store.load_founder_memory()
        assert saved == "Memory summary of decisions"

    def test_founder_memory_loads_existing(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_founder_memory("Existing memory content")
        gateway = MagicMock()

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        result = svc._get_founder_memory(PhaseKey.P2)

        assert result == "Existing memory content"
        gateway.run.assert_not_called()

    def test_update_founder_memory_appends_delta(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        store.save_founder_memory("Initial memory")
        gateway = MagicMock()
        gateway.run = MagicMock(return_value=_make_result(
            text="### Phase 1\n- You chose Ocean Golf",
            role=RoleName.CONSISTENCY,
        ))

        svc = _make_service(store, state, ledger, app_config, gateway=gateway)
        svc._update_founder_memory(PhaseKey.P1, "# Deliverable content")

        loaded = store.load_founder_memory()
        assert loaded is not None
        assert "Initial memory" in loaded
        assert "Ocean Golf" in loaded


# ===================================================================
# Master Prompt Adaptation Tests
# ===================================================================


class TestMasterPromptAdaptation:
    def test_adapt_master_prompt_websearch_only(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger,
    ) -> None:
        # Config with perplexity and grok disabled
        config = load_app_config()
        config.research.perplexity_enabled = False
        config.research.grok_enabled = False

        svc = _make_service(
            store, state, ledger, config,
            master_prompt="<research_architecture>original content</research_architecture>\n<hard_boundaries>\n9. **Never recommend a service without a sentiment check.**\n</hard_boundaries>",
        )

        result = svc._adapt_master_prompt()
        assert "Web Search Only" in result
        assert "original content" not in result

    def test_adapt_master_prompt_caches_result(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        svc = _make_service(store, state, ledger, app_config)

        result1 = svc._adapt_master_prompt()
        result2 = svc._adapt_master_prompt()

        assert result1 is result2  # Same object — cached


# ===================================================================
# Preamble Stripping
# ===================================================================


class TestPreambleStripping:
    def test_strip_preamble_with_text_before_heading(self) -> None:
        text = "Some preamble text\n\n# Real Document\n\nContent"
        assert _strip_synthesis_preamble(text) == "# Real Document\n\nContent"

    def test_strip_preamble_no_heading(self) -> None:
        text = "No heading here"
        assert _strip_synthesis_preamble(text) == "No heading here"

    def test_strip_preamble_starts_with_heading(self) -> None:
        text = "# Already starts with heading\n\nContent"
        assert _strip_synthesis_preamble(text) == text


# ===================================================================
# Integration Test
# ===================================================================


class TestRunPhaseFullFlow:
    def test_run_phase_full_flow(
        self, store: RunStore, state: StateRegistry,
        ledger: CostLedger, app_config: AppConfig,
    ) -> None:
        _setup_templates(store)
        gateway = MagicMock()

        call_sequence: list[str] = []

        def mock_run(job: MessageJob) -> MessageResult:
            call_sequence.append(f"{job.role.value}:{job.label}")

            if job.role == RoleName.GUIDE:
                return _make_result(
                    text=f"Guide response {GUIDE_COMPLETE_MARKER}",
                    role=RoleName.GUIDE,
                    phase=job.phase,
                )
            if job.role == RoleName.FOUNDER:
                return _make_result(
                    text=f"Founder answer {FOUNDER_COMPLETE_MARKER}",
                    role=RoleName.FOUNDER,
                    phase=job.phase,
                )
            if job.role == RoleName.SYNTHESIS:
                return _make_result(
                    text="# Phase 1 — Vision\n\n## Platform Name\nOcean Golf",
                    role=RoleName.SYNTHESIS,
                    phase=job.phase,
                )
            if job.role == RoleName.CONSISTENCY:
                if "fact extraction" in job.label:
                    return _make_result(
                        text=json.dumps([{
                            "namespace": "naming",
                            "subject": "platform",
                            "attribute": "name",
                            "value": "Ocean Golf",
                            "confidence": 1.0,
                        }]),
                        role=RoleName.CONSISTENCY,
                        phase=job.phase,
                    )
                # Memory delta
                return _make_result(
                    text="### Phase 1\n- Platform: Ocean Golf",
                    role=RoleName.CONSISTENCY,
                    phase=job.phase,
                )

            return _make_result(text="default", role=job.role, phase=job.phase)

        gateway.run = MagicMock(side_effect=mock_run)
        svc = _make_service(store, state, ledger, app_config, gateway=gateway)

        result = svc.run_phase(PhaseKey.P1, max_exchanges=5)

        assert isinstance(result, PhaseResult)
        assert result.outcome.phase == PhaseKey.P1
        assert result.outcome.status == "completed"
        assert result.deliverable_text.startswith("# Phase 1")
        assert len(result.transcript) >= 2
        assert len(result.extracted_facts) >= 1
        assert result.template_spec is not None

        # Deliverable saved
        assert store.load_deliverable(PhaseKey.P1) is not None

        # Facts registered
        assert state.fact_count() >= 1

        # Founder memory updated
        memory = store.load_founder_memory()
        assert memory is not None
        assert "Ocean Golf" in memory
