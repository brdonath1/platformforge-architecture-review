"""Tests for settings.py -- config loading and policy resolution."""

from decimal import Decimal
from pathlib import Path

import pytest
from src.contracts import MessageJob, PhaseKey, RoleName
from src.settings import (
    AppConfig,
    load_app_config,
    resolve_role_policy,
    estimate_reserved_cost,
)


CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.json"

ALL_ROLES = list(RoleName)
ALL_TIERS = ["haiku_4_5", "sonnet_4_5", "sonnet_4_6_std", "sonnet_4_6_high"]


@pytest.fixture
def config() -> AppConfig:
    return load_app_config(CONFIG_PATH)


class TestLoadConfig:
    def test_loads_successfully(self, config):
        assert isinstance(config, AppConfig)

    def test_active_tier_is_haiku(self, config):
        assert config.runtime.active_tier == "haiku_4_5"

    def test_cost_ceiling(self, config):
        assert config.runtime.hard_cost_ceiling_usd == Decimal("200.00")

    def test_research_flags(self, config):
        assert config.research.anthropic_web_search is True
        assert config.research.perplexity_enabled is True
        assert config.research.grok_enabled is True

    @pytest.mark.parametrize("tier", ALL_TIERS)
    def test_all_four_tiers_present(self, config, tier):
        assert tier in config.tiers

    def test_missing_file_raises(self):
        with pytest.raises(FileNotFoundError):
            load_app_config(Path("/nonexistent/config.json"))


class TestResolveRolePolicy:
    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_all_roles_resolve_under_haiku(self, config, role):
        policy = resolve_role_policy(config, role)
        assert policy.input_budget > 0
        assert policy.output_budget > 0

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_haiku_thinking_disabled_all_roles(self, config, role):
        policy = resolve_role_policy(config, role)
        assert policy.thinking == "disabled"

    def test_guide_budgets(self, config):
        policy = resolve_role_policy(config, RoleName.GUIDE)
        assert policy.input_budget == 110000
        assert policy.output_budget == 12000

    def test_synthesis_budgets(self, config):
        policy = resolve_role_policy(config, RoleName.SYNTHESIS)
        assert policy.input_budget == 120000
        assert policy.output_budget == 16000

    def test_unknown_tier_raises(self, config):
        config.runtime.active_tier = "nonexistent_tier"
        with pytest.raises(KeyError, match="not found in config"):
            resolve_role_policy(config, RoleName.GUIDE)


class TestEstimateReservedCost:
    def test_positive_cost(self, config):
        jobs = [
            MessageJob(role=RoleName.GUIDE, phase=PhaseKey.P1, label="guide p1"),
            MessageJob(role=RoleName.SYNTHESIS, phase=PhaseKey.P1, label="synth p1"),
        ]
        cost = estimate_reserved_cost(config, jobs)
        assert isinstance(cost, Decimal)
        assert cost > Decimal("0")

    def test_empty_jobs_zero_cost(self, config):
        cost = estimate_reserved_cost(config, [])
        assert cost == Decimal("0")

    def test_single_job_math(self, config):
        jobs = [MessageJob(role=RoleName.GUIDE, phase=PhaseKey.P1, label="test")]
        cost = estimate_reserved_cost(config, jobs)
        expected = (
            Decimal("110000") / Decimal("1000000") * Decimal("1.00")
        ) + (
            Decimal("12000") / Decimal("1000000") * Decimal("5.00")
        )
        assert cost == expected

    def test_bad_tier_raises(self, config):
        config.runtime.active_tier = "bad"
        with pytest.raises(KeyError):
            estimate_reserved_cost(
                config,
                [MessageJob(role=RoleName.GUIDE, phase=PhaseKey.P1, label="x")]
            )


class TestHaikuModel:
    def test_model_id(self, config):
        m = config.tiers["haiku_4_5"].model
        assert m.model_id == "claude-haiku-4-5-20251001"

    def test_context_window(self, config):
        m = config.tiers["haiku_4_5"].model
        assert m.context_window_tokens == 200000

    def test_output_ceiling(self, config):
        m = config.tiers["haiku_4_5"].model
        assert m.output_ceiling_tokens == 8192

    def test_thinking_disabled(self, config):
        m = config.tiers["haiku_4_5"].model
        assert m.supports_thinking is False
        assert m.default_thinking == "disabled"
