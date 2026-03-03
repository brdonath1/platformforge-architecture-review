"""
PlatformForge Orchestrator — Durable Run Store (run_store.py)

Filesystem persistence, canonical state registry, and cost tracking.

Three classes:
1. RunStore — filesystem persistence layer
2. StateRegistry — cross-phase canonical fact registry with supersession
3. CostLedger — thread-safe cost tracking with budget enforcement

Decision Authority: D-196 (re-architecture), D-194 (parallel review)
Codex Spec Reference: Section 2.6 Step 4
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from .contracts import (
    CallUsage,
    CanonicalFact,
    PhaseKey,
    PhaseOutcome,
    fact_key,
)

logger_store = logging.getLogger("platformforge.run_store")
logger_cost = logging.getLogger("platformforge.cost_ledger")


# ---------------------------------------------------------------------------
# Phase ordering for supersession
# ---------------------------------------------------------------------------

_PHASE_ORDER: dict[PhaseKey, int] = {
    PhaseKey.P1: 1,
    PhaseKey.P2: 2,
    PhaseKey.P3: 3,
    PhaseKey.P4: 4,
    PhaseKey.P5: 5,
    PhaseKey.P6A: 6,
    PhaseKey.P6B: 7,
    PhaseKey.P6C: 8,
    PhaseKey.P7: 9,
    PhaseKey.P8: 10,
    PhaseKey.P9: 11,
    PhaseKey.P10: 12,
}


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CostCeilingExceeded(RuntimeError):
    """Raised when a call would exceed the hard cost ceiling."""

    def __init__(
        self, current: Decimal, attempted: Decimal, ceiling: Decimal
    ) -> None:
        self.current = current
        self.attempted = attempted
        self.ceiling = ceiling
        super().__init__(
            f"Cost ceiling exceeded: current ${current}, "
            f"attempted +${attempted}, ceiling ${ceiling}"
        )


# ---------------------------------------------------------------------------
# RunStore
# ---------------------------------------------------------------------------

class RunStore:
    """Filesystem persistence layer for orchestrator runs.

    Manages: directory layout, deliverable save/load, conversation
    transcript save/load, phase metrics, GitHub publishing, template
    caching, and run resume detection.

    All paths are relative to a configurable root directory.
    Default root: the dry-run/ directory (parent of src/).
    """

    def __init__(self, root: Path | None = None) -> None:
        """Initialize with root directory.

        If root is None, defaults to Path(__file__).resolve().parent.parent
        (i.e., dry-run/).

        Creates the output directory structure on init:
          {root}/output/
          {root}/output/deliverables/
          {root}/output/conversations/
          {root}/output/metrics/
          {root}/output/templates_cache/
        """
        if root is None:
            self.root = Path(__file__).resolve().parent.parent
        else:
            self.root = Path(root)

        output = self.root / "output"
        self.deliverables_dir = output / "deliverables"
        self.conversations_dir = output / "conversations"
        self.metrics_dir = output / "metrics"
        self.templates_dir = output / "templates_cache"

        for d in (
            self.deliverables_dir,
            self.conversations_dir,
            self.metrics_dir,
            self.templates_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

        logger_store.debug("RunStore initialised at %s", self.root)

    # -- Deliverables ------------------------------------------------------

    def save_deliverable(self, phase: PhaseKey, content: str) -> Path:
        """Save a phase deliverable as markdown.

        Filename: deliverable-{phase.value}.md (e.g., deliverable-6a.md)
        Returns the path to the saved file.
        """
        path = self.deliverables_dir / f"deliverable-{phase.value}.md"
        path.write_text(content, encoding="utf-8")
        logger_store.info("Saved deliverable %s (%d chars)", path.name, len(content))
        return path

    def load_deliverable(self, phase: PhaseKey) -> str | None:
        """Load a saved deliverable. Returns None if not found."""
        path = self.deliverables_dir / f"deliverable-{phase.value}.md"
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    def load_all_deliverables(self) -> dict[PhaseKey, str]:
        """Load all saved deliverables. Returns {PhaseKey: content}."""
        result: dict[PhaseKey, str] = {}
        for pk in PhaseKey:
            content = self.load_deliverable(pk)
            if content is not None:
                result[pk] = content
        return result

    # -- Conversations -----------------------------------------------------

    def save_conversation(
        self, phase: PhaseKey, transcript: list[dict[str, object]]
    ) -> Path:
        """Save conversation transcript as JSON.

        Filename: conversation-{phase.value}.json
        Serializes with indent=2 for readability.
        Returns the path to the saved file.
        """
        path = self.conversations_dir / f"conversation-{phase.value}.json"
        path.write_text(
            json.dumps(transcript, indent=2, default=str), encoding="utf-8"
        )
        logger_store.info("Saved conversation %s", path.name)
        return path

    def load_conversation(
        self, phase: PhaseKey
    ) -> list[dict[str, object]] | None:
        """Load a saved conversation. Returns None if not found."""
        path = self.conversations_dir / f"conversation-{phase.value}.json"
        if not path.exists():
            return None
        raw: list[dict[str, object]] = json.loads(
            path.read_text(encoding="utf-8")
        )
        return raw

    # -- Metrics -----------------------------------------------------------

    def save_phase_metrics(
        self, phase: PhaseKey, metrics: dict[str, object]
    ) -> Path:
        """Save phase metrics as JSON.

        Filename: phase-{phase.value}-metrics.json
        Returns the path to the saved file.
        """
        path = self.metrics_dir / f"phase-{phase.value}-metrics.json"
        path.write_text(
            json.dumps(metrics, indent=2, default=str), encoding="utf-8"
        )
        logger_store.info("Saved phase metrics %s", path.name)
        return path

    def save_timing_waterfall(self, waterfall: dict[str, object]) -> Path:
        """Save timing waterfall for the full run.

        Filename: timing-waterfall.json
        Returns the path to the saved file.
        """
        path = self.metrics_dir / "timing-waterfall.json"
        path.write_text(
            json.dumps(waterfall, indent=2, default=str), encoding="utf-8"
        )
        logger_store.info("Saved timing waterfall")
        return path

    def save_cost_report(
        self, report: dict[str, object]
    ) -> tuple[Path, Path]:
        """Save cost report as both timestamped archive and latest.

        Files:
          cost-report-{YYYYMMDD-HHMMSS}.json  (archive)
          cost-report.json                     (latest)

        Returns (archive_path, latest_path).
        """
        ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
        body = json.dumps(report, indent=2, default=str)

        archive_path = self.metrics_dir / f"cost-report-{ts}.json"
        latest_path = self.metrics_dir / "cost-report.json"

        archive_path.write_text(body, encoding="utf-8")
        latest_path.write_text(body, encoding="utf-8")
        logger_store.info("Saved cost report (archive: %s)", archive_path.name)
        return archive_path, latest_path

    def save_consistency_report(self, report: dict[str, object]) -> Path:
        """Save cross-phase consistency report.

        Filename: cross-phase-consistency.json
        Returns the path to the saved file.
        """
        path = self.metrics_dir / "cross-phase-consistency.json"
        path.write_text(
            json.dumps(report, indent=2, default=str), encoding="utf-8"
        )
        logger_store.info("Saved consistency report")
        return path

    # -- Resume detection --------------------------------------------------

    def detect_completed_phases(self) -> list[PhaseKey]:
        """Scan deliverables/ directory and return phases that have saved deliverables.

        Used for run resumption: if phase N has a deliverable, it's complete.
        Returns phases in methodology order (P1, P2, ... P10).
        """
        found: list[PhaseKey] = []
        for pk in PhaseKey:
            path = self.deliverables_dir / f"deliverable-{pk.value}.md"
            if path.exists():
                found.append(pk)
        return found

    def build_phase_outcome(self, phase: PhaseKey) -> PhaseOutcome:
        """Build a PhaseOutcome from saved artifacts for a completed phase.

        Reads deliverable, conversation, and metrics files. Populates
        all PhaseOutcome fields from the saved data. If metrics file
        is missing, leaves numeric fields at defaults.

        Raises FileNotFoundError if the deliverable doesn't exist
        (phase not completed).
        """
        deliv_path = self.deliverables_dir / f"deliverable-{phase.value}.md"
        if not deliv_path.exists():
            raise FileNotFoundError(
                f"No deliverable for phase {phase.value}: {deliv_path}"
            )
        content = deliv_path.read_text(encoding="utf-8")

        conv_path = self.conversations_dir / f"conversation-{phase.value}.json"
        metrics_path = self.metrics_dir / f"phase-{phase.value}-metrics.json"

        outcome = PhaseOutcome(
            phase=phase,
            status="completed",
            deliverable_path=str(deliv_path.relative_to(self.root)),
            deliverable_chars=len(content),
        )

        if conv_path.exists():
            outcome.conversation_path = str(conv_path.relative_to(self.root))
            transcript: list[dict[str, object]] = json.loads(
                conv_path.read_text(encoding="utf-8")
            )
            outcome.exchange_count = sum(
                1 for t in transcript if t.get("role") == "founder"
            )

        if metrics_path.exists():
            outcome.metrics_path = str(metrics_path.relative_to(self.root))
            metrics: dict[str, object] = json.loads(
                metrics_path.read_text(encoding="utf-8")
            )
            if "cost_usd" in metrics:
                outcome.cost_usd = Decimal(str(metrics["cost_usd"]))
            if "elapsed_seconds" in metrics:
                outcome.elapsed_seconds = float(
                    str(metrics["elapsed_seconds"])
                )
            if "started_at" in metrics:
                outcome.started_at = str(metrics["started_at"])
            if "completed_at" in metrics:
                outcome.completed_at = str(metrics["completed_at"])

        return outcome

    # -- Founder memory ----------------------------------------------------

    def save_founder_memory(self, content: str) -> Path:
        """Save founder memory to deliverables/founder-memory.md."""
        target = self.deliverables_dir / "founder-memory.md"
        target.write_text(content, encoding="utf-8")
        logger_store.info("Saved founder memory (%d chars)", len(content))
        return target

    def load_founder_memory(self) -> str | None:
        """Load founder memory from deliverables/founder-memory.md."""
        target = self.deliverables_dir / "founder-memory.md"
        if not target.exists():
            return None
        return target.read_text(encoding="utf-8")

    # -- Review artifacts --------------------------------------------------

    def save_review_findings(
        self, phase: PhaseKey, layer: int, findings_json: str
    ) -> Path:
        """Save review findings JSON to metrics directory."""
        target = self.metrics_dir / f"phase-{phase.value}-l{layer}-review.json"
        target.write_text(findings_json, encoding="utf-8")
        return target

    def save_review_pipeline_summary(
        self, phase: PhaseKey, summary_json: str
    ) -> Path:
        """Save review pipeline summary to metrics directory."""
        target = self.metrics_dir / f"phase-{phase.value}-review-pipeline.json"
        target.write_text(summary_json, encoding="utf-8")
        return target

    def save_interview_brief(
        self, phase: PhaseKey, brief_xml: str
    ) -> Path:
        """Save interview brief XML to metrics directory."""
        target = self.metrics_dir / f"phase-{phase.value}-interview-brief.xml"
        target.write_text(brief_xml, encoding="utf-8")
        return target

    def save_reengagement_transcript(
        self, phase: PhaseKey, transcript_json: str
    ) -> Path:
        """Save re-engagement conversation to conversations directory."""
        target = self.conversations_dir / f"phase-{phase.value}-reengagement.json"
        target.write_text(transcript_json, encoding="utf-8")
        return target

    def save_correction_debug(
        self, phase: PhaseKey, round_num: int, raw_xml: str
    ) -> Path:
        """Save raw correction XML for debugging."""
        target = self.metrics_dir / f"phase-{phase.value}-correction-{round_num}-raw.txt"
        target.write_text(raw_xml, encoding="utf-8")
        return target

    # -- Template cache ----------------------------------------------------

    def cache_template(self, filename: str, content: str) -> Path:
        """Write a template file to the local cache.

        Returns the cache file path.
        """
        path = self.templates_dir / filename
        path.write_text(content, encoding="utf-8")
        logger_store.debug("Cached template %s", filename)
        return path

    def load_cached_template(self, filename: str) -> str | None:
        """Load a template from cache. Returns None if not cached."""
        path = self.templates_dir / filename
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")

    # -- GitHub publishing -------------------------------------------------

    def publish_to_github(
        self,
        phase: PhaseKey,
        github_repo: str,
        github_pat: str,
        label: str = "",
    ) -> dict[str, int]:
        """Push output/ files to GitHub via Contents API.

        Iterates all files in output/ recursively. For each file:
        - Skips directories and .gitkeep files
        - GETs the file from GitHub to check existence
        - Compares git blob SHA (header = "blob {size}\\0" + content)
        - If unchanged, skips. If new or changed, PUTs.
        - Non-fatal: individual file failures do not stop the loop.

        Returns {"pushed": N, "skipped": N, "failed": N}.

        Uses urllib.request (stdlib), NOT the requests library.

        # TODO: D-196 future optimization — use GitHub Trees API for
        # batched single-commit publishing instead of per-file PUT.
        """
        output_dir = self.root / "output"
        stats: dict[str, int] = {"pushed": 0, "skipped": 0, "failed": 0}

        if not output_dir.exists():
            return stats

        for file_path in sorted(output_dir.rglob("*")):
            if file_path.is_dir():
                continue
            if file_path.name == ".gitkeep":
                continue

            rel = file_path.relative_to(self.root)
            repo_path = f"dry-run/{rel}"
            content_bytes = file_path.read_bytes()
            local_sha = _git_blob_sha(content_bytes)

            api_url = (
                f"https://api.github.com/repos/{github_repo}"
                f"/contents/{repo_path}"
            )
            headers = {
                "Authorization": f"token {github_pat}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PlatformForge-Orchestrator",
            }

            remote_sha: str | None = None
            try:
                get_req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(get_req) as resp:
                    body: dict[str, object] = json.loads(resp.read())
                    remote_sha = str(body.get("sha", ""))
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    logger_store.warning(
                        "GitHub GET failed for %s: %s", repo_path, e
                    )
                    stats["failed"] += 1
                    continue
                # 404 = new file, remote_sha stays None

            if remote_sha is not None and remote_sha == local_sha:
                stats["skipped"] += 1
                continue

            encoded = base64.b64encode(content_bytes).decode("ascii")
            put_body: dict[str, str] = {
                "message": f"Update {repo_path} ({label or phase.value})",
                "content": encoded,
            }
            if remote_sha is not None:
                put_body["sha"] = remote_sha

            try:
                put_data = json.dumps(put_body).encode("utf-8")
                put_req = urllib.request.Request(
                    api_url,
                    data=put_data,
                    headers={**headers, "Content-Type": "application/json"},
                    method="PUT",
                )
                with urllib.request.urlopen(put_req) as resp:
                    if resp.status in (200, 201):
                        stats["pushed"] += 1
                    else:
                        stats["failed"] += 1
            except (urllib.error.HTTPError, urllib.error.URLError) as e:
                logger_store.warning(
                    "GitHub PUT failed for %s: %s", repo_path, e
                )
                stats["failed"] += 1

        logger_store.info(
            "GitHub publish (phase %s): pushed=%d, skipped=%d, failed=%d",
            phase.value,
            stats["pushed"],
            stats["skipped"],
            stats["failed"],
        )
        return stats


# ---------------------------------------------------------------------------
# StateRegistry
# ---------------------------------------------------------------------------

class StateRegistry:
    """Cross-phase canonical fact registry with supersession rules.

    Stores CanonicalFact entries keyed by '{namespace}:{subject}.{attribute}'.
    When a fact with the same key is registered from a later phase, it
    supersedes the earlier one.

    Phase ordering follows the PhaseKey enum: P1 < P2 < ... < P10.
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._facts: dict[str, CanonicalFact] = {}
        self._supersession_log: list[dict[str, str]] = []

    def register(self, fact: CanonicalFact) -> bool:
        """Register a canonical fact.

        If a fact with the same key already exists:
        - If the new fact's source_phase is later (higher ordinal),
          it supersedes the old fact. Returns True.
        - If the new fact's source_phase is earlier or equal,
          the old fact is kept. Returns False.

        If no existing fact, registers and returns True.

        The key is built using contracts.fact_key(namespace, subject, attribute).
        """
        key = fact_key(fact.namespace, fact.subject, fact.attribute)

        if key in self._facts:
            existing = self._facts[key]
            if _PHASE_ORDER[fact.source_phase] > _PHASE_ORDER[existing.source_phase]:
                self._supersession_log.append({
                    "key": key,
                    "old_phase": existing.source_phase.value,
                    "new_phase": fact.source_phase.value,
                    "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                })
                self._facts[key] = fact
                return True
            return False

        self._facts[key] = fact
        return True

    def get(
        self, namespace: str, subject: str, attribute: str
    ) -> CanonicalFact | None:
        """Look up a single fact by key components. Returns None if not found."""
        key = fact_key(namespace, subject, attribute)
        return self._facts.get(key)

    def get_by_key(self, key: str) -> CanonicalFact | None:
        """Look up a single fact by its full key string."""
        return self._facts.get(key)

    def query_namespace(self, namespace: str) -> list[CanonicalFact]:
        """Return all facts in a namespace, ordered by key."""
        return [
            f
            for k, f in sorted(self._facts.items())
            if f.namespace == namespace
        ]

    def query_phase(self, phase: PhaseKey) -> list[CanonicalFact]:
        """Return all facts whose source_phase matches, ordered by key."""
        return [
            f
            for k, f in sorted(self._facts.items())
            if f.source_phase == phase
        ]

    def query_subject(
        self, namespace: str, subject: str
    ) -> list[CanonicalFact]:
        """Return all facts for a specific subject within a namespace."""
        return [
            f
            for k, f in sorted(self._facts.items())
            if f.namespace == namespace and f.subject == subject
        ]

    def all_facts(self) -> list[CanonicalFact]:
        """Return all facts in the registry, ordered by key."""
        return [f for _, f in sorted(self._facts.items())]

    def fact_count(self) -> int:
        """Return the number of facts in the registry."""
        return len(self._facts)

    def to_json(self) -> str:
        """Serialize the entire registry to JSON.

        Output format:
        {
          "facts": {
            "pricing:platform.model": { ...CanonicalFact fields... },
            ...
          },
          "supersession_log": [...]
        }

        Uses Pydantic's model_dump(mode="json") for serialization.
        """
        facts_dict: dict[str, object] = {}
        for key, f in sorted(self._facts.items()):
            facts_dict[key] = f.model_dump(mode="json")

        payload: dict[str, object] = {
            "facts": facts_dict,
            "supersession_log": self._supersession_log,
        }
        return json.dumps(payload, indent=2, default=str)

    @classmethod
    def from_json(cls, data: str) -> StateRegistry:
        """Deserialize a registry from JSON.

        Inverse of to_json(). Restores all facts and the supersession log.
        """
        raw: dict[str, object] = json.loads(data)
        registry = cls()

        facts_raw = raw.get("facts", {})
        if isinstance(facts_raw, dict):
            for key, fact_data in facts_raw.items():
                if isinstance(fact_data, dict):
                    f = CanonicalFact.model_validate(fact_data)
                    registry._facts[key] = f

        log_raw = raw.get("supersession_log", [])
        if isinstance(log_raw, list):
            registry._supersession_log = [
                entry for entry in log_raw if isinstance(entry, dict)
            ]

        return registry

    def save(self, path: Path) -> None:
        """Persist registry to a JSON file."""
        path.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> StateRegistry:
        """Load registry from a JSON file. Raises FileNotFoundError if missing."""
        if not path.exists():
            raise FileNotFoundError(f"Registry file not found: {path}")
        return cls.from_json(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# CostLedger
# ---------------------------------------------------------------------------

@dataclass
class _PhaseBucket:
    """Accumulator for per-phase cost data."""

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))
    external_calls: dict[str, int] = field(default_factory=dict)
    external_cost_usd: Decimal = field(default_factory=lambda: Decimal("0"))


class CostLedger:
    """Thread-safe cost tracking with budget enforcement.

    Accumulates CallUsage entries from the LLM gateway. Provides
    per-phase aggregation, hard ceiling checks, and report generation.

    Thread-safe (D-194): review pipeline runs concurrent LLM calls.
    """

    def __init__(self, hard_ceiling_usd: Decimal) -> None:
        """Initialize with the hard cost ceiling from config."""
        self._ceiling = hard_ceiling_usd
        self._lock = threading.Lock()
        self._buckets: dict[str, _PhaseBucket] = {}
        self._total: Decimal = Decimal("0")

    def _get_bucket(self, phase: PhaseKey) -> _PhaseBucket:
        """Get or create a bucket for a phase. Must be called under lock."""
        key = phase.value
        if key not in self._buckets:
            self._buckets[key] = _PhaseBucket()
        return self._buckets[key]

    def record(self, phase: PhaseKey, usage: CallUsage) -> None:
        """Record a single API call's usage. Thread-safe.

        Raises CostCeilingExceeded if total_cost_usd would exceed
        hard_ceiling_usd after this call.
        """
        with self._lock:
            new_total = self._total + usage.cost_usd
            if new_total > self._ceiling:
                raise CostCeilingExceeded(
                    self._total, usage.cost_usd, self._ceiling
                )
            self._total = new_total

            bucket = self._get_bucket(phase)
            bucket.calls += 1
            bucket.input_tokens += usage.input_tokens
            bucket.output_tokens += usage.output_tokens
            bucket.cache_read_tokens += usage.cache_read_tokens
            bucket.cache_write_tokens += usage.cache_write_tokens
            bucket.cost_usd += usage.cost_usd

        logger_cost.debug(
            "Recorded call phase=%s cost=$%s total=$%s",
            phase.value,
            usage.cost_usd,
            new_total,
        )

    def record_external(
        self, phase: PhaseKey, engine: str, cost_usd: Decimal
    ) -> None:
        """Record a Perplexity/Grok API call cost. Thread-safe."""
        with self._lock:
            new_total = self._total + cost_usd
            if new_total > self._ceiling:
                raise CostCeilingExceeded(
                    self._total, cost_usd, self._ceiling
                )
            self._total = new_total

            bucket = self._get_bucket(phase)
            bucket.external_calls[engine] = (
                bucket.external_calls.get(engine, 0) + 1
            )
            bucket.external_cost_usd += cost_usd

    @property
    def total_cost_usd(self) -> Decimal:
        """Current total cost across all phases."""
        with self._lock:
            return self._total

    @property
    def remaining_budget_usd(self) -> Decimal:
        """Remaining budget before hitting the ceiling."""
        with self._lock:
            return self._ceiling - self._total

    def phase_summary(self, phase: PhaseKey) -> dict[str, object]:
        """Return aggregated metrics for a single phase.

        Returns empty dict if phase has no recorded calls.
        """
        with self._lock:
            key = phase.value
            if key not in self._buckets:
                return {}
            bucket = self._buckets[key]
            return {
                "calls": bucket.calls,
                "input_tokens": bucket.input_tokens,
                "output_tokens": bucket.output_tokens,
                "cache_read_tokens": bucket.cache_read_tokens,
                "cache_write_tokens": bucket.cache_write_tokens,
                "cost_usd": str(bucket.cost_usd),
                "external_calls": dict(bucket.external_calls),
            }

    def build_report(self) -> dict[str, object]:
        """Build the full cost report suitable for JSON serialization."""
        with self._lock:
            total_input = 0
            total_output = 0
            total_cache_read = 0
            total_cache_write = 0
            total_external = Decimal("0")
            phases: dict[str, object] = {}

            for key, bucket in sorted(self._buckets.items()):
                total_input += bucket.input_tokens
                total_output += bucket.output_tokens
                total_cache_read += bucket.cache_read_tokens
                total_cache_write += bucket.cache_write_tokens
                total_external += bucket.external_cost_usd
                phases[key] = {
                    "calls": bucket.calls,
                    "input_tokens": bucket.input_tokens,
                    "output_tokens": bucket.output_tokens,
                    "cache_read_tokens": bucket.cache_read_tokens,
                    "cache_write_tokens": bucket.cache_write_tokens,
                    "cost_usd": str(bucket.cost_usd),
                    "external_calls": dict(bucket.external_calls),
                    "external_cost_usd": str(bucket.external_cost_usd),
                }

            return {
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                "total": {
                    "input_tokens": total_input,
                    "output_tokens": total_output,
                    "cache_read_tokens": total_cache_read,
                    "cache_write_tokens": total_cache_write,
                    "external_cost_usd": str(total_external),
                    "total_cost_usd": str(self._total),
                },
                "phases": phases,
                "ceiling_usd": str(self._ceiling),
                "remaining_usd": str(self._ceiling - self._total),
            }


# ---------------------------------------------------------------------------
# Helpers (module-private)
# ---------------------------------------------------------------------------

def _git_blob_sha(content: bytes) -> str:
    """Compute the git blob SHA-1 for content bytes.

    Git blob format: "blob {size}\\0{content}"
    """
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()  # noqa: S324
