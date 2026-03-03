"""
PlatformForge Orchestrator -- Settings (settings.py)

Configuration loading and policy resolution. Loads config.json and
resolves runtime policies per role.

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.5 (Configuration)
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from .contracts import MessageJob, RoleName


# ---------------------------------------------------------------------------
# Configuration models
# ---------------------------------------------------------------------------

class ModelProfile(BaseModel):
    """Hardware/capability profile for a specific Claude model."""

    model_id: str
    context_window_tokens: int
    output_ceiling_tokens: int
    supports_thinking: bool
    default_thinking: str = Field(
        description="disabled, enabled, or budget string like 10000"
    )
    input_price_per_mtok: Decimal = Field(
        description="USD per 1M input tokens."
    )
    output_price_per_mtok: Decimal = Field(
        description="USD per 1M output tokens."
    )


class RoleExecutionPolicy(BaseModel):
    """Execution constraints for a single role under a specific tier."""

    input_budget: int
    output_budget: int
    thinking: str = Field(
        default="disabled",
        description="disabled, enabled, or token budget string."
    )
    max_parallel: int = Field(default=1)


class TierBundle(BaseModel):
    """Complete configuration for one model tier."""

    tier_name: str
    model: ModelProfile
    role_policies: dict[str, RoleExecutionPolicy]


class ResearchConfig(BaseModel):
    """Research engine toggles."""

    anthropic_web_search: bool = True
    perplexity_enabled: bool = True
    grok_enabled: bool = True


class RuntimeConfig(BaseModel):
    """Top-level runtime settings."""

    active_tier: str
    hard_cost_ceiling_usd: Decimal
    publish_after_each_phase: bool = True


class AppConfig(BaseModel):
    """Root configuration model loaded from config.json."""

    runtime: RuntimeConfig
    research: ResearchConfig
    tiers: dict[str, TierBundle]


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

def load_app_config(path: Path | None = None) -> AppConfig:
    """Load configuration from a JSON file.

    Default path: ../config.json relative to the src/ directory.
    Validates all required fields via Pydantic.
    """
    if path is None:
        path = Path(__file__).resolve().parent.parent / "config.json"

    if not path.exists():
        raise FileNotFoundError(
            f"Config file not found: {path}. "
            f"Expected config.json in the dry-run/ directory."
        )

    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    return AppConfig.model_validate(raw)


def resolve_role_policy(
    config: AppConfig, role: RoleName
) -> RoleExecutionPolicy:
    """Look up the execution policy for a role under the active tier.

    Raises KeyError if the role is not found in the active tier.
    """
    tier_name = config.runtime.active_tier

    if tier_name not in config.tiers:
        available = list(config.tiers.keys())
        raise KeyError(
            f"Active tier '{tier_name}' not found in config. "
            f"Available tiers: {available}"
        )

    tier = config.tiers[tier_name]
    role_key = role.value

    if role_key not in tier.role_policies:
        available = list(tier.role_policies.keys())
        raise KeyError(
            f"Role '{role_key}' not found in tier '{tier_name}'. "
            f"Available roles: {available}"
        )

    return tier.role_policies[role_key]


def estimate_reserved_cost(
    config: AppConfig, jobs: Sequence[MessageJob]
) -> Decimal:
    """Estimate worst-case cost for a set of jobs based on the active tier.

    Uses input_budget * input_price + output_budget * output_price per job.
    This is a RESERVATION, not actual cost -- always overestimates.
    """
    tier_name = config.runtime.active_tier

    if tier_name not in config.tiers:
        raise KeyError(f"Active tier '{tier_name}' not found in config.")

    tier = config.tiers[tier_name]
    model = tier.model
    total = Decimal("0")

    for job in jobs:
        policy = resolve_role_policy(config, job.role)
        input_cost = (
            Decimal(str(policy.input_budget))
            / Decimal("1000000")
            * model.input_price_per_mtok
        )
        output_cost = (
            Decimal(str(policy.output_budget))
            / Decimal("1000000")
            * model.output_price_per_mtok
        )
        total += input_cost + output_cost

    return total
