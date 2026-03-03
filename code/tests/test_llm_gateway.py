"""
Tests for llm_gateway.py

All tests use mocked responses — zero live API calls.

Decision Authority: D-196, D-197
"""

from __future__ import annotations

import json
import time
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.contracts import (
    CallUsage,
    MessageJob,
    MessageResult,
    PhaseKey,
    RoleName,
)
from src.settings import AppConfig, load_app_config
from src.llm_gateway import (
    AnthropicGateway,
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_MULTIPLIER,
    MAX_RETRIES,
    MAX_TOOL_CONTINUATIONS,
    PerplexityGateway,
    GrokGateway,
)

# ---------------------------------------------------------------------------
# Fixtures directory
# ---------------------------------------------------------------------------

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict[str, Any]:
    """Load a JSON fixture file."""
    with open(FIXTURES_DIR / name, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _make_content_block(block_data: dict[str, Any]) -> Any:
    """Turn a fixture content block dict into a real SDK type object."""
    from anthropic.types import TextBlock, ThinkingBlock, ToolUseBlock

    btype = block_data.get("type")
    if btype == "text":
        return TextBlock(type="text", text=block_data["text"])
    elif btype == "thinking":
        return ThinkingBlock(
            type="thinking",
            thinking=block_data["thinking"],
            signature="sig_test",
        )
    elif btype == "tool_use":
        return ToolUseBlock(
            type="tool_use",
            id=block_data["id"],
            name=block_data["name"],
            input=block_data["input"],
            caller=None,
        )
    # Fallback for unknown types
    return SimpleNamespace(**block_data)


def _make_usage(usage_data: dict[str, Any]) -> SimpleNamespace:
    """Turn fixture usage dict into a usage object."""
    return SimpleNamespace(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        cache_creation_input_tokens=usage_data.get("cache_creation_input_tokens", 0),
        cache_read_input_tokens=usage_data.get("cache_read_input_tokens", 0),
    )


def _make_mock_response(fixture: dict[str, Any]) -> SimpleNamespace:
    """Build a mock response object from a fixture dict."""
    content = [_make_content_block(b) for b in fixture["content"]]
    usage = _make_usage(fixture.get("usage", {}))
    return SimpleNamespace(
        id=fixture["id"],
        content=content,
        model=fixture["model"],
        stop_reason=fixture.get("stop_reason", "end_turn"),
        usage=usage,
    )


def _make_mock_stream(fixture: dict[str, Any]) -> MagicMock:
    """Build a mock stream context manager that returns get_final_message()."""
    response = _make_mock_response(fixture)
    stream = MagicMock()
    stream.get_final_message.return_value = response
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    return stream


def build_gateway_with_mock(
    fixture: dict[str, Any] | list[dict[str, Any]],
    config: AppConfig | None = None,
) -> tuple[AnthropicGateway, MagicMock]:
    """Build an AnthropicGateway with a mocked Anthropic client.

    If fixture is a list, subsequent calls return subsequent fixtures
    (for tool continuation testing).
    """
    if config is None:
        config = load_app_config(
            Path(__file__).parent.parent.parent / "config.json"
        )

    with patch("src.llm_gateway.anthropic.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        if isinstance(fixture, list):
            streams = [_make_mock_stream(f) for f in fixture]
            mock_client.messages.stream.side_effect = streams
        else:
            mock_client.messages.stream.return_value = _make_mock_stream(fixture)

        gateway = AnthropicGateway(config)

    # Reassign the mock client (since __init__ already ran)
    gateway._client = mock_client
    return gateway, mock_client


def make_job(
    role: RoleName = RoleName.GUIDE,
    phase: PhaseKey = PhaseKey.P1,
    label: str = "test-job",
    **kwargs: Any,
) -> MessageJob:
    """Helper to build a MessageJob with defaults."""
    defaults: dict[str, Any] = {
        "messages": [{"role": "user", "content": "Hello"}],
    }
    defaults.update(kwargs)
    return MessageJob(
        role=role,
        phase=phase,
        label=label,
        **defaults,
    )


# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

@pytest.fixture
def config() -> AppConfig:
    """Load real config.json."""
    return load_app_config(
        Path(__file__).parent.parent.parent / "config.json"
    )


# ===========================================================================
# THINKING NORMALIZATION TESTS
# ===========================================================================

class TestThinkingNormalization:
    """Test that thinking is correctly resolved per tier/role/job."""

    def test_thinking_disabled_for_haiku(self, config: AppConfig) -> None:
        """Haiku tier: thinking param must NOT appear in API params."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job()
        gateway.run(job)

        call_kwargs = mock_client.messages.stream.call_args
        params = call_kwargs.kwargs if call_kwargs.kwargs else call_kwargs[1]
        if not params:
            # Might be positional
            params = {}
            if call_kwargs.args:
                params = call_kwargs.args[0] if isinstance(call_kwargs.args[0], dict) else {}
        assert "thinking" not in params, (
            "Haiku tier must NOT include thinking parameter"
        )

    def test_thinking_disabled_even_with_job_override(self, config: AppConfig) -> None:
        """Haiku: even if job requests thinking, model doesn't support it."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job(thinking_budget=5000)
        gateway.run(job)

        call_kwargs = mock_client.messages.stream.call_args
        # Extract the kwargs passed to stream()
        actual_params = call_kwargs[1] if call_kwargs[1] else {}
        assert "thinking" not in actual_params

    def test_thinking_resolution_disabled_string(self, config: AppConfig) -> None:
        """When policy thinking is 'disabled', _resolve_thinking returns None."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)
        from src.settings import RoleExecutionPolicy
        policy = RoleExecutionPolicy(
            input_budget=100000, output_budget=12000,
            thinking="disabled", max_parallel=1,
        )
        job = make_job()
        result = gateway._resolve_thinking(job, policy)
        assert result is None

    def test_thinking_resolution_enabled_with_sonnet_model(self) -> None:
        """For a model that supports thinking, 'enabled' policy returns budget."""
        config = load_app_config(
            Path(__file__).parent.parent.parent / "config.json"
        )
        # Temporarily switch to sonnet tier for this test
        config.runtime.active_tier = "sonnet_4_5"

        fixture = load_fixture("fixture_thinking_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        from src.settings import RoleExecutionPolicy
        policy = RoleExecutionPolicy(
            input_budget=180000, output_budget=16000,
            thinking="enabled", max_parallel=1,
        )
        job = make_job()
        result = gateway._resolve_thinking(job, policy)
        assert result is not None
        assert result["type"] == "enabled"
        assert result["budget_tokens"] == 16000  # output_budget

    def test_thinking_resolution_numeric_string(self, config: AppConfig) -> None:
        """Numeric string in policy -> enabled with that budget."""
        # Need a model that supports thinking
        config.runtime.active_tier = "sonnet_4_5"
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        from src.settings import RoleExecutionPolicy
        policy = RoleExecutionPolicy(
            input_budget=180000, output_budget=16000,
            thinking="10000", max_parallel=1,
        )
        job = make_job()
        result = gateway._resolve_thinking(job, policy)
        assert result is not None
        assert result["budget_tokens"] == 10000

    def test_thinking_job_override_zero_disables(self, config: AppConfig) -> None:
        """job.thinking_budget == 0 -> None, even if model supports it."""
        config.runtime.active_tier = "sonnet_4_5"
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        from src.settings import RoleExecutionPolicy
        policy = RoleExecutionPolicy(
            input_budget=180000, output_budget=16000,
            thinking="enabled", max_parallel=1,
        )
        job = make_job(thinking_budget=0)
        result = gateway._resolve_thinking(job, policy)
        assert result is None


# ===========================================================================
# STREAMING PARSE TESTS
# ===========================================================================

class TestStreamingParse:
    """Test response parsing from fixtures."""

    def test_parse_text_only(self, config: AppConfig) -> None:
        """Text-only response: text field populated, no thinking."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.error is None
        assert result.text == "This is a test response from the guide."
        assert result.thinking_text == ""
        assert result.tool_use_blocks == []
        assert result.stop_reason == "end_turn"

    def test_parse_thinking_plus_text(self, config: AppConfig) -> None:
        """Response with thinking + text: both fields separated."""
        fixture = load_fixture("fixture_thinking_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.error is None
        assert "pricing model" in result.thinking_text
        assert "analysis" in result.text
        assert result.thinking_text != result.text

    def test_parse_tool_use_blocks(self, config: AppConfig) -> None:
        """Response with tool_use: blocks captured with id, name, input."""
        # Use text response for the continuation
        tool_fixture = load_fixture("fixture_tool_use_response.json")
        text_fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock([tool_fixture, text_fixture], config)

        job = make_job()
        result = gateway.run(job)

        # After tool continuation, tool_use_blocks should be populated
        assert len(result.tool_use_blocks) >= 1
        first_tool = result.tool_use_blocks[0]
        assert first_tool["name"] == "web_search"
        assert first_tool["id"] == "toolu_test_001"

    def test_parse_usage_stats(self, config: AppConfig) -> None:
        """Usage tokens extracted correctly into CallUsage."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.usage is not None
        assert result.usage.input_tokens == 100
        assert result.usage.output_tokens == 25
        assert result.usage.model_id == "claude-haiku-4-5-20251001"

    def test_parse_cache_tokens(self, config: AppConfig) -> None:
        """Cache tokens extracted from thinking fixture."""
        fixture = load_fixture("fixture_thinking_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.usage is not None
        assert result.usage.cache_write_tokens == 50
        assert result.usage.cache_read_tokens == 30


# ===========================================================================
# RETRY TESTS
# ===========================================================================

class TestRetryLogic:
    """Test retry behavior on various error types."""

    def test_retry_on_429(self, config: AppConfig) -> None:
        """429 triggers retry, succeeds on attempt 2."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        # First call raises 429, second succeeds
        error_429 = _make_api_status_error(429)
        stream_ok = _make_mock_stream(fixture)
        mock_client.messages.stream.side_effect = [error_429, stream_ok]

        job = make_job()
        with patch("src.llm_gateway.time.sleep"):  # Skip actual sleep
            result = gateway.run(job)

        assert result.error is None
        assert result.retries_attempted == 1
        assert result.text == "This is a test response from the guide."

    def test_retry_on_500(self, config: AppConfig) -> None:
        """500 triggers retry with backoff."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        error_500 = _make_api_status_error(500)
        stream_ok = _make_mock_stream(fixture)
        mock_client.messages.stream.side_effect = [error_500, stream_ok]

        job = make_job()
        with patch("src.llm_gateway.time.sleep") as mock_sleep:
            result = gateway.run(job)

        assert result.error is None
        assert result.retries_attempted == 1
        mock_sleep.assert_called_once()

    def test_no_retry_on_400(self, config: AppConfig) -> None:
        """400 fails immediately, no retries."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        error_400 = _make_api_status_error(400)
        mock_client.messages.stream.side_effect = error_400

        job = make_job()
        result = gateway.run(job)

        assert result.error is not None
        assert "400" in result.error
        assert result.retries_attempted == 0

    def test_no_retry_on_401(self, config: AppConfig) -> None:
        """401 auth error fails immediately."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        error_401 = _make_api_status_error(401)
        mock_client.messages.stream.side_effect = error_401

        job = make_job()
        result = gateway.run(job)

        assert result.error is not None
        assert "401" in result.error
        assert result.retries_attempted == 0

    def test_max_retries_exhausted(self, config: AppConfig) -> None:
        """After MAX_RETRIES, error is set."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        error_529 = _make_api_status_error(529)
        mock_client.messages.stream.side_effect = error_529

        job = make_job()
        with patch("src.llm_gateway.time.sleep"):
            result = gateway.run(job)

        assert result.error is not None
        assert "529" in result.error
        assert result.retries_attempted == MAX_RETRIES

    def test_retry_backoff_timing(self, config: AppConfig) -> None:
        """Verify exponential backoff: 2s, 4s, 8s."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        error_503 = _make_api_status_error(503)
        mock_client.messages.stream.side_effect = error_503

        job = make_job()
        with patch("src.llm_gateway.time.sleep") as mock_sleep:
            gateway.run(job)

        # Should have slept 3 times (attempts 1, 2, 3 with backoff)
        assert mock_sleep.call_count == MAX_RETRIES
        calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert calls[0] == pytest.approx(2.0)  # 2^1
        assert calls[1] == pytest.approx(4.0)  # 2^2
        assert calls[2] == pytest.approx(8.0)  # 2^3

    def test_connection_error_retries(self, config: AppConfig) -> None:
        """APIConnectionError triggers retry."""
        import anthropic as anth

        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        conn_error = anth.APIConnectionError(request=MagicMock())
        stream_ok = _make_mock_stream(fixture)
        mock_client.messages.stream.side_effect = [conn_error, stream_ok]

        job = make_job()
        with patch("src.llm_gateway.time.sleep"):
            result = gateway.run(job)

        assert result.error is None
        assert result.retries_attempted == 1


# ===========================================================================
# COST CALCULATION TESTS
# ===========================================================================

class TestCostCalculation:
    """Test cost calculation logic."""

    def test_cost_haiku_basic(self, config: AppConfig) -> None:
        """Haiku pricing: $1/Mtok in, $5/Mtok out."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.usage is not None
        # 100 input * $1/M + 25 output * $5/M
        expected = Decimal("100") / Decimal("1000000") * Decimal("1.00") + \
                   Decimal("25") / Decimal("1000000") * Decimal("5.00")
        assert result.usage.cost_usd == expected

    def test_cost_with_cache(self, config: AppConfig) -> None:
        """Cache pricing: write 1.25x, read 0.1x input price."""
        fixture = load_fixture("fixture_thinking_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert result.usage is not None
        # 200 in, 100 out, 50 cache_write, 30 cache_read
        # Haiku: $1/Mtok in, $5/Mtok out
        million = Decimal("1000000")
        in_price = Decimal("1.00")
        out_price = Decimal("5.00")
        expected = (
            Decimal("200") / million * in_price
            + Decimal("100") / million * out_price
            + Decimal("50") / million * in_price * CACHE_WRITE_MULTIPLIER
            + Decimal("30") / million * in_price * CACHE_READ_MULTIPLIER
        )
        assert result.usage.cost_usd == expected

    def test_estimate_cost_matches_settings(self, config: AppConfig) -> None:
        """estimate_cost() should match settings.estimate_reserved_cost()."""
        from src.settings import estimate_reserved_cost

        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job(role=RoleName.GUIDE)
        gateway_estimate = gateway.estimate_cost(job)
        settings_estimate = estimate_reserved_cost(config, [job])

        assert gateway_estimate == settings_estimate

    def test_estimate_cost_positive(self, config: AppConfig) -> None:
        """All roles produce positive cost estimates."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        for role in RoleName:
            job = make_job(role=role)
            cost = gateway.estimate_cost(job)
            assert cost > Decimal("0"), f"Role {role.value} has zero cost"


# ===========================================================================
# TOOL CONTINUATION TESTS
# ===========================================================================

class TestToolContinuation:
    """Test tool_use -> continuation flow."""

    def test_continuation_extends_messages(self, config: AppConfig) -> None:
        """After tool_use, messages list grows with assistant + user turns."""
        tool_fixture = load_fixture("fixture_tool_use_response.json")
        text_fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(
            [tool_fixture, text_fixture], config
        )

        job = make_job()
        result = gateway.run(job)

        # Should have made 2 calls total
        assert mock_client.messages.stream.call_count == 2

        # Second call should have more messages
        second_call = mock_client.messages.stream.call_args_list[1]
        second_params = second_call[1] if second_call[1] else {}
        msgs = second_params.get("messages", [])
        # Original message + assistant tool_use + user tool_result
        assert len(msgs) >= 3

    def test_continuation_merges_usage(self, config: AppConfig) -> None:
        """Usage from both calls is summed."""
        tool_fixture = load_fixture("fixture_tool_use_response.json")
        text_fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(
            [tool_fixture, text_fixture], config
        )

        job = make_job()
        result = gateway.run(job)

        assert result.usage is not None
        # tool: 150 in + 50 out, text: 100 in + 25 out
        assert result.usage.input_tokens == 250
        assert result.usage.output_tokens == 75

    def test_continuation_max_depth(self, config: AppConfig) -> None:
        """Stops after MAX_TOOL_CONTINUATIONS, returns what it has."""
        tool_fixture = load_fixture("fixture_tool_use_response.json")

        # All responses are tool_use — should stop at max depth
        fixtures = [tool_fixture] * (MAX_TOOL_CONTINUATIONS + 2)
        gateway, mock_client = build_gateway_with_mock(fixtures, config)

        job = make_job()
        result = gateway.run(job)

        # 1 initial + MAX_TOOL_CONTINUATIONS continuations
        expected_calls = 1 + MAX_TOOL_CONTINUATIONS
        assert mock_client.messages.stream.call_count == expected_calls

    def test_no_continuation_for_end_turn(self, config: AppConfig) -> None:
        """end_turn stop_reason: no continuation attempted."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job()
        result = gateway.run(job)

        assert mock_client.messages.stream.call_count == 1
        assert result.stop_reason == "end_turn"


# ===========================================================================
# PARALLEL DISPATCH TESTS
# ===========================================================================

class TestParallelDispatch:
    """Test run_parallel() behavior."""

    def test_parallel_returns_in_order(self, config: AppConfig) -> None:
        """Results match input job order."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        # Make the mock return different streams per call
        streams = []
        for i in range(3):
            f = dict(load_fixture("fixture_text_response.json"))
            f["content"] = [{"type": "text", "text": f"Response {i}"}]
            streams.append(_make_mock_stream(f))
        mock_client.messages.stream.side_effect = streams

        jobs = [
            make_job(label=f"job-{i}", role=RoleName.GUIDE)
            for i in range(3)
        ]
        results = gateway.run_parallel(jobs)

        assert len(results) == 3
        for i, r in enumerate(results):
            assert r.label == f"job-{i}"

    def test_parallel_individual_failure(self, config: AppConfig) -> None:
        """One job fails, others succeed."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        ok_stream = _make_mock_stream(fixture)
        error_400 = _make_api_status_error(400)
        ok_stream_2 = _make_mock_stream(fixture)
        mock_client.messages.stream.side_effect = [ok_stream, error_400, ok_stream_2]

        jobs = [make_job(label=f"job-{i}") for i in range(3)]
        results = gateway.run_parallel(jobs)

        assert len(results) == 3
        assert results[0].error is None
        assert results[1].error is not None
        assert results[2].error is None

    def test_parallel_empty_jobs(self, config: AppConfig) -> None:
        """Empty job list returns empty results."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        results = gateway.run_parallel([])
        assert results == []


# ===========================================================================
# INTEGRATION TESTS (full run() path, still mocked)
# ===========================================================================

class TestFullRun:
    """End-to-end through run() with mocked client."""

    def test_text_response(self, config: AppConfig) -> None:
        """MessageJob -> run() -> MessageResult with text, usage, timing."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(fixture, config)

        job = make_job(
            system_prompt="You are a helpful guide.",
            messages=[{"role": "user", "content": "What is PlatformForge?"}],
        )
        result = gateway.run(job)

        assert result.error is None
        assert result.role == RoleName.GUIDE
        assert result.phase == PhaseKey.P1
        assert result.text != ""
        assert result.usage is not None
        assert result.usage.cost_usd > Decimal("0")
        assert result.wall_seconds >= 0
        assert result.retries_attempted == 0

    def test_with_tool_use(self, config: AppConfig) -> None:
        """MessageJob with tools -> tool continuation -> final result."""
        tool_fixture = load_fixture("fixture_tool_use_response.json")
        text_fixture = load_fixture("fixture_text_response.json")
        gateway, _ = build_gateway_with_mock(
            [tool_fixture, text_fixture], config
        )

        job = make_job(
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
        )
        result = gateway.run(job)

        assert result.error is None
        assert len(result.tool_use_blocks) >= 1
        assert result.usage is not None
        # Merged usage from both calls
        assert result.usage.input_tokens > 0

    def test_model_id_correct(self, config: AppConfig) -> None:
        """Gateway uses the correct model_id from active tier."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job()
        gateway.run(job)

        call_kwargs = mock_client.messages.stream.call_args[1]
        assert call_kwargs["model"] == "claude-haiku-4-5-20251001"

    def test_system_prompt_passed(self, config: AppConfig) -> None:
        """System prompt is included in API params."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job(system_prompt="You are the Guide.")
        gateway.run(job)

        call_kwargs = mock_client.messages.stream.call_args[1]
        assert call_kwargs["system"] == "You are the Guide."

    def test_no_system_prompt_omitted(self, config: AppConfig) -> None:
        """Empty system prompt is not sent."""
        fixture = load_fixture("fixture_text_response.json")
        gateway, mock_client = build_gateway_with_mock(fixture, config)

        job = make_job(system_prompt="")
        gateway.run(job)

        call_kwargs = mock_client.messages.stream.call_args[1]
        assert "system" not in call_kwargs


# ===========================================================================
# STUBS EXIST TESTS
# ===========================================================================

class TestStubs:
    """Verify provider stubs exist."""

    def test_perplexity_stub(self) -> None:
        assert PerplexityGateway is not None
        _ = PerplexityGateway()

    def test_grok_stub(self) -> None:
        assert GrokGateway is not None
        _ = GrokGateway()


# ===========================================================================
# GATEWAY INITIALIZATION TESTS
# ===========================================================================

class TestGatewayInit:
    """Test AnthropicGateway initialization."""

    def test_init_with_valid_config(self, config: AppConfig) -> None:
        """Gateway initializes successfully with valid config."""
        with patch("src.llm_gateway.anthropic.Anthropic"):
            gateway = AnthropicGateway(config)
        assert gateway.model_id == "claude-haiku-4-5-20251001"

    def test_init_with_bad_tier_raises(self, config: AppConfig) -> None:
        """Invalid active tier raises KeyError."""
        config.runtime.active_tier = "nonexistent"
        with patch("src.llm_gateway.anthropic.Anthropic"):
            with pytest.raises(KeyError, match="nonexistent"):
                AnthropicGateway(config)


# ===========================================================================
# Helper: build mock API errors
# ===========================================================================

def _make_api_status_error(status_code: int) -> Exception:
    """Create a mock anthropic.APIStatusError with the given status code."""
    import anthropic as anth

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.headers = {}
    mock_response.text = f"Error {status_code}"

    # Build the right error subclass based on status
    if status_code == 429:
        return anth.RateLimitError(
            message=f"Rate limit error {status_code}",
            response=mock_response,
            body=None,
        )
    elif status_code >= 500:
        return anth.InternalServerError(
            message=f"Server error {status_code}",
            response=mock_response,
            body=None,
        )
    else:
        return anth.APIStatusError(
            message=f"API error {status_code}",
            response=mock_response,
            body=None,
        )
