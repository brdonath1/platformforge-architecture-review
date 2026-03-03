"""
PlatformForge Orchestrator — Top-Level Entry Point (orchestrator.py)

CLI entry point and run coordinator. Ties PhaseService and ReviewPipeline
together. Manages the phase loop, cost ceiling checks, cross-phase
consistency, and run lifecycle.

Does NOT own:
- Phase execution internals (PhaseService)
- Review pipeline internals (ReviewPipeline)
- LLM API calls (AnthropicGateway)
- File persistence (RunStore)

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.6 Step 7
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .contracts import (
    MessageJob,
    PhaseKey,
    RoleName,
    RunSummary,
    phase_key,
)
from .llm_gateway import AnthropicGateway
from .phase_service import PHASE_ORDER, PhaseService
from .review_pipeline import ReviewPipeline, load_review_personas
from .run_store import CostCeilingExceeded, CostLedger, RunStore, StateRegistry
from .settings import AppConfig, load_app_config

logger = logging.getLogger("platformforge.orchestrator")

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

GITHUB_REPO: str = "brdonath1/platformforge"
TEMPLATES_PATH: str = "artifacts/current"
MASTER_PROMPT_FILENAME: str = "master-system-prompt.md"
DEFAULT_MAX_EXCHANGES: int = 75


# ---------------------------------------------------------------------------
# Template and file fetching — module-level functions
# ---------------------------------------------------------------------------

def fetch_github_file(repo: str, path: str) -> str:
    """Fetch raw file content from GitHub.

    Uses GITHUB_PAT from environment if available for private repos.
    Falls back to unauthenticated for public repos.
    """
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github.v3.raw"}
    pat = os.environ.get("GITHUB_PAT", "")
    if pat:
        headers["Authorization"] = f"token {pat}"
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as resp:
        raw: bytes = resp.read()
        return raw.decode("utf-8")


def load_template_cached(store: RunStore, filename: str) -> str:
    """Load a template from cache, fetching from GitHub if needed."""
    cached = store.load_cached_template(filename)
    if cached is not None:
        return cached
    logger.info("Fetching template from GitHub: %s", filename)
    content = fetch_github_file(GITHUB_REPO, f"{TEMPLATES_PATH}/{filename}")
    store.cache_template(filename, content)
    return content


def load_all_phase_templates(store: RunStore) -> None:
    """Pre-fetch all phase templates so PhaseService can find them."""
    from .template_parser import TEMPLATE_FILE_MAP

    for _phase_val, filenames in TEMPLATE_FILE_MAP.items():
        for filename in filenames:
            load_template_cached(store, filename)
    logger.info("All phase templates cached")


def load_persona(root: Path) -> str:
    """Load the founder persona from persona.md."""
    path = root / "persona.md"
    if not path.exists():
        raise FileNotFoundError(
            f"persona.md not found at {path}. "
            "Place it in the dry-run root directory."
        )
    return path.read_text(encoding="utf-8")


def check_research_capabilities() -> dict[str, bool]:
    """Check available research engines from environment variables."""
    return {
        "web_search": True,  # Always available via Anthropic API
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "grok": bool(os.environ.get("GROK_API_KEY")),
    }


def _load_dotenv(root: Path) -> None:
    """Load .env file if present. Minimal parser — no third-party deps."""
    env_path = root / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


# ---------------------------------------------------------------------------
# Orchestrator class
# ---------------------------------------------------------------------------

class Orchestrator:
    """Top-level run coordinator.

    Ties PhaseService and ReviewPipeline together. Manages the phase loop,
    cost ceiling checks, cross-phase consistency, and run lifecycle.

    Does NOT own:
    - Phase execution internals (PhaseService)
    - Review pipeline internals (ReviewPipeline)
    - LLM API calls (AnthropicGateway)
    - File persistence (RunStore)
    """

    def __init__(
        self,
        config: AppConfig,
        store: RunStore,
        gateway: AnthropicGateway,
        state: StateRegistry,
        ledger: CostLedger,
        master_prompt: str,
        persona: str,
        review_personas: dict[str, object],
    ) -> None:
        self._config = config
        self._store = store
        self._gateway = gateway
        self._state = state
        self._ledger = ledger
        self._master_prompt = master_prompt
        self._persona = persona
        self._review_personas = review_personas

        self._phase_service = PhaseService(
            gateway=gateway,
            store=store,
            state=state,
            ledger=ledger,
            config=config,
            master_prompt=master_prompt,
            persona=persona,
        )
        self._review_pipeline = ReviewPipeline(
            gateway=gateway,
            store=store,
            ledger=ledger,
            config=config,
            persona=persona,
            review_personas=review_personas,
        )

    # -------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------

    def run(
        self, phases: list[PhaseKey], max_exchanges: int = DEFAULT_MAX_EXCHANGES
    ) -> RunSummary:
        """Main run loop — execute phases sequentially.

        For each phase: check budget, run phase, run review, save artifacts.
        After all phases: cross-phase consistency, timing waterfall, cost report.
        """
        run_start = time.monotonic()
        run_start_iso = datetime.now(tz=timezone.utc).isoformat()
        timing_entries: list[dict[str, object]] = []
        summary = RunSummary(
            phases_requested=[p.value for p in phases],
        )

        for phase in phases:
            # Cost ceiling pre-check
            if self._ledger.remaining_budget_usd <= Decimal("0"):
                summary.halted_at_phase = phase.value
                summary.halt_reason = "Cost ceiling reached before phase start"
                logger.warning(
                    "Cost ceiling reached — halting before phase %s",
                    phase.value,
                )
                break

            phase_start = time.monotonic()

            try:
                # Run phase conversation + synthesis
                phase_result = self._phase_service.run_phase(
                    phase, max_exchanges
                )
                conversation_elapsed = time.monotonic() - phase_start

                # Save phase artifacts
                self._store.save_deliverable(
                    phase, phase_result.deliverable_text
                )
                self._store.save_conversation(phase, phase_result.transcript)
                self._store.save_phase_metrics(
                    phase, phase_result.outcome.model_dump(mode="json")
                )

                # Run review pipeline
                review_start = time.monotonic()
                template_text = ""
                if phase_result.template_spec is not None:
                    template_text = (
                        phase_result.template_spec.synthesis_instructions
                    )

                prior_deliverables = self._phase_service.load_prior_deliverables(
                    phase
                )

                review_result = self._review_pipeline.run(
                    phase,
                    phase_result.deliverable_text,
                    template_text,
                    prior_deliverables,
                )
                review_elapsed = time.monotonic() - review_start

                # Overwrite deliverable with reviewed version if corrections applied
                if review_result.deliverable_text != phase_result.deliverable_text:
                    self._store.save_deliverable(
                        phase, review_result.deliverable_text
                    )

                # Save review notes if present
                if review_result.review_notes:
                    self._store.save_deliverable(
                        phase,
                        review_result.deliverable_text,
                    )

                # Publish if configured
                if self._config.runtime.publish_after_each_phase:
                    pat = os.environ.get("GITHUB_PAT", "")
                    if pat:
                        self._store.publish_to_github(
                            phase, GITHUB_REPO, pat, label=f"phase-{phase.value}"
                        )

                # Record timing
                phase_elapsed = time.monotonic() - phase_start
                timing_entries.append(
                    self._build_timing_entry(
                        phase,
                        phase_elapsed,
                        conversation_elapsed,
                        review_elapsed,
                    )
                )

                summary.phases_completed.append(phase.value)
                logger.info(
                    "Phase %s completed in %.1f seconds",
                    phase.value,
                    phase_elapsed,
                )

            except CostCeilingExceeded as exc:
                summary.halted_at_phase = phase.value
                summary.halt_reason = f"Cost ceiling exceeded: {exc}"
                logger.warning("Cost ceiling exceeded during phase %s", phase.value)
                break

            except KeyboardInterrupt:
                summary.halted_at_phase = phase.value
                summary.halt_reason = "User interrupted (KeyboardInterrupt)"
                logger.warning("User interrupted during phase %s", phase.value)
                break

            except Exception as exc:
                summary.halted_at_phase = phase.value
                summary.halt_reason = (
                    f"Phase {phase.value} failed: {type(exc).__name__}: "
                    f"{str(exc)[:200]}. Resume from phase {phase.value}."
                )
                logger.exception("Phase %s failed", phase.value)
                break

        # Post-loop: cross-phase consistency
        completed_keys = [
            phase_key(v) for v in summary.phases_completed
        ]
        if len(completed_keys) >= 2:
            try:
                self.run_cross_phase_consistency(completed_keys)
                summary.consistency_check_run = True
            except Exception:
                logger.exception("Cross-phase consistency check failed")

        # Save timing waterfall
        run_elapsed = time.monotonic() - run_start
        run_end_iso = datetime.now(tz=timezone.utc).isoformat()
        waterfall: dict[str, object] = {
            "run_start": run_start_iso,
            "run_end": run_end_iso,
            "total_elapsed_seconds": round(run_elapsed, 1),
            "model": self._gateway.model_id,
            "phases": timing_entries,
        }
        self._store.save_timing_waterfall(waterfall)

        # Save cost report
        cost_report = self._ledger.build_report()
        self._store.save_cost_report(cost_report)

        # Final publish
        pat = os.environ.get("GITHUB_PAT", "")
        if pat:
            self._store.publish_to_github(
                completed_keys[-1] if completed_keys else PhaseKey.P1,
                GITHUB_REPO,
                pat,
                label="final",
            )

        summary.total_cost_usd = str(self._ledger.total_cost_usd)
        summary.total_elapsed_seconds = round(run_elapsed, 1)

        return summary

    def run_cross_phase_consistency(
        self, phases_completed: list[PhaseKey]
    ) -> dict[str, object]:
        """Post-run cross-phase consistency check.

        Only runs if 2+ deliverables exist. Loads all completed deliverables,
        builds a combined document, and asks the model to identify conflicts.
        """
        all_deliverables = self._store.load_all_deliverables()

        # Filter to only completed phases
        relevant: dict[PhaseKey, str] = {
            pk: text
            for pk, text in all_deliverables.items()
            if pk in phases_completed
        }

        if len(relevant) < 2:
            logger.info(
                "Skipping consistency check — fewer than 2 deliverables"
            )
            return {"skipped": True, "reason": "fewer than 2 deliverables"}

        # Build combined document
        parts: list[str] = []
        for pk in sorted(relevant.keys(), key=lambda p: p.value):
            parts.append(f"<phase_{pk.value}>\n{relevant[pk]}\n</phase_{pk.value}>")
        combined = "\n\n".join(parts)

        consistency_prompt = (
            "Review the following deliverables from multiple phases for "
            "cross-phase consistency. Identify:\n"
            "- Naming conflicts across phases\n"
            "- Feature ID mismatches\n"
            "- Technology contradictions\n"
            "- User role inconsistencies\n"
            "- Architectural conflicts\n\n"
            "Return your findings as a JSON object with keys: "
            "'issues' (list of issue dicts with 'phases', 'type', 'description'), "
            "'summary' (string).\n\n"
            f"{combined}"
        )

        job = MessageJob(
            role=RoleName.CONSISTENCY,
            phase=phases_completed[-1],
            label="cross-phase consistency",
            system_prompt=(
                "You are a meticulous cross-phase consistency auditor. "
                "You compare deliverables across phases and identify "
                "contradictions, naming conflicts, and architectural "
                "inconsistencies. Return results as valid JSON."
            ),
            messages=[{"role": "user", "content": consistency_prompt}],
            tools=[],
            thinking_budget=0,
        )

        result = self._gateway.run(job)
        if result.error:
            logger.warning("Consistency check LLM error: %s", result.error)
            return {"error": result.error}

        # Record cost
        if result.usage:
            self._ledger.record(phases_completed[-1], result.usage)

        # Parse JSON response
        try:
            report: dict[str, object] = json.loads(result.text)
        except (json.JSONDecodeError, ValueError):
            logger.warning("Consistency check returned unparseable response")
            report = {"error": "unparseable"}

        self._store.save_consistency_report(report)
        return report

    # -------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------

    def _build_timing_entry(
        self,
        phase: PhaseKey,
        total_seconds: float,
        conversation_seconds: float,
        review_seconds: float,
    ) -> dict[str, object]:
        """Build timing waterfall entry for one phase."""
        return {
            "phase": phase.value,
            "total_seconds": round(total_seconds, 1),
            "conversation_seconds": round(conversation_seconds, 1),
            "review_pipeline_seconds": round(review_seconds, 1),
        }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry point for the orchestrator."""
    parser = argparse.ArgumentParser(
        description="PlatformForge Orchestrator — AI-driven phase execution"
    )
    parser.add_argument(
        "--phase",
        type=str,
        default="1",
        help="Starting phase (default: 1)",
    )
    parser.add_argument(
        "--max-exchanges",
        type=int,
        default=DEFAULT_MAX_EXCHANGES,
        help=f"Per-phase exchange limit (default: {DEFAULT_MAX_EXCHANGES})",
    )
    parser.add_argument(
        "--max-phases",
        type=int,
        default=0,
        help="Limit number of phases (0 = all, default: 0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print config and exit without running",
    )
    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Load .env if present
    store = RunStore()
    _load_dotenv(store.root)

    # Validate environment
    if not args.dry_run and not os.environ.get("ANTHROPIC_API_KEY"):
        logger.error("ANTHROPIC_API_KEY not set. Set it or use --dry-run.")
        raise SystemExit(1)

    # Load configuration
    config = load_app_config()
    gateway = AnthropicGateway(config)
    state = StateRegistry()
    ledger = CostLedger(config.runtime.hard_cost_ceiling_usd)

    # Load resources
    master_prompt = load_template_cached(store, MASTER_PROMPT_FILENAME)
    persona = load_persona(store.root)
    review_personas = load_review_personas(store.root / "personas")
    load_all_phase_templates(store)
    research_caps = check_research_capabilities()

    # Resolve phase list
    start_phase = phase_key(args.phase)
    start_idx = PHASE_ORDER.index(start_phase)
    phases_to_run = PHASE_ORDER[start_idx:]
    if args.max_phases > 0:
        phases_to_run = phases_to_run[: args.max_phases]

    # Startup banner
    logger.info("PlatformForge Orchestrator")
    logger.info("  Model: %s", gateway.model_id)
    logger.info("  Phases: %s", [p.value for p in phases_to_run])
    logger.info("  Max exchanges: %d", args.max_exchanges)
    logger.info("  Cost ceiling: $%s", config.runtime.hard_cost_ceiling_usd)
    logger.info("  Research: %s", research_caps)

    if args.dry_run:
        logger.info("Dry run — exiting without execution")
        return

    # Create orchestrator and run
    orchestrator = Orchestrator(
        config=config,
        store=store,
        gateway=gateway,
        state=state,
        ledger=ledger,
        master_prompt=master_prompt,
        persona=persona,
        review_personas=review_personas,
    )
    run_summary = orchestrator.run(phases_to_run, args.max_exchanges)

    # Final summary
    logger.info("Run complete")
    logger.info("  Phases completed: %s", run_summary.phases_completed)
    logger.info("  Total cost: $%s", run_summary.total_cost_usd)
    logger.info("  Total time: %.1f seconds", run_summary.total_elapsed_seconds)
    if run_summary.halted_at_phase:
        logger.warning(
            "  Halted at phase %s: %s",
            run_summary.halted_at_phase,
            run_summary.halt_reason,
        )
    if run_summary.consistency_check_run:
        logger.info("  Cross-phase consistency check: completed")


if __name__ == "__main__":
    main()
