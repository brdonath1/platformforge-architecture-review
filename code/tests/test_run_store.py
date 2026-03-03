"""Tests for run_store.py — RunStore, StateRegistry, CostLedger."""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from src.contracts import CallUsage, CanonicalFact, PhaseKey, PhaseOutcome, RoleName, fact_key
from src.run_store import (
    CostCeilingExceeded,
    CostLedger,
    RunStore,
    StateRegistry,
    _git_blob_sha,
)


# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

def _make_usage(
    cost: str = "0.01",
    input_tokens: int = 100,
    output_tokens: int = 50,
    cache_read: int = 0,
    cache_write: int = 0,
) -> CallUsage:
    return CallUsage(
        role=RoleName.GUIDE,
        model_id="claude-haiku-4-5-20251001",
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=Decimal(cost),
    )


def _make_fact(
    namespace: str = "pricing",
    subject: str = "platform",
    attribute: str = "model",
    value: str = "B2B2C",
    phase: PhaseKey = PhaseKey.P1,
    confidence: float = 1.0,
) -> CanonicalFact:
    return CanonicalFact(
        namespace=namespace,
        subject=subject,
        attribute=attribute,
        value=value,
        source_phase=phase,
        confidence=confidence,
    )


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


# ===================================================================
# RunStore Tests
# ===================================================================


class TestRunStoreInit:
    def test_init_creates_directories(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.deliverables_dir.exists()
        assert store.conversations_dir.exists()
        assert store.metrics_dir.exists()
        assert store.templates_dir.exists()

    def test_init_with_custom_root(self, tmp_path: Path) -> None:
        custom = tmp_path / "custom"
        store = RunStore(root=custom)
        assert store.root == custom
        assert store.deliverables_dir == custom / "output" / "deliverables"

    def test_init_idempotent(self, tmp_path: Path) -> None:
        RunStore(root=tmp_path)
        RunStore(root=tmp_path)  # No exception


class TestRunStoreDeliverable:
    def test_save_and_load_deliverable(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        content = "# Phase 1 Deliverable\n\nContent here."
        store.save_deliverable(PhaseKey.P1, content)
        loaded = store.load_deliverable(PhaseKey.P1)
        assert loaded == content

    def test_load_deliverable_not_found(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.load_deliverable(PhaseKey.P1) is None

    def test_save_deliverable_filename_format(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_deliverable(PhaseKey.P1, "test")
        assert path.name == "deliverable-1.md"

    def test_save_deliverable_6a(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_deliverable(PhaseKey.P6A, "test")
        assert path.name == "deliverable-6a.md"


class TestRunStoreConversation:
    def test_save_and_load_conversation(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        transcript: list[dict[str, object]] = [
            {"role": "guide", "content": "Hello"},
            {"role": "founder", "content": "Hi"},
        ]
        store.save_conversation(PhaseKey.P1, transcript)
        loaded = store.load_conversation(PhaseKey.P1)
        assert loaded == transcript

    def test_load_conversation_not_found(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.load_conversation(PhaseKey.P1) is None

    def test_conversation_json_formatting(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        transcript: list[dict[str, object]] = [{"role": "guide", "content": "Hi"}]
        path = store.save_conversation(PhaseKey.P1, transcript)
        raw = path.read_text(encoding="utf-8")
        # indent=2 means lines with leading spaces
        assert "\n  " in raw


class TestRunStoreMetrics:
    def test_save_phase_metrics(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        metrics: dict[str, object] = {"phase": "1", "status": "COMPLETED"}
        path = store.save_phase_metrics(PhaseKey.P1, metrics)
        assert path.exists()
        loaded: dict[str, object] = json.loads(path.read_text(encoding="utf-8"))
        assert loaded["phase"] == "1"

    def test_save_timing_waterfall(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        wf: dict[str, object] = {"run_start": "2026-03-03T00:00:00", "phases": []}
        path = store.save_timing_waterfall(wf)
        assert path.name == "timing-waterfall.json"
        assert path.exists()

    def test_save_cost_report_creates_both_files(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        report: dict[str, object] = {"total_cost_usd": "1.23"}
        archive, latest = store.save_cost_report(report)
        assert archive.exists()
        assert latest.exists()
        assert latest.name == "cost-report.json"
        assert archive.name.startswith("cost-report-")
        assert archive.name != latest.name

    def test_save_consistency_report(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        report: dict[str, object] = {"issues": []}
        path = store.save_consistency_report(report)
        assert path.name == "cross-phase-consistency.json"
        assert path.exists()


class TestRunStoreResume:
    def test_detect_completed_phases_empty(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.detect_completed_phases() == []

    def test_detect_completed_phases_partial(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.save_deliverable(PhaseKey.P1, "d1")
        store.save_deliverable(PhaseKey.P3, "d3")
        found = store.detect_completed_phases()
        assert PhaseKey.P1 in found
        assert PhaseKey.P3 in found
        assert PhaseKey.P2 not in found

    def test_detect_completed_phases_order(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        # Save in reverse order
        store.save_deliverable(PhaseKey.P3, "d3")
        store.save_deliverable(PhaseKey.P1, "d1")
        store.save_deliverable(PhaseKey.P2, "d2")
        found = store.detect_completed_phases()
        assert found == [PhaseKey.P1, PhaseKey.P2, PhaseKey.P3]

    def test_build_phase_outcome(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.save_deliverable(PhaseKey.P1, "# Deliverable\nContent here")
        store.save_conversation(
            PhaseKey.P1,
            [
                {"role": "guide", "content": "q1"},
                {"role": "founder", "content": "a1"},
                {"role": "guide", "content": "q2"},
                {"role": "founder", "content": "a2"},
            ],
        )
        store.save_phase_metrics(
            PhaseKey.P1,
            {
                "cost_usd": "1.50",
                "elapsed_seconds": 120.5,
                "started_at": "2026-03-03T10:00:00",
                "completed_at": "2026-03-03T10:02:00",
            },
        )

        outcome = store.build_phase_outcome(PhaseKey.P1)
        assert isinstance(outcome, PhaseOutcome)
        assert outcome.phase == PhaseKey.P1
        assert outcome.status == "completed"
        assert outcome.exchange_count == 2
        assert outcome.deliverable_chars == len("# Deliverable\nContent here")
        assert outcome.cost_usd == Decimal("1.50")
        assert outcome.elapsed_seconds == 120.5
        assert outcome.started_at == "2026-03-03T10:00:00"
        assert outcome.completed_at == "2026-03-03T10:02:00"

    def test_build_phase_outcome_missing_deliverable(
        self, tmp_path: Path
    ) -> None:
        store = RunStore(root=tmp_path)
        with pytest.raises(FileNotFoundError):
            store.build_phase_outcome(PhaseKey.P1)


class TestRunStoreFounderMemory:
    def test_save_founder_memory(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_founder_memory("# Memory\nDecisions here.")
        assert path.exists()
        assert path.name == "founder-memory.md"
        assert path.read_text(encoding="utf-8") == "# Memory\nDecisions here."

    def test_load_founder_memory_returns_none_when_missing(
        self, tmp_path: Path
    ) -> None:
        store = RunStore(root=tmp_path)
        assert store.load_founder_memory() is None

    def test_load_founder_memory_round_trip(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.save_founder_memory("test memory content")
        loaded = store.load_founder_memory()
        assert loaded == "test memory content"


class TestRunStoreReviewArtifacts:
    def test_save_review_findings(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_review_findings(PhaseKey.P1, 2, '{"findings": []}')
        assert path.exists()
        assert path.name == "phase-1-l2-review.json"

    def test_save_review_pipeline_summary(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_review_pipeline_summary(PhaseKey.P1, '{"summary": {}}')
        assert path.exists()
        assert path.name == "phase-1-review-pipeline.json"

    def test_save_interview_brief(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_interview_brief(PhaseKey.P1, "<brief>test</brief>")
        assert path.exists()
        assert path.name == "phase-1-interview-brief.xml"

    def test_save_reengagement_transcript(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_reengagement_transcript(PhaseKey.P1, '[{"role": "guide"}]')
        assert path.exists()
        assert path.name == "phase-1-reengagement.json"

    def test_save_correction_debug(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        path = store.save_correction_debug(PhaseKey.P1, 2, "<corrections>xml</corrections>")
        assert path.exists()
        assert path.name == "phase-1-correction-2-raw.txt"


class TestRunStoreTemplateCache:
    def test_cache_and_load_template(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        store.cache_template("phase-1-conversation.md", "# Template")
        loaded = store.load_cached_template("phase-1-conversation.md")
        assert loaded == "# Template"

    def test_load_cached_template_not_found(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        assert store.load_cached_template("nonexistent.md") is None


class TestRunStoreGitHub:
    """GitHub publishing tests using mocked urllib."""

    def _blob_sha(self, content: bytes) -> str:
        header = f"blob {len(content)}\0".encode("ascii")
        return hashlib.sha1(header + content).hexdigest()

    def test_publish_new_file(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        (store.deliverables_dir / "deliverable-1.md").write_text(
            "content", encoding="utf-8"
        )

        def mock_urlopen(req: Any) -> _FakeHTTPResponse:
            if req.get_method() == "GET":
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", {}, BytesIO(b"")  # type: ignore[arg-type]
                )
            return _FakeHTTPResponse(b'{"content": {}}', 201)

        with patch("src.run_store.urllib.request.urlopen", side_effect=mock_urlopen):
            stats = store.publish_to_github(
                PhaseKey.P1, "owner/repo", "fake-token"
            )
        assert stats["pushed"] == 1
        assert stats["skipped"] == 0
        assert stats["failed"] == 0

    def test_publish_unchanged_file(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        content = b"content"
        (store.deliverables_dir / "deliverable-1.md").write_bytes(content)
        sha = self._blob_sha(content)

        def mock_urlopen(req: Any) -> _FakeHTTPResponse:
            return _FakeHTTPResponse(
                json.dumps({"sha": sha}).encode(), 200
            )

        with patch("src.run_store.urllib.request.urlopen", side_effect=mock_urlopen):
            stats = store.publish_to_github(
                PhaseKey.P1, "owner/repo", "fake-token"
            )
        assert stats["skipped"] == 1
        assert stats["pushed"] == 0

    def test_publish_changed_file(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        (store.deliverables_dir / "deliverable-1.md").write_text(
            "new content", encoding="utf-8"
        )

        call_count = {"get": 0, "put": 0}

        def mock_urlopen(req: Any) -> _FakeHTTPResponse:
            if req.get_method() == "GET":
                call_count["get"] += 1
                return _FakeHTTPResponse(
                    json.dumps({"sha": "old-sha-different"}).encode(), 200
                )
            call_count["put"] += 1
            return _FakeHTTPResponse(b'{"content": {}}', 200)

        with patch("src.run_store.urllib.request.urlopen", side_effect=mock_urlopen):
            stats = store.publish_to_github(
                PhaseKey.P1, "owner/repo", "fake-token"
            )
        assert stats["pushed"] == 1
        assert call_count["put"] == 1

    def test_publish_failure_nonfatal(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        (store.deliverables_dir / "deliverable-1.md").write_text(
            "a", encoding="utf-8"
        )
        (store.deliverables_dir / "deliverable-2.md").write_text(
            "b", encoding="utf-8"
        )

        call_index = {"i": 0}

        def mock_urlopen(req: Any) -> _FakeHTTPResponse:
            if req.get_method() == "GET":
                raise urllib.error.HTTPError(
                    req.full_url, 404, "Not Found", {}, BytesIO(b"")  # type: ignore[arg-type]
                )
            # First PUT fails, second succeeds
            call_index["i"] += 1
            if call_index["i"] == 1:
                raise urllib.error.HTTPError(
                    req.full_url, 500, "Server Error", {}, BytesIO(b"")  # type: ignore[arg-type]
                )
            return _FakeHTTPResponse(b'{"content": {}}', 201)

        with patch("src.run_store.urllib.request.urlopen", side_effect=mock_urlopen):
            stats = store.publish_to_github(
                PhaseKey.P1, "owner/repo", "fake-token"
            )
        assert stats["failed"] == 1
        assert stats["pushed"] == 1

    def test_publish_empty_output(self, tmp_path: Path) -> None:
        store = RunStore(root=tmp_path)
        # No files in output directories
        stats = store.publish_to_github(
            PhaseKey.P1, "owner/repo", "fake-token"
        )
        assert stats == {"pushed": 0, "skipped": 0, "failed": 0}

    def test_git_blob_sha_matches(self) -> None:
        content = b"hello world"
        expected_header = f"blob {len(content)}\0".encode("ascii")
        expected = hashlib.sha1(expected_header + content).hexdigest()
        assert _git_blob_sha(content) == expected


# ===================================================================
# StateRegistry Tests
# ===================================================================


class TestStateRegistryBasic:
    def test_register_new_fact(self) -> None:
        reg = StateRegistry()
        f = _make_fact()
        assert reg.register(f) is True
        got = reg.get("pricing", "platform", "model")
        assert got is not None
        assert got.value == "B2B2C"

    def test_register_duplicate_key_same_phase(self) -> None:
        reg = StateRegistry()
        f1 = _make_fact(value="v1")
        f2 = _make_fact(value="v2")  # Same key, same phase
        reg.register(f1)
        result = reg.register(f2)
        assert result is False
        assert reg.get("pricing", "platform", "model") is not None
        got = reg.get("pricing", "platform", "model")
        assert got is not None and got.value == "v1"

    def test_get_nonexistent(self) -> None:
        reg = StateRegistry()
        assert reg.get("no", "such", "fact") is None

    def test_fact_count(self) -> None:
        reg = StateRegistry()
        assert reg.fact_count() == 0
        reg.register(_make_fact())
        assert reg.fact_count() == 1
        reg.register(_make_fact(attribute="name"))
        assert reg.fact_count() == 2


class TestStateRegistrySupersession:
    def test_supersession_later_phase_wins(self) -> None:
        reg = StateRegistry()
        f1 = _make_fact(value="old", phase=PhaseKey.P1)
        f5 = _make_fact(value="new", phase=PhaseKey.P5)
        reg.register(f1)
        result = reg.register(f5)
        assert result is True
        got = reg.get("pricing", "platform", "model")
        assert got is not None and got.value == "new"

    def test_supersession_earlier_phase_rejected(self) -> None:
        reg = StateRegistry()
        f5 = _make_fact(value="current", phase=PhaseKey.P5)
        f1 = _make_fact(value="stale", phase=PhaseKey.P1)
        reg.register(f5)
        result = reg.register(f1)
        assert result is False
        got = reg.get("pricing", "platform", "model")
        assert got is not None and got.value == "current"

    def test_supersession_log_recorded(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(value="old", phase=PhaseKey.P1))
        reg.register(_make_fact(value="new", phase=PhaseKey.P5))
        assert len(reg._supersession_log) == 1
        entry = reg._supersession_log[0]
        assert entry["key"] == "pricing:platform.model"
        assert entry["old_phase"] == "1"
        assert entry["new_phase"] == "5"

    def test_6a_supersedes_5(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(value="v5", phase=PhaseKey.P5))
        result = reg.register(_make_fact(value="v6a", phase=PhaseKey.P6A))
        assert result is True
        got = reg.get("pricing", "platform", "model")
        assert got is not None and got.value == "v6a"

    def test_6b_supersedes_6a(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(value="v6a", phase=PhaseKey.P6A))
        result = reg.register(_make_fact(value="v6b", phase=PhaseKey.P6B))
        assert result is True
        got = reg.get("pricing", "platform", "model")
        assert got is not None and got.value == "v6b"


class TestStateRegistryQueries:
    def test_query_namespace(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(namespace="pricing", attribute="model"))
        reg.register(_make_fact(namespace="pricing", attribute="tier"))
        reg.register(_make_fact(namespace="arch", attribute="db"))
        results = reg.query_namespace("pricing")
        assert len(results) == 2
        assert all(f.namespace == "pricing" for f in results)

    def test_query_namespace_empty(self) -> None:
        reg = StateRegistry()
        assert reg.query_namespace("nonexistent") == []

    def test_query_phase(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(attribute="a", phase=PhaseKey.P1))
        reg.register(_make_fact(attribute="b", phase=PhaseKey.P2))
        results = reg.query_phase(PhaseKey.P1)
        assert len(results) == 1
        assert results[0].source_phase == PhaseKey.P1

    def test_query_subject(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(subject="platform", attribute="model"))
        reg.register(_make_fact(subject="platform", attribute="name"))
        reg.register(_make_fact(subject="database", attribute="engine"))
        results = reg.query_subject("pricing", "platform")
        assert len(results) == 2
        assert all(f.subject == "platform" for f in results)

    def test_all_facts(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(namespace="b", attribute="x"))
        reg.register(_make_fact(namespace="a", attribute="y"))
        facts = reg.all_facts()
        assert len(facts) == 2
        # Ordered by key: "a:..." < "b:..."
        assert facts[0].namespace == "a"
        assert facts[1].namespace == "b"

    def test_all_facts_after_supersession(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(value="old", phase=PhaseKey.P1))
        reg.register(_make_fact(value="new", phase=PhaseKey.P5))
        facts = reg.all_facts()
        assert len(facts) == 1
        assert facts[0].value == "new"


class TestStateRegistrySerialization:
    def test_to_json_and_from_json_roundtrip(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(namespace="pricing", attribute="model"))
        reg.register(_make_fact(namespace="arch", subject="db", attribute="engine", value="postgres"))
        data = reg.to_json()
        restored = StateRegistry.from_json(data)
        assert restored.fact_count() == 2
        got = restored.get("pricing", "platform", "model")
        assert got is not None and got.value == "B2B2C"

    def test_to_json_includes_supersession_log(self) -> None:
        reg = StateRegistry()
        reg.register(_make_fact(value="old", phase=PhaseKey.P1))
        reg.register(_make_fact(value="new", phase=PhaseKey.P5))
        data = json.loads(reg.to_json())
        assert "supersession_log" in data
        assert len(data["supersession_log"]) == 1

    def test_from_json_preserves_fact_values(self) -> None:
        reg = StateRegistry()
        f = _make_fact(
            namespace="test",
            subject="s",
            attribute="a",
            value="hello",
            phase=PhaseKey.P3,
            confidence=0.8,
        )
        reg.register(f)
        restored = StateRegistry.from_json(reg.to_json())
        got = restored.get("test", "s", "a")
        assert got is not None
        assert got.value == "hello"
        assert got.source_phase == PhaseKey.P3
        assert got.confidence == 0.8

    def test_save_and_load_file(self, tmp_path: Path) -> None:
        reg = StateRegistry()
        reg.register(_make_fact())
        path = tmp_path / "registry.json"
        reg.save(path)
        loaded = StateRegistry.load(path)
        assert loaded.fact_count() == 1
        got = loaded.get("pricing", "platform", "model")
        assert got is not None and got.value == "B2B2C"


# ===================================================================
# CostLedger Tests
# ===================================================================


class TestCostLedgerBasic:
    def test_record_single_call(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        usage = _make_usage(cost="0.05")
        ledger.record(PhaseKey.P1, usage)
        assert ledger.total_cost_usd == Decimal("0.05")

    def test_record_multiple_calls(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        ledger.record(PhaseKey.P1, _make_usage(cost="0.10"))
        ledger.record(PhaseKey.P1, _make_usage(cost="0.20"))
        ledger.record(PhaseKey.P2, _make_usage(cost="0.30"))
        assert ledger.total_cost_usd == Decimal("0.60")

    def test_record_external_call(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        ledger.record_external(PhaseKey.P1, "perplexity", Decimal("0.05"))
        assert ledger.total_cost_usd == Decimal("0.05")

    def test_phase_summary(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        ledger.record(
            PhaseKey.P1,
            _make_usage(cost="0.10", input_tokens=500, output_tokens=200),
        )
        ledger.record(
            PhaseKey.P1,
            _make_usage(cost="0.05", input_tokens=300, output_tokens=100),
        )
        summary = ledger.phase_summary(PhaseKey.P1)
        assert summary["calls"] == 2
        assert summary["input_tokens"] == 800
        assert summary["output_tokens"] == 300
        assert summary["cost_usd"] == "0.15"

    def test_phase_summary_unknown_phase(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        assert ledger.phase_summary(PhaseKey.P9) == {}


class TestCostLedgerBudget:
    def test_ceiling_not_exceeded(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("1.00"))
        ledger.record(PhaseKey.P1, _make_usage(cost="0.50"))
        # No exception

    def test_ceiling_exceeded_raises(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("1.00"))
        ledger.record(PhaseKey.P1, _make_usage(cost="0.80"))
        with pytest.raises(CostCeilingExceeded):
            ledger.record(PhaseKey.P1, _make_usage(cost="0.30"))

    def test_ceiling_exceeded_fields(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("1.00"))
        ledger.record(PhaseKey.P1, _make_usage(cost="0.80"))
        with pytest.raises(CostCeilingExceeded) as exc_info:
            ledger.record(PhaseKey.P1, _make_usage(cost="0.30"))
        assert exc_info.value.current == Decimal("0.80")
        assert exc_info.value.attempted == Decimal("0.30")
        assert exc_info.value.ceiling == Decimal("1.00")

    def test_remaining_budget(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("10.00"))
        ledger.record(PhaseKey.P1, _make_usage(cost="3.50"))
        assert ledger.remaining_budget_usd == Decimal("6.50")


class TestCostLedgerThreadSafety:
    def test_concurrent_recording(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("10000"))
        per_call = Decimal("0.01")
        threads_count = 10
        calls_per_thread = 100

        def worker(phase: PhaseKey) -> None:
            for _ in range(calls_per_thread):
                ledger.record(phase, _make_usage(cost=str(per_call)))

        threads = [
            threading.Thread(
                target=worker,
                args=(PhaseKey.P1,),
            )
            for _ in range(threads_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        expected = per_call * threads_count * calls_per_thread
        assert ledger.total_cost_usd == expected

    def test_concurrent_ceiling_check(self) -> None:
        ceiling = Decimal("1.00")
        ledger = CostLedger(hard_ceiling_usd=ceiling)
        errors: list[CostCeilingExceeded] = []
        successes: list[bool] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                ledger.record(PhaseKey.P1, _make_usage(cost="0.20"))
                with lock:
                    successes.append(True)
            except CostCeilingExceeded as e:
                with lock:
                    errors.append(e)

        # 6 threads × $0.20 = $1.20 > $1.00 ceiling
        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Exactly 5 should succeed ($1.00), 1 should fail
        assert len(successes) == 5
        assert len(errors) == 1
        assert ledger.total_cost_usd == Decimal("1.00")


class TestCostLedgerReport:
    def test_build_report_structure(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        ledger.record(PhaseKey.P1, _make_usage(cost="1.00"))
        report = ledger.build_report()
        assert "timestamp" in report
        assert "total" in report
        assert "phases" in report
        assert "ceiling_usd" in report
        assert "remaining_usd" in report

    def test_build_report_decimal_serialization(self) -> None:
        ledger = CostLedger(hard_ceiling_usd=Decimal("200"))
        ledger.record(PhaseKey.P1, _make_usage(cost="1.50"))
        report = ledger.build_report()
        total = report["total"]
        assert isinstance(total, dict)
        assert isinstance(total["total_cost_usd"], str)
        assert total["total_cost_usd"] == "1.50"
        assert isinstance(report["ceiling_usd"], str)
        assert report["ceiling_usd"] == "200"
        assert isinstance(report["remaining_usd"], str)
