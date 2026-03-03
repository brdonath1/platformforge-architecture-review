"""
PlatformForge Orchestrator — LLM Gateway (llm_gateway.py)

Single interface to the Anthropic Messages API. All LLM calls in the
orchestrator go through AnthropicGateway.run() or .run_parallel().

Handles: streaming parse, retry, thinking normalization, parallel
dispatch, cost calculation, and tool continuations.

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.1 (Module Map), 2.5 (Thinking toggle),
    2.6 Step 2
Fragility Fixes: Rank 7 (_execute_stream), Rank 8 (tool continuations)
"""

from __future__ import annotations

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any, Sequence

import anthropic

from .contracts import (
    CallUsage,
    MessageJob,
    MessageResult,
    PhaseKey,
    RoleName,
)
from .settings import AppConfig, RoleExecutionPolicy, resolve_role_policy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 3
RETRY_BACKOFF_BASE: float = 2.0
MAX_TOOL_CONTINUATIONS: int = 5
DEFAULT_PARALLEL_WORKERS: int = 4
JOB_TIMEOUT_SECONDS: float = 300.0

RETRYABLE_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 529})

# Cache pricing multipliers (Anthropic standard)
CACHE_WRITE_MULTIPLIER: Decimal = Decimal("1.25")
CACHE_READ_MULTIPLIER: Decimal = Decimal("0.10")


# ---------------------------------------------------------------------------
# Stubs for future providers (Step 2 scope: designed in, not implemented)
# ---------------------------------------------------------------------------

class PerplexityGateway:
    """Placeholder for Perplexity Sonar integration. Not implemented in Step 2."""


class GrokGateway:
    """Placeholder for Grok/X integration. Not implemented in Step 2."""


# ---------------------------------------------------------------------------
# AnthropicGateway
# ---------------------------------------------------------------------------

class AnthropicGateway:
    """Single interface to the Anthropic Messages API.

    All LLM calls in the orchestrator go through this class.
    Handles: streaming parse, retry, thinking normalization,
    parallel dispatch, cost calculation, and tool continuations.
    """

    def __init__(self, config: AppConfig) -> None:
        """Initialize with app config.

        Resolves the active tier's ModelProfile and instantiates
        the Anthropic client.
        """
        self._config = config
        tier_name = config.runtime.active_tier
        if tier_name not in config.tiers:
            available = list(config.tiers.keys())
            raise KeyError(
                f"Active tier '{tier_name}' not found. Available: {available}"
            )
        self._tier = config.tiers[tier_name]
        self._model = self._tier.model
        self._client = anthropic.Anthropic()

    @property
    def model_id(self) -> str:
        """The model ID for the active tier."""
        return self._model.model_id

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def run(self, job: MessageJob) -> MessageResult:
        """Execute a single LLM call with retry and streaming.

        Returns a MessageResult. On failure after all retries,
        MessageResult.error is set rather than raising an exception.
        """
        policy = resolve_role_policy(self._config, job.role)
        params = self._build_params(job, policy)

        result = self._run_with_retry(job, params)

        # Handle tool continuations if needed
        if result.error is None and result.stop_reason == "tool_use":
            result = self._handle_tool_continuation(job, result, params)

        return result

    def run_parallel(
        self, jobs: Sequence[MessageJob]
    ) -> list[MessageResult]:
        """Execute multiple jobs concurrently.

        Uses ThreadPoolExecutor. Results are returned in the same
        order as input jobs. Individual failures do not cancel
        other jobs — the failed job's MessageResult.error is set.
        """
        if not jobs:
            return []

        max_parallel = max(
            (resolve_role_policy(self._config, j.role).max_parallel
             for j in jobs),
            default=1,
        )
        max_workers = min(len(jobs), max_parallel, DEFAULT_PARALLEL_WORKERS)

        results: list[MessageResult | None] = [None] * len(jobs)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {
                executor.submit(self.run, job): idx
                for idx, job in enumerate(jobs)
            }
            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results[idx] = future.result(timeout=JOB_TIMEOUT_SECONDS)
                except Exception as exc:
                    job = jobs[idx]
                    results[idx] = MessageResult(
                        role=job.role,
                        phase=job.phase,
                        label=job.label,
                        error=f"Parallel execution error: {exc}",
                    )

        # Type narrowing: all slots should be filled
        return [r for r in results if r is not None]

    def estimate_cost(self, job: MessageJob) -> Decimal:
        """Estimate worst-case cost for a single job.

        Uses the role's policy budgets against the active tier's pricing.
        """
        policy = resolve_role_policy(self._config, job.role)
        input_cost = (
            Decimal(str(policy.input_budget))
            / Decimal("1000000")
            * self._model.input_price_per_mtok
        )
        output_cost = (
            Decimal(str(policy.output_budget))
            / Decimal("1000000")
            * self._model.output_price_per_mtok
        )
        return input_cost + output_cost

    # -------------------------------------------------------------------
    # Thinking normalization
    # -------------------------------------------------------------------

    def _resolve_thinking(
        self, job: MessageJob, policy: RoleExecutionPolicy
    ) -> dict[str, Any] | None:
        """Determine thinking configuration for an API call.

        Returns a thinking dict for the API, or None if thinking
        should be omitted entirely.

        Priority order:
        1. Model does NOT support thinking -> None
        2. job.thinking_budget == 0 -> None
        3. job.thinking_budget > 0 -> enabled with that budget
        4. Policy thinking field: "disabled" -> None,
           "enabled" -> enabled with output_budget,
           numeric string -> enabled with that int
        """
        if not self._model.supports_thinking:
            return None

        # Explicit override on the job
        if job.thinking_budget is not None:
            if job.thinking_budget <= 0:
                return None
            return {
                "type": "enabled",
                "budget_tokens": job.thinking_budget,
            }

        # Fall back to role policy
        thinking_str = policy.thinking
        if thinking_str == "disabled":
            return None
        if thinking_str == "enabled":
            return {
                "type": "enabled",
                "budget_tokens": policy.output_budget,
            }
        # Try numeric string
        try:
            budget = int(thinking_str)
            if budget <= 0:
                return None
            return {"type": "enabled", "budget_tokens": budget}
        except (ValueError, TypeError):
            return None

    # -------------------------------------------------------------------
    # Parameter building
    # -------------------------------------------------------------------

    def _build_params(
        self, job: MessageJob, policy: RoleExecutionPolicy
    ) -> dict[str, Any]:
        """Build the parameters dict for the Anthropic API call."""
        max_tokens = job.max_output_tokens or policy.output_budget

        params: dict[str, Any] = {
            "model": self._model.model_id,
            "max_tokens": max_tokens,
            "messages": job.messages or [
                {"role": "user", "content": "Hello"}
            ],
        }

        if job.system_prompt:
            params["system"] = job.system_prompt

        if job.tools:
            params["tools"] = job.tools

        thinking = self._resolve_thinking(job, policy)
        if thinking is not None:
            params["thinking"] = thinking

        return params

    # -------------------------------------------------------------------
    # Retry logic
    # -------------------------------------------------------------------

    def _run_with_retry(
        self, job: MessageJob, params: dict[str, Any]
    ) -> MessageResult:
        """Execute an API call with exponential backoff retry."""
        last_error: str | None = None

        for attempt in range(MAX_RETRIES + 1):
            try:
                start = time.monotonic()
                result = self._stream_call(job, params)
                elapsed = time.monotonic() - start
                result.wall_seconds = elapsed
                result.retries_attempted = attempt

                # Attach cost
                if result.usage is None:
                    result.usage = self._calculate_cost(
                        job.role, {"input_tokens": 0, "output_tokens": 0}
                    )

                return result

            except anthropic.APIStatusError as exc:
                status = exc.status_code
                if status not in RETRYABLE_STATUS_CODES:
                    logger.warning(
                        "Non-retryable API error %d for %s/%s: %s",
                        status, job.role.value, job.label, exc,
                    )
                    return MessageResult(
                        role=job.role,
                        phase=job.phase,
                        label=job.label,
                        error=f"API error {status}: {exc}",
                        retries_attempted=0,
                    )

                last_error = f"API error {status}: {exc}"
                if attempt < MAX_RETRIES:
                    backoff = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.info(
                        "Retryable error %d for %s/%s (attempt %d/%d), "
                        "backing off %.1fs",
                        status, job.role.value, job.label,
                        attempt + 1, MAX_RETRIES, backoff,
                    )
                    time.sleep(backoff)

            except anthropic.APIConnectionError as exc:
                last_error = f"Connection error: {exc}"
                if attempt < MAX_RETRIES:
                    backoff = RETRY_BACKOFF_BASE ** (attempt + 1)
                    logger.info(
                        "Connection error for %s/%s (attempt %d/%d), "
                        "backing off %.1fs",
                        job.role.value, job.label,
                        attempt + 1, MAX_RETRIES, backoff,
                    )
                    time.sleep(backoff)

        # All retries exhausted
        return MessageResult(
            role=job.role,
            phase=job.phase,
            label=job.label,
            error=last_error or "Unknown error after retries",
            retries_attempted=MAX_RETRIES,
        )

    # -------------------------------------------------------------------
    # Streaming call
    # -------------------------------------------------------------------

    def _stream_call(
        self, job: MessageJob, params: dict[str, Any]
    ) -> MessageResult:
        """Execute a streaming API call and parse the response.

        Pure parsing — no progress UI, no print statements.
        """
        from anthropic.types import (
            TextBlock,
            ThinkingBlock,
            ToolUseBlock,
            ServerToolUseBlock,
        )

        text_parts: list[str] = []
        thinking_parts: list[str] = []
        tool_use_blocks: list[dict[str, object]] = []
        stop_reason = "end_turn"
        usage_data: dict[str, int] = {}

        with self._client.messages.stream(**params) as stream:
            response = stream.get_final_message()

        # Parse content blocks from the final message
        for block in response.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
            elif isinstance(block, ThinkingBlock):
                thinking_parts.append(block.thinking)
            elif isinstance(block, (ToolUseBlock, ServerToolUseBlock)):
                tool_use_blocks.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                    "type": "tool_use",
                })

        stop_reason = response.stop_reason or "end_turn"

        # Extract usage
        if response.usage:
            usage_data = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "cache_creation_input_tokens": getattr(
                    response.usage, "cache_creation_input_tokens", 0
                ) or 0,
                "cache_read_input_tokens": getattr(
                    response.usage, "cache_read_input_tokens", 0
                ) or 0,
            }

        cost = self._calculate_cost(job.role, usage_data)

        return MessageResult(
            role=job.role,
            phase=job.phase,
            label=job.label,
            text="".join(text_parts),
            thinking_text="".join(thinking_parts),
            tool_use_blocks=tool_use_blocks,
            stop_reason=stop_reason,
            usage=cost,
        )

    # -------------------------------------------------------------------
    # Tool continuations
    # -------------------------------------------------------------------

    def _handle_tool_continuation(
        self,
        job: MessageJob,
        prior_result: MessageResult,
        base_params: dict[str, Any],
    ) -> MessageResult:
        """Continue conversation after tool_use stop_reason.

        For server-managed tools (web_search), the SDK handles execution.
        We rebuild the message chain and call again.
        Max MAX_TOOL_CONTINUATIONS depth to prevent infinite loops.
        """
        current_result = prior_result
        all_text_parts: list[str] = [prior_result.text]
        all_thinking_parts: list[str] = [prior_result.thinking_text]
        all_tool_use: list[dict[str, object]] = list(prior_result.tool_use_blocks)
        all_tool_results: list[dict[str, object]] = []
        total_usage = prior_result.usage

        messages = list(base_params.get("messages", []))

        for depth in range(MAX_TOOL_CONTINUATIONS):
            if current_result.stop_reason != "tool_use":
                break

            # Build assistant message with tool_use blocks
            assistant_content: list[dict[str, object]] = []
            if current_result.text:
                assistant_content.append({
                    "type": "text",
                    "text": current_result.text,
                })
            for tub in current_result.tool_use_blocks:
                assistant_content.append(tub)

            messages.append({
                "role": "assistant",
                "content": assistant_content,
            })

            # Build tool_result blocks
            # For server-side tools, we pass back empty results
            # as the SDK handles them during streaming
            user_content: list[dict[str, object]] = []
            for tub in current_result.tool_use_blocks:
                tool_result: dict[str, object] = {
                    "type": "tool_result",
                    "tool_use_id": tub.get("id", ""),
                    "content": "",
                }
                user_content.append(tool_result)
                all_tool_results.append(tool_result)

            messages.append({
                "role": "user",
                "content": user_content,
            })

            # Make the continuation call
            cont_params = dict(base_params)
            cont_params["messages"] = messages

            start = time.monotonic()
            current_result = self._stream_call(job, cont_params)
            elapsed = time.monotonic() - start

            # Accumulate
            if current_result.text:
                all_text_parts.append(current_result.text)
            if current_result.thinking_text:
                all_thinking_parts.append(current_result.thinking_text)
            all_tool_use.extend(current_result.tool_use_blocks)

            # Merge usage
            if total_usage and current_result.usage:
                total_usage = CallUsage(
                    role=total_usage.role,
                    model_id=total_usage.model_id,
                    input_tokens=total_usage.input_tokens + current_result.usage.input_tokens,
                    output_tokens=total_usage.output_tokens + current_result.usage.output_tokens,
                    cache_read_tokens=total_usage.cache_read_tokens + current_result.usage.cache_read_tokens,
                    cache_write_tokens=total_usage.cache_write_tokens + current_result.usage.cache_write_tokens,
                    cost_usd=total_usage.cost_usd + current_result.usage.cost_usd,
                )
            elif current_result.usage:
                total_usage = current_result.usage

        return MessageResult(
            role=job.role,
            phase=job.phase,
            label=job.label,
            text="".join(all_text_parts),
            thinking_text="".join(all_thinking_parts),
            tool_use_blocks=all_tool_use,
            tool_result_blocks=all_tool_results,
            stop_reason=current_result.stop_reason,
            usage=total_usage,
            wall_seconds=prior_result.wall_seconds + current_result.wall_seconds,
            retries_attempted=prior_result.retries_attempted,
        )

    # -------------------------------------------------------------------
    # Cost calculation
    # -------------------------------------------------------------------

    def _calculate_cost(
        self, role: RoleName, usage_data: dict[str, int]
    ) -> CallUsage:
        """Build a CallUsage from raw API usage data.

        Cache pricing: write at 1.25x input price, read at 0.1x input price.
        """
        input_tokens = usage_data.get("input_tokens", 0)
        output_tokens = usage_data.get("output_tokens", 0)
        cache_write = usage_data.get("cache_creation_input_tokens", 0)
        cache_read = usage_data.get("cache_read_input_tokens", 0)

        input_price = self._model.input_price_per_mtok
        output_price = self._model.output_price_per_mtok
        million = Decimal("1000000")

        cost = (
            Decimal(str(input_tokens)) / million * input_price
            + Decimal(str(output_tokens)) / million * output_price
            + Decimal(str(cache_write)) / million * input_price * CACHE_WRITE_MULTIPLIER
            + Decimal(str(cache_read)) / million * input_price * CACHE_READ_MULTIPLIER
        )

        return CallUsage(
            role=role,
            model_id=self._model.model_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read,
            cache_write_tokens=cache_write,
            cost_usd=cost,
        )
