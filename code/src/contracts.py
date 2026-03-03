"""
PlatformForge Orchestrator — Data Contracts (contracts.py)

All shared types used across the orchestrator. No business logic. No I/O.
Pure data definitions.

Decision Authority: D-196 (re-architecture), D-197 (Haiku baseline)
Codex Spec Reference: Section 2.2 (Data Contracts)
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from enum import Enum
from typing import Union

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class PhaseKey(str, Enum):
    """12 phases of the PlatformForge methodology.

    Values are lowercase strings matching template directory names.
    """
    P1 = "1"
    P2 = "2"
    P3 = "3"
    P4 = "4"
    P5 = "5"
    P6A = "6a"
    P6B = "6b"
    P6C = "6c"
    P7 = "7"
    P8 = "8"
    P9 = "9"
    P10 = "10"


class RoleName(str, Enum):
    """9 roles in the orchestrator."""
    GUIDE = "guide"
    FOUNDER = "founder"
    SYNTHESIS = "synthesis"
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    L4 = "l4"
    CORRECTION = "correction"
    CONSISTENCY = "consistency"


# ---------------------------------------------------------------------------
# Canonical Fact types
# ---------------------------------------------------------------------------

# Union of allowed value types for CanonicalFact — no Any.
FactValue = Union[str, int, float, list[str], dict[str, str]]


class CanonicalFact(BaseModel):
    """A single verified fact extracted from founder conversation."""

    namespace: str = Field(
        ..., description="Domain area: pricing, architecture, naming, etc."
    )
    subject: str = Field(
        ..., description="Entity within the namespace."
    )
    attribute: str = Field(
        ..., description="Specific property of the subject."
    )
    value: FactValue = Field(
        ..., description="The verified value. Restricted to known types."
    )
    source_phase: PhaseKey = Field(
        ..., description="Phase where this fact was established."
    )
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0,
        description="Confidence score. 1.0 = explicitly stated by founder."
    )


class PhaseOutcome(BaseModel):
    """Recorded outcome of a completed phase run.

    Captures everything needed to resume after interruption or
    to load prior-phase context for downstream phases.
    """

    phase: PhaseKey
    status: str = Field(
        default="pending",
        description="pending, running, completed, failed",
    )
    deliverable_path: str = Field(
        default="",
        description="Relative path to saved deliverable markdown.",
    )
    conversation_path: str = Field(
        default="",
        description="Relative path to saved conversation JSON.",
    )
    metrics_path: str = Field(
        default="",
        description="Relative path to saved phase metrics JSON.",
    )
    exchange_count: int = Field(
        default=0,
        description="Number of founder exchanges in the conversation.",
    )
    deliverable_chars: int = Field(
        default=0,
        description="Character count of the final deliverable.",
    )
    cost_usd: Decimal = Field(
        default=Decimal("0"),
        description="Total API cost for this phase.",
    )
    elapsed_seconds: float = Field(
        default=0.0,
        description="Total wall-clock time for this phase.",
    )
    started_at: str = Field(
        default="",
        description="ISO 8601 timestamp when phase started.",
    )
    completed_at: str = Field(
        default="",
        description="ISO 8601 timestamp when phase completed.",
    )


# ---------------------------------------------------------------------------
# Template / Deliverable types
# ---------------------------------------------------------------------------

class RequiredElement(BaseModel):
    """A mandatory element within a deliverable section."""

    name: str = Field(..., description="Element identifier.")
    description: str = Field(..., description="What this element must contain.")
    validation_rule: str = Field(
        default="", description="How to verify this element is correct."
    )


class SectionSpec(BaseModel):
    """Specification for one section of a deliverable."""

    section_id: str = Field(..., description="Unique section identifier.")
    title: str = Field(..., description="Section heading.")
    required_elements: list[RequiredElement] = Field(default_factory=list)
    depends_on_fact_keys: list[str] = Field(
        default_factory=list,
        description="Fact keys this section depends on. "
        "Populated by template parser (Step 3).",
    )


class RawTemplateBundle(BaseModel):
    """Raw template file contents before parsing.

    For Phase 1: conversation_raw and synthesis_raw come from separate files.
    For Phases 2-10: both are split from a single combined file.
    """

    phase: PhaseKey
    conversation_raw: str = Field(
        default="",
        description="Raw conversation instructions markdown.",
    )
    synthesis_raw: str = Field(
        default="",
        description="Raw synthesis instructions markdown.",
    )
    source_paths: list[str] = Field(
        default_factory=list,
        description="Filesystem paths that were loaded.",
    )


class PhaseTemplateSpec(BaseModel):
    """Full specification for a phase's deliverable template."""

    phase: PhaseKey
    deliverable_name: str = Field(
        ..., description="Human-readable phase title from the template header."
    )
    conversation_instructions: str = Field(
        default="",
        description="Raw markdown content BEFORE the SYNTHESIS_START marker.",
    )
    synthesis_instructions: str = Field(
        default="",
        description="Raw markdown content AFTER the SYNTHESIS_START marker.",
    )
    completion_gate: list[str] = Field(
        default_factory=list,
        description="Completion gate checklist items.",
    )
    sections: list[SectionSpec] = Field(default_factory=list)
    required_elements: list[RequiredElement] = Field(default_factory=list)
    output_artifacts: list[str] = Field(
        default_factory=list,
        description="Names of deliverable outputs from phase_outputs.",
    )
    template_path: str = Field(
        default="", description="Path to the raw template file."
    )


class DeliverableArtifact(BaseModel):
    """A completed deliverable produced by synthesis.

    section_hashes uses SHA-256 of normalized markdown content:
    strip leading/trailing whitespace, normalize line endings to \\n,
    then hash. This provides change detection across review cycles.
    """

    phase: PhaseKey
    deliverable_name: str
    markdown_content: str = Field(
        ..., description="Full markdown text of the deliverable."
    )
    section_hashes: dict[str, str] = Field(
        default_factory=dict,
        description="Map of section_id -> SHA-256 hash of normalized section content.",
    )
    fact_keys_used: list[str] = Field(
        default_factory=list,
        description="Canonical fact keys referenced during generation.",
    )
    generation_model: str = Field(
        default="", description="Model ID used to generate this deliverable."
    )
    generation_cost_usd: Decimal = Field(
        default=Decimal("0"),
        description="Actual API cost for generating this deliverable.",
    )


# ---------------------------------------------------------------------------
# Message / Job types
# ---------------------------------------------------------------------------

class CallUsage(BaseModel):
    """Token usage and cost for a single API call."""

    role: RoleName
    model_id: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    cost_usd: Decimal


class MessageJob(BaseModel):
    """Job descriptor for an LLM API call.

    Contains everything needed to construct and dispatch a single
    Anthropic Messages API request.
    """

    role: RoleName
    phase: PhaseKey
    label: str = Field(..., description="Human-readable description for logging.")

    # --- Step 2 additions ---
    system_prompt: str = Field(
        default="", description="System prompt for the API call."
    )
    messages: list[dict[str, object]] = Field(
        default_factory=list,
        description="Conversation messages. Each dict has 'role' and 'content' keys.",
    )
    tools: list[dict[str, object]] = Field(
        default_factory=list,
        description="Tool definitions for the API call (e.g., web_search).",
    )
    max_output_tokens: int | None = Field(
        default=None,
        description="Override output token limit. If None, uses role policy default.",
    )
    thinking_budget: int | None = Field(
        default=None,
        description=(
            "Thinking token budget. None = use tier/role default. "
            "0 = explicitly disabled. >0 = budget in tokens."
        ),
    )


class MessageResult(BaseModel):
    """Result from a single LLM API call."""

    role: RoleName
    phase: PhaseKey
    label: str

    # Content
    text: str = Field(
        default="", description="Concatenated text content from the response."
    )
    thinking_text: str = Field(
        default="",
        description="Concatenated thinking block content, if any.",
    )
    tool_use_blocks: list[dict[str, object]] = Field(
        default_factory=list,
        description="Raw tool_use content blocks from the response.",
    )
    tool_result_blocks: list[dict[str, object]] = Field(
        default_factory=list,
        description="Raw tool_result content blocks (from continuations).",
    )
    stop_reason: str = Field(
        default="end_turn",
        description="API stop reason: end_turn, tool_use, max_tokens, etc.",
    )

    # Usage
    usage: CallUsage | None = Field(
        default=None, description="Token usage and cost for this call."
    )

    # Timing
    wall_seconds: float = Field(
        default=0.0, description="Wall-clock time for the API call in seconds."
    )

    # Error state
    error: str | None = Field(
        default=None,
        description="Error message if the call failed after all retries.",
    )
    retries_attempted: int = Field(
        default=0, description="Number of retry attempts before success or final failure."
    )


class PhaseResult(BaseModel):
    """Complete result from a single phase execution.

    Returned by PhaseService.run_phase(). Contains everything
    the orchestrator and review pipeline need to proceed.
    """

    outcome: PhaseOutcome
    deliverable_text: str = Field(
        default="",
        description="Raw markdown content of the generated deliverable.",
    )
    transcript: list[dict[str, object]] = Field(
        default_factory=list,
        description="Conversation transcript. Each dict has 'role', 'text', optional 'research'.",
    )
    extracted_facts: list[CanonicalFact] = Field(
        default_factory=list,
        description="Facts extracted from the conversation and registered in StateRegistry.",
    )
    template_spec: PhaseTemplateSpec | None = Field(
        default=None,
        description="Parsed template spec for this phase. Useful for review pipeline.",
    )


# ---------------------------------------------------------------------------
# Orchestrator types
# ---------------------------------------------------------------------------

class RunSummary(BaseModel):
    """Complete summary of an orchestrator run."""

    phases_requested: list[str] = Field(
        default_factory=list, description="Phase values requested for this run."
    )
    phases_completed: list[str] = Field(
        default_factory=list, description="Phase values successfully completed."
    )
    total_cost_usd: str = Field(
        default="0.00", description="Total cost as Decimal string."
    )
    total_elapsed_seconds: float = Field(default=0.0)
    consistency_check_run: bool = Field(default=False)
    halted_at_phase: str = Field(
        default="", description="Phase where run stopped, if not all completed."
    )
    halt_reason: str = Field(default="")


# ---------------------------------------------------------------------------
# Review Pipeline types
# ---------------------------------------------------------------------------

class ReviewFinding(BaseModel):
    """A single finding from an L1-L4 review layer."""

    id: str = Field(..., description="Finding ID, e.g. 'L2-3'.")
    category: str = Field(
        ..., description="must-fix, should-improve, or consider."
    )
    section: str = Field(default="unknown", description="Section of the deliverable.")
    issue: str = Field(default="", description="What is wrong or missing.")
    evidence: str = Field(default="", description="Quote or reference from deliverable/template.")
    recommendation: str = Field(default="", description="Specific action to resolve.")


class PatchEntry(BaseModel):
    """A single correction patch parsed from XML."""

    id: str = Field(..., description="Patch ID matching a finding ID.")
    action: str = Field(
        ..., description="replace, insert_after, insert_before, or append_to_section."
    )
    anchor: str = Field(default="", description="Exact markdown heading for context.")
    search_text: str = Field(default="", description="Exact text to find in deliverable.")
    new_text: str = Field(default="", description="Replacement or inserted content.")


class PatchResult(BaseModel):
    """Result of applying a single patch."""

    id: str
    action: str
    status: str = Field(
        ..., description="applied, applied_fuzzy, applied_anchored, "
        "skipped_not_found, skipped_ambiguous, skipped_anchor_not_found, "
        "skipped_no_search, skipped_empty_replacement, skipped_unknown_action."
    )
    detail: str = Field(default="")


class ReviewPipelineResult(BaseModel):
    """Complete result from the review pipeline."""

    deliverable_text: str = Field(
        ..., description="Final deliverable after all corrections and updates."
    )
    review_notes: str = Field(
        default="", description="Consider items document (markdown)."
    )
    l1_initial_missing: int = Field(default=0)
    l2_findings: list[ReviewFinding] = Field(default_factory=list)
    l3_findings: list[ReviewFinding] = Field(default_factory=list)
    l4_findings: list[ReviewFinding] = Field(default_factory=list)
    total_must_fix: int = Field(default=0)
    total_should_improve: int = Field(default=0)
    total_consider: int = Field(default=0)
    reengagement_triggered: bool = Field(default=False)
    pipeline_elapsed_seconds: float = Field(default=0.0)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def phase_key(value: str | int) -> PhaseKey:
    """Convert a raw value to PhaseKey.

    Accepts string or int representations (e.g., "6a", "1", 1).
    Raises ValueError if the value doesn't match any PhaseKey.
    """
    raw = str(value).lower().strip()
    for pk in PhaseKey:
        if pk.value == raw:
            return pk
    valid = [pk.value for pk in PhaseKey]
    raise ValueError(
        f"Invalid phase key: {value!r}. Valid values: {valid}"
    )


def role_name(value: str) -> RoleName:
    """Convert a raw value to RoleName.

    Raises ValueError if the value doesn't match any RoleName.
    """
    raw = value.lower().strip()
    for rn in RoleName:
        if rn.value == raw:
            return rn
    valid = [rn.value for rn in RoleName]
    raise ValueError(
        f"Invalid role name: {value!r}. Valid values: {valid}"
    )


def fact_key(namespace: str, subject: str, attribute: str) -> str:
    """Build a canonical fact key.

    Format: '{namespace}:{subject}.{attribute}'
    """
    return f"{namespace}:{subject}.{attribute}"


def section_hash(markdown: str) -> str:
    """SHA-256 of normalized markdown content.

    Normalization: strip leading/trailing whitespace, normalize
    line endings to \\n before hashing.
    """
    normalized = markdown.strip().replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
