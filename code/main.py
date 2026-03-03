#!/usr/bin/env python3
"""
PlatformForge Methodology Dry Run Orchestrator
================================================
Runs the full 10-phase PlatformForge methodology using a dual-Claude loop:
  - Guide Claude: Runs the methodology with web search
  - Founder Claude: Plays the Ocean Golf founder persona
  - Synthesis Claude: Generates deliverables from conversation

Usage:
    export ANTHROPIC_API_KEY="your-key-here"
    pip install anthropic --break-system-packages
    python main.py [--phase N] [--max-exchanges 40] [--dry-run]

    --phase N           Start from phase N (default: 1, useful for resuming)
    --max-exchanges N   Max conversation exchanges per phase (default: 40)
    --dry-run           Print config and exit without making API calls
"""

import os
import sys
import re
import copy
import json
import time
import argparse
import base64
import hashlib
import subprocess
import traceback
import threading
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import warnings
warnings.filterwarnings("ignore", message=".*PydanticDeprecatedSince.*")


# S84: Module-level singleton for Anthropic client (connection pooling)
_anthropic_client = None


# ---------------------------------------------------------------------------
# .env file loader (no external dependencies)
# ---------------------------------------------------------------------------

def load_env_file():
    """
    Load environment variables from a .env file in the same directory as main.py.

    Supports KEY=value and KEY="value" formats. Skips comments (#) and blank lines.
    Does NOT override variables already set in the environment.
    """
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return 0

    loaded = 0
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


# Load .env before anything else touches env vars
_env_loaded = load_env_file()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# D-185: PAT loaded from .env — never hardcode secrets in source
GITHUB_PAT = os.environ.get("GITHUB_PAT", "")
GITHUB_REPO = "brdonath1/platformforge"
TEMPLATES_PATH = "artifacts/current"

GUIDE_MODEL = "claude-haiku-4-5-20251001"
FOUNDER_MODEL = "claude-haiku-4-5-20251001"
SYNTHESIS_MODEL = "claude-haiku-4-5-20251001"
# S84: Semantic alias — same model as Founder but used for validation, memory,
# and other utility tasks that aren't founder conversation.
UTILITY_MODEL = FOUNDER_MODEL

# D-188: Single variable controls all review pipeline layers (L1-L4 + correction synthesis).
# D-191: Set to Haiku 4.5 for fast iteration. D-192 graduated escalation:
#   Tier 1: claude-haiku-4-5-20251001  (~$20, ~4h)
#   Tier 2: claude-sonnet-4-5-20241022 (~$60, ~7h)
#   Tier 3: claude-sonnet-4-6          (~$110, ~12h)
#   Tier 4: claude-sonnet-4-6 high     (~$135, ~16h)
REVIEW_MODEL = "claude-haiku-4-5-20251001"

MAX_GUIDE_TOKENS = 64000       # Guide responses (Haiku ceiling 64K; Opus/Sonnet 65536)
MAX_FOUNDER_TOKENS = 16384     # Founder responses (no thinking — conversational only)
MAX_SYNTHESIS_TOKENS = 64000   # Deliverable generation (Haiku ceiling 64K; Opus 128K)
MAX_VALIDATION_TOKENS = 8192   # Post-synthesis structural validation (Sonnet)
MAX_EXCHANGES = 75            # Safety limit per phase

# D-188: Review pipeline token limits per layer
MAX_L1_TOKENS = 8192           # L1 compliance — mechanical checklist
MAX_L2_TOKENS = 32768          # L2 domain expert — deep analysis
MAX_L3_TOKENS = 32768          # L3 downstream consumer — cross-phase reasoning
MAX_L4_TOKENS = 16384          # L4 founder comprehension — accessibility check
MAX_CORRECTION_TOKENS = 32768  # Correction synthesis — surgical fixes
MAX_REENGAGEMENT_TOPICS = 8    # Cap on should-improve items per interview brief
MAX_L1_RETRIES = 2             # L1 re-check attempts before accepting
MAX_REENGAGEMENT_EXCHANGES = 5 # Max exchanges in founder re-engagement conversation

# Web search: $10/1K searches. Limit per guide call to control cost.
WEB_SEARCH_MAX_USES = 3

# S73 3h: Cost ceiling — halt gracefully if cumulative cost exceeds this limit
MAX_RUN_COST_USD = 200.0       # S76: Raised from $50 for unattended full 10-phase runs

# S73 3d: API retry configuration
API_MAX_RETRIES = 3            # Retry transient errors (429, 500, 502, 503, timeout)
API_RETRY_BASE_DELAY = 5      # Base delay in seconds (doubles each retry)
# S77 D-178: Overloaded (529) gets longer retry window for overnight resilience
API_OVERLOADED_RETRY_DELAY = 15   # Fixed 15s between retries
API_OVERLOADED_MAX_WAIT = 300     # Keep retrying for up to 300s total (5 min cap per CLAUDE.md)

# S73 3c: Context editing — automatically clear old tool results and thinking
# as Guide conversations grow. Reduces token waste from stale web search results
# in long multi-turn conversations. Only affects Guide calls.
# D-194: clear_thinking_20251015 requires thinking enabled — skip for Haiku.
_context_edits = []
if "haiku" not in GUIDE_MODEL:
    _context_edits.append({"type": "clear_thinking_20251015"})
_context_edits.append({
    "type": "clear_tool_uses_20250919",
    "trigger": {"type": "input_tokens", "value": 100_000},
    "keep": {"type": "tool_uses", "value": 5},
    "clear_at_least": {"type": "input_tokens", "value": 10_000},
})
GUIDE_CONTEXT_MANAGEMENT = {"edits": _context_edits}

# Pricing (per million tokens) — update if rates change
# D-152: Long-context pricing applies when total input tokens > 200K
# Total input = input_tokens + cache_read + cache_write
PRICING = {
    "claude-opus-4-6":   {"input": 5.00, "output": 25.00, "cache_read": 0.50, "cache_write": 6.25,
                          "input_long": 10.00, "output_long": 37.50, "cache_read_long": 1.00, "cache_write_long": 12.50},
    "claude-sonnet-4-6": {"input": 3.00,  "output": 15.00, "cache_read": 0.30, "cache_write": 3.75,
                          "input_long": 6.00, "output_long": 22.50, "cache_read_long": 0.60, "cache_write_long": 7.50},
    # D-191: Haiku 4.5 for fast iteration mode. No long-context tier (200K cap).
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00, "cache_read": 0.10, "cache_write": 1.25},
    "web_search_per_query": 0.01,  # $10/1K = $0.01 each
}

# Phase template mapping
# Phase 1 is special: separate conversation + synthesis templates
# Phase 6 has three sub-phases (a, b, c)
# All others are single combined templates
PHASE_TEMPLATES = {
    1:    {"conversation": "phase-1-conversation.md",     "synthesis": "phase-1-synthesis.md"},
    2:    {"combined": "phase-2-users.md"},
    3:    {"combined": "phase-3-features.md"},
    4:    {"combined": "phase-4-data.md"},
    5:    {"combined": "phase-5-technical-architecture.md"},
    "6a": {"combined": "phase-6a-design-foundation.md"},
    "6b": {"combined": "phase-6b-page-architecture.md"},
    "6c": {"combined": "phase-6c-interaction-synthesis.md"},
    7:    {"combined": "phase-7-build-planning.md"},
    8:    {"combined": "phase-8-lifecycle-operations.md"},
    9:    {"combined": "phase-9-review-validation.md"},
    10:   {"combined": "phase-10-github-push-handoff.md"},
}

# Ordered list of phases to execute
PHASE_ORDER = [1, 2, 3, 4, 5, "6a", "6b", "6c", 7, 8, 9, 10]

# Markers for phase completion detection
GUIDE_COMPLETE_MARKER = "[READY_FOR_SYNTHESIS]"
FOUNDER_COMPLETE_MARKER = "[PHASE_COMPLETE]"


# D-188: Review personas loaded from external files at startup via load_review_personas()

# Guide system prompt preamble (prepended to master-system-prompt + phase template)
GUIDE_PREAMBLE = """
<simulation_context>
IMPORTANT — READ BEFORE PROCEEDING:

You are running inside an automated methodology validation simulation. The "founder" you are
speaking with is another AI playing the role of Rafael Delgado, founder of Ocean Golf (a luxury
golf concierge platform in Cabo San Lucas). Treat them as you would a real founder — ask probing
questions, challenge assumptions, surface risks, expand their thinking.

BEHAVIORAL ADJUSTMENTS FOR THIS SIMULATION:
1. Use the web_search tool for all live research instead of Perplexity, Grok, or Deep Research
   (those engines are not available). The web_search tool is your only research tool.
2. Skip any instructions about phone calls, voice mode, or Retell AI — this is text-only.
3. When you believe the phase conversation is complete and you are ready to move to deliverable
   synthesis, include the marker [READY_FOR_SYNTHESIS] at the END of your final message.
4. Follow the phase template's conversation structure and completion gates rigorously.
5. Do not rush — explore each conversation area thoroughly before moving to the next.
6. The founder will confirm phase completion with [PHASE_COMPLETE] — wait for this before ending.
</simulation_context>

"""

# Synthesis preamble (prepended to master-system-prompt + synthesis template)
SYNTHESIS_PREAMBLE = """
<role>
You are a professional document generation engine for PlatformForge, an AI-guided
platform planning service. Your sole task is to produce complete, publication-ready
deliverable documents from completed phase conversations.

You are NOT a conversation agent. You do not discuss, summarize, or explain.
You generate the full deliverable document as specified in the synthesis template below.
</role>

<generation_rules>
1. Produce the COMPLETE deliverable with every section specified in the template.
   A table of contents, summary, or index is NOT a deliverable — the actual content is.
2. Every required section must contain substantive prose content, not placeholders or stubs.
3. Include all appendices, manifests, and structured data specified in the template.
4. Use evidence from the conversation transcript and research data provided.
   Quote specific data points (market sizes, competitor names, pricing) from the research.
5. The deliverable must be self-contained — a reader who was not in the conversation
   should fully understand the platform's vision from this document alone.
6. Output as a complete markdown document beginning with a level-1 heading (#).
7. Do not include preamble text like "I'll now generate..." — start directly with the document.
8. Do not truncate or abbreviate any section. If you are running out of output space,
   prioritize completing the current section fully before starting the next.
</generation_rules>
"""

# ---------------------------------------------------------------------------
# Output directories
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("output")
CONVERSATIONS_DIR = OUTPUT_DIR / "conversations"
DELIVERABLES_DIR = OUTPUT_DIR / "deliverables"
METRICS_DIR = OUTPUT_DIR / "metrics"
TEMPLATES_DIR = OUTPUT_DIR / "templates_cache"

# D-152: 1M context window ACTIVE (Tier 4 confirmed)
# With 1M tokens available, all prior deliverables load in full text.
# No extraction needed. No budget splitting needed.
# Long-context pricing applies when input exceeds 200K tokens:
#   Input: $10/MTok (2x standard), Output: $37.50/MTok (1.5x standard)
#   Prompt caching still applies on top of long-context rates.


def setup_directories():
    """Create output directory structure."""
    for d in [CONVERSATIONS_DIR, DELIVERABLES_DIR, METRICS_DIR, TEMPLATES_DIR]:
        d.mkdir(parents=True, exist_ok=True)


# S82 D-179 FIX: Auto-push output to GitHub via API (replaces local git push)
def git_push_output(phase_key, label: str = ""):
    """
    Push output/ directory files to GitHub via the Contents API.
    Non-fatal: prints warnings but never crashes the run.
    Uses the API directly — no dependency on local git state or remote sync.
    """
    commit_msg = f"dry-run: phase {phase_key} completed"
    if label:
        commit_msg += f" — {label}"

    output_dir = Path("output")
    if not output_dir.is_dir():
        print(f"\n  ⚠ No output/ directory found")
        return False

    pushed = 0
    skipped = 0
    failed = 0

    for local_path in sorted(output_dir.rglob("*")):
        if local_path.is_dir() or local_path.name == ".gitkeep":
            continue

        repo_path = f"dry-run/{local_path}"
        api_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{repo_path}"
        headers = {
            "Authorization": f"Bearer {GITHUB_PAT}",
            "Accept": "application/vnd.github.v3+json",
        }

        try:
            # Read local file and encode
            local_bytes = local_path.read_bytes()
            content_b64 = base64.b64encode(local_bytes).decode("utf-8")

            # Check if file already exists in GitHub (need SHA for updates)
            sha = None
            try:
                check_req = urllib.request.Request(api_url, headers=headers)
                with urllib.request.urlopen(check_req, timeout=30) as resp:
                    existing = json.loads(resp.read().decode("utf-8"))
                    sha = existing.get("sha")
                    # S84: Compare git blob SHA for accurate change detection
                    # (size comparison could miss same-size content changes)
                    blob_header = f"blob {len(local_bytes)}\0".encode()
                    local_sha = hashlib.sha1(blob_header + local_bytes).hexdigest()
                    if sha == local_sha:
                        skipped += 1
                        continue
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    print(f"\n  ⚠ Check failed for {repo_path}: HTTP {e.code}")
                    failed += 1
                    continue
                # 404 = new file, no SHA needed

            # Build payload
            payload = {"message": commit_msg, "content": content_b64}
            if sha:
                payload["sha"] = sha

            # Push file
            data = json.dumps(payload).encode("utf-8")
            put_req = urllib.request.Request(api_url, data=data, headers={
                **headers,
                "Content-Type": "application/json",
            }, method="PUT")

            with urllib.request.urlopen(put_req, timeout=60) as resp:
                if resp.status in (200, 201):
                    pushed += 1

        except urllib.error.HTTPError as e:
            print(f"\n  ⚠ Push failed for {repo_path}: HTTP {e.code}")
            failed += 1
        except Exception as e:
            print(f"\n  ⚠ Push error for {repo_path}: {type(e).__name__}: {e}")
            traceback.print_exc()
            failed += 1

    if pushed > 0:
        print(f"\n  📤 Pushed {pushed} file(s) to GitHub via API: {commit_msg}")
    if skipped > 0:
        print(f"\n  ℹ {skipped} file(s) unchanged — skipped")
    if failed > 0:
        print(f"\n  ⚠ {failed} file(s) failed to push")
    if pushed == 0 and failed == 0 and skipped == 0:
        print(f"\n  ℹ No output files to push for phase {phase_key}")

    return failed == 0


# ---------------------------------------------------------------------------
# GitHub template fetching
# ---------------------------------------------------------------------------

def fetch_github_file(path: str) -> str:
    """Fetch a file from the PlatformForge GitHub repo."""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github.raw+json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"  ⚠ Failed to fetch {path}: HTTP {e.code}")
        raise


def load_template(filename: str) -> str:
    """Load a template, using cache if available."""
    cache_path = TEMPLATES_DIR / filename
    if cache_path.exists():
        return cache_path.read_text()

    print(f"  📥 Fetching template: {filename}")
    content = fetch_github_file(f"{TEMPLATES_PATH}/{filename}")
    cache_path.write_text(content)
    return content


def load_persona() -> str:
    """Load the founder persona document."""
    persona_path = Path(__file__).parent / "persona.md"
    if not persona_path.exists():
        print("❌ persona.md not found! Place it in the same directory as main.py.")
        sys.exit(1)
    return persona_path.read_text()


# ---------------------------------------------------------------------------
# Anthropic API calls
# ---------------------------------------------------------------------------

def _execute_stream(client, kwargs, show_progress=True):
    """
    Execute a single streaming API call and return parsed results.

    Extracted from call_api to keep retry logic clean. All streaming event
    handling lives here — call_api handles setup, config, and retry.

    Returns dict with content, usage, stop_reason, search_count, thinking_chars.
    """

    content_blocks = []
    current_block = None
    current_text = ""
    current_thinking = ""
    current_signature = ""
    stop_reason = None
    usage_input = 0
    usage_output = 0
    usage_cache_read = 0
    usage_cache_write = 0
    search_count = 0
    thinking_chars = 0
    total_chars = 0
    last_progress_chars = 0
    thinking_start = None
    last_heartbeat = 0

    with client.messages.stream(**kwargs) as stream:
        for event in stream:
            event_type = getattr(event, "type", "")

            if event_type == "content_block_start":
                # Save previous block if any
                if current_block is not None:
                    if current_block.type == "text":
                        current_block.text = current_text
                    elif current_block.type == "thinking":
                        current_block.thinking = current_thinking
                        current_block.signature = current_signature
                    content_blocks.append(current_block)

                # Start new block
                block_data = event.content_block
                block_type = getattr(block_data, "type", "text")
                current_block = SimpleNamespace(type=block_type)
                current_text = ""
                current_thinking = ""
                current_signature = ""

                # Copy relevant attributes
                if block_type == "text":
                    current_text = getattr(block_data, "text", "")
                elif block_type == "thinking":
                    current_thinking = getattr(block_data, "thinking", "")
                elif block_type == "redacted_thinking":
                    current_block.data = getattr(block_data, "data", "")
                elif block_type == "server_tool_use":
                    current_block.name = getattr(block_data, "name", "")
                    current_block.id = getattr(block_data, "id", "")
                    current_block.input = {}
                    current_text = ""  # Accumulate input JSON chunks (same as tool_use)
                    if current_block.name == "web_search":
                        search_count += 1
                elif block_type == "web_search_tool_result":
                    # D-195: Capture web_search_tool_result attributes for manual
                    # fallback (used when get_final_message() fails). The content
                    # is delivered complete in content_block_start, not via deltas.
                    current_block.tool_use_id = getattr(block_data, "tool_use_id", "")
                    current_block.content = getattr(block_data, "content", [])
                elif block_type == "tool_use":
                    # S73 D-160: Client-side tool_use blocks (perplexity, grok)
                    current_block.name = getattr(block_data, "name", "")
                    current_block.id = getattr(block_data, "id", "")
                    current_block.input = {}
                    current_text = ""  # Reuse to accumulate input JSON chunks

            elif event_type == "content_block_delta":
                delta = event.delta
                delta_type = getattr(delta, "type", "")
                if delta_type == "text_delta":
                    chunk = getattr(delta, "text", "")
                    current_text += chunk
                    if show_progress:
                        if thinking_start is not None and total_chars == 0:
                            elapsed = time.time() - thinking_start
                            print(f"\r  ✅ Thinking complete ({elapsed:.0f}s, {thinking_chars:,} chars)          ")
                            thinking_start = None
                        total_chars += len(chunk)
                        if total_chars - last_progress_chars >= 2000:
                            print(f"\r  ⏳ Generating... {total_chars:,} chars   ", end="", flush=True)
                            last_progress_chars = total_chars
                elif delta_type == "thinking_delta":
                    chunk = getattr(delta, "thinking", "")
                    current_thinking += chunk
                    thinking_chars += len(chunk)
                    if show_progress:
                        now = time.time()
                        if thinking_start is None:
                            thinking_start = now
                        elapsed = now - thinking_start
                        if elapsed - last_heartbeat >= 1:
                            # Blink: alternate between showing and hiding the brain
                            blink_on = int(elapsed) % 2 == 0
                            if blink_on:
                                print(f"\r  🧠 Thinking... {elapsed:.0f}s ({thinking_chars:,} chars)   ", end="", flush=True)
                            else:
                                print(f"\r     Thinking... {elapsed:.0f}s ({thinking_chars:,} chars)   ", end="", flush=True)
                            last_heartbeat = elapsed
                elif delta_type == "signature_delta":
                    current_signature += getattr(delta, "signature", "")
                elif delta_type == "input_json_delta":
                    # S73 D-160: Accumulate streamed JSON for tool_use input
                    chunk = getattr(delta, "partial_json", "")
                    current_text += chunk

            elif event_type == "content_block_stop":
                if current_block is not None:
                    if current_block.type == "text":
                        current_block.text = current_text
                    elif current_block.type == "thinking":
                        current_block.thinking = current_thinking
                        current_block.signature = current_signature
                    elif current_block.type == "tool_use":
                        # S73 D-160: Parse accumulated JSON into the input dict
                        if current_text:
                            try:
                                current_block.input = json.loads(current_text)
                            except json.JSONDecodeError:
                                current_block.input = {}
                    elif current_block.type == "server_tool_use":
                        # S80 D-183: Parse accumulated JSON into input dict (same as tool_use)
                        if current_text:
                            try:
                                current_block.input = json.loads(current_text)
                            except json.JSONDecodeError:
                                current_block.input = {}
                    content_blocks.append(current_block)
                    current_block = None
                    current_text = ""
                    current_thinking = ""
                    current_signature = ""

            elif event_type == "message_delta":
                stop_reason = getattr(event.delta, "stop_reason", None)
                out_usage = getattr(event, "usage", None)
                if out_usage:
                    usage_output = getattr(out_usage, "output_tokens", usage_output)
                    cr = getattr(out_usage, "cache_read_input_tokens", None)
                    cw = getattr(out_usage, "cache_creation_input_tokens", None)
                    if cr is not None:
                        usage_cache_read = cr
                    if cw is not None:
                        usage_cache_write = cw

            elif event_type == "message_start":
                msg = getattr(event, "message", None)
                if msg:
                    msg_usage = getattr(msg, "usage", None)
                    if msg_usage:
                        usage_input = getattr(msg_usage, "input_tokens", 0)
                        usage_cache_read = getattr(msg_usage, "cache_read_input_tokens", 0) or 0
                        usage_cache_write = getattr(msg_usage, "cache_creation_input_tokens", 0) or 0

        # S80 D-184: Use SDK's accumulated message for byte-perfect block objects.
        # Our manual streaming parser (SimpleNamespace) loses subtle attributes
        # (caller, citations) and can corrupt thinking block signatures on replay.
        # get_final_message() returns proper SDK objects with model_dump().
        try:
            final_msg = stream.get_final_message()
            content_blocks = list(final_msg.content)
            current_block = None  # S84: Prevent stale manual block from being appended
        except Exception as _final_err:
            # Fall back to manually parsed content_blocks
            print(f"  ⚠ get_final_message() fallback: {type(_final_err).__name__}: {str(_final_err)[:120]}")

    # Catch any remaining block (only relevant if get_final_message() failed)
    if current_block is not None:
        if current_block.type == "text":
            current_block.text = current_text
        elif current_block.type == "thinking":
            current_block.thinking = current_thinking
            current_block.signature = current_signature
        elif current_block.type == "tool_use":
            if current_text:
                try:
                    current_block.input = json.loads(current_text)
                except json.JSONDecodeError:
                    current_block.input = {}
        content_blocks.append(current_block)

    if show_progress and total_chars > 0:
        print(f"\r  ✅ Generated {total_chars:,} chars                ")

    return {
        "content": content_blocks,
        "usage": {
            "input_tokens": usage_input,
            "output_tokens": usage_output,
            "cache_creation_input_tokens": usage_cache_write,
            "cache_read_input_tokens": usage_cache_read,
        },
        "stop_reason": stop_reason,
        "search_count": search_count,
        "thinking_chars": thinking_chars,
    }


def call_api(
    model: str,
    system: str,
    messages: list,
    max_tokens: int,
    tools=None,
    show_progress=True,
    cache_system=False,
    enable_thinking=True,
    thinking_effort=None,
    context_management=None,
) -> dict:
    """
    Call the Anthropic Messages API using streaming with retry.

    S73 additions:
      - context_management: dict of context editing config (3c)
      - Automatic retry with exponential backoff for transient errors (3d)

    S76 D-168 step 2:
      - thinking_effort: Override auto-selected effort level. If None, Opus
        defaults to "max" and other models to "high". Pass explicitly to
        override (e.g., "high" for Opus synthesis).

    Args:
        cache_system: If True, enable prompt caching on system + last user message.
        enable_thinking: If True, enable adaptive thinking. Disable for Founder.
        thinking_effort: Override effort level ("max", "high", "low"). None = auto.
        context_management: If provided, enables context-management-2025-06-27 beta.
                            Automatically clears old tool results and thinking blocks.

    Returns dict with content, usage, stop_reason, search_count, thinking_chars.
    """
    try:
        import anthropic
    except ImportError:
        print("❌ anthropic package not installed. Run: pip install anthropic --break-system-packages")
        sys.exit(1)

    import httpx

    # S84: Singleton client — reuse across all API calls for connection pooling.
    # S73: Extended timeout for Opus synthesis — default httpx timeout (~60s) is
    # too short for effort:max thinking (38s+) followed by 85KB+ text generation.
    # 10 minutes covers worst-case Opus synthesis with extended thinking.
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(
            timeout=httpx.Timeout(600.0, connect=30.0),
        )
    client = _anthropic_client

    # S75 D-168 step 1: 1M beta header RE-ADDED for isolation testing.
    # The script without this header produced 110KB Phase 1 deliverable.
    # This test determines if the 1M header alone changes synthesis behavior.
    # If Phase 1 still produces >=40KB, header is not the problem.
    # If it drops to 1.5-2KB, header confirmed as root cause.
    beta_headers = []
    if "haiku" not in model:
        beta_headers.append("context-1m-2025-08-07")
    if context_management:
        beta_headers.append("context-management-2025-06-27")
    extra_headers = {"anthropic-beta": ",".join(beta_headers)} if beta_headers else {}

    # Prompt caching setup
    if cache_system and system:
        system_content = [
            {
                "type": "text",
                "text": system,
                "cache_control": {"type": "ephemeral"},
            }
        ]
        messages = prepare_messages_for_cache(messages)
    else:
        system_content = system

    kwargs = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system_content,
        "messages": messages,
        "extra_headers": extra_headers,
    }

    # Adaptive thinking config
    # S76 D-168 step 2: thinking_effort override allows per-call control.
    # Default: Opus=max, others=high. Override for synthesis isolation testing.
    if enable_thinking and "haiku" not in model:
        kwargs["thinking"] = {"type": "adaptive"}
        if thinking_effort:
            kwargs["output_config"] = {"effort": thinking_effort}
        elif "opus" in model:
            kwargs["output_config"] = {"effort": "max"}
        else:
            kwargs["output_config"] = {"effort": "high"}
    if tools:
        kwargs["tools"] = tools
    # S73 3c: Context editing — automatic clearing of old tool results/thinking
    # Must be passed via extra_body since the SDK doesn't have a native parameter yet
    if context_management:
        kwargs["extra_body"] = {"context_management": context_management}

    # S73 3d: Retry with exponential backoff for transient errors
    # S77 D-178: Overloaded (529) gets dedicated longer retry loop
    call_start = time.time()  # D-194 3C: Per-call timing
    last_error = None
    for attempt in range(1, API_MAX_RETRIES + 1):
        try:
            result = _execute_stream(client, kwargs, show_progress)
            result["call_elapsed_seconds"] = round(time.time() - call_start, 2)
            result["retry_count"] = attempt - 1
            return result
        except Exception as e:
            last_error = e
            is_retryable = False
            is_overloaded = False

            # S77 D-178: Overloaded errors (529) — dedicated retry with longer window
            if isinstance(e, anthropic.APIStatusError) and getattr(e, "status_code", 0) == 529:
                is_retryable = True
                is_overloaded = True
            # Anthropic SDK error types
            elif isinstance(e, anthropic.RateLimitError):
                is_retryable = True
            elif isinstance(e, anthropic.InternalServerError):
                is_retryable = True
            elif isinstance(e, anthropic.APIStatusError) and getattr(e, "status_code", 0) in (502, 503):
                is_retryable = True
            elif isinstance(e, getattr(anthropic, "APITimeoutError", type(None))):
                is_retryable = True
            elif isinstance(e, getattr(anthropic, "APIConnectionError", type(None))):
                is_retryable = True
            # Python built-in network errors
            elif isinstance(e, (TimeoutError, ConnectionError, OSError)):
                is_retryable = True
            # S73: httpx/httpcore timeouts — not subclasses of Python's TimeoutError.
            # These surface when the read operation times out mid-stream (e.g., Opus
            # thinking for 38s then generating 85KB+, exceeding httpx default timeout).
            elif "Timeout" in type(e).__name__ or "ReadTimeout" in type(e).__name__:
                is_retryable = True

            # S77 D-178: Overloaded gets its own retry loop — break out of standard loop
            if is_overloaded:
                total_waited = 0
                overloaded_attempt = 1
                while total_waited < API_OVERLOADED_MAX_WAIT:
                    print(f"\n  ⚠ API overloaded (attempt {overloaded_attempt}, "
                          f"waited {total_waited}s/{API_OVERLOADED_MAX_WAIT}s): "
                          f"{type(e).__name__}: {str(e)[:120]}")
                    print(f"  ⏳ Retrying in {API_OVERLOADED_RETRY_DELAY}s...")
                    time.sleep(API_OVERLOADED_RETRY_DELAY)
                    total_waited += API_OVERLOADED_RETRY_DELAY
                    overloaded_attempt += 1
                    try:
                        result = _execute_stream(client, kwargs, show_progress)
                        result["call_elapsed_seconds"] = round(time.time() - call_start, 2)
                        result["retry_count"] = attempt - 1 + overloaded_attempt
                        return result
                    except anthropic.APIStatusError as oe:
                        if getattr(oe, "status_code", 0) == 529:
                            last_error = oe
                            continue  # Still overloaded, keep waiting
                        else:
                            raise  # Different error, don't swallow it
                    except Exception:
                        raise  # Non-overloaded error, don't swallow it
                # Exhausted overloaded retry window
                print(f"\n  ❌ API still overloaded after {total_waited}s. Giving up.")
                raise last_error

            if is_retryable and attempt < API_MAX_RETRIES:
                delay = API_RETRY_BASE_DELAY * (2 ** (attempt - 1))
                print(f"\n  ⚠ API error (attempt {attempt}/{API_MAX_RETRIES}): "
                      f"{type(e).__name__}: {str(e)[:120]}")
                print(f"  ⏳ Retrying in {delay}s...")
                time.sleep(delay)
                continue
            else:
                raise  # Non-retryable or exhausted retries

    # Should not reach here, but just in case
    raise last_error


def extract_text(content_blocks) -> str:
    """Extract text from API response content blocks."""
    parts = []
    for block in content_blocks:
        if getattr(block, "type", "") == "text":
            parts.append(block.text)
    return "\n".join(parts)


def strip_synthesis_preamble(text: str) -> str:
    """
    Strip AI 'thinking out loud' preamble from synthesis output.

    The synthesis model often starts with lines like "I'll now proceed with..."
    or "I need to verify..." before the actual deliverable content. The real
    deliverable always begins with a markdown heading (# or ##).

    This strips everything before the first markdown heading.
    """
    match = re.search(r'^#{1,3}\s', text, re.MULTILINE)
    if match:
        stripped = text[match.start():]
        preamble_len = match.start()
        if preamble_len > 0:
            print(f"  🧹 Stripped {preamble_len:,} chars of synthesis preamble")
        return stripped
    return text


def content_to_dict_list(content_blocks) -> list:
    """Convert content blocks to serializable dicts for message history.
    
    Whitelist approach: preserves thinking, redacted_thinking, text, and 
    tool_use blocks. Strips server_tool_use (web search server-side blocks
    that can't be replayed).
    
    Thinking blocks MUST be preserved unmodified for the API to maintain
    the model's reasoning flow across turns. Opus 4.6 preserves prior-turn
    thinking by default, but the last assistant turn's blocks must be passed
    back complete.
    
    NOTE: For tool continuation (where this message will be the LATEST
    assistant message in the next API call), use serialize_for_replay()
    instead — it preserves ALL blocks without filtering to satisfy the
    API's thinking block signature verification.
    """
    result = []
    for block in content_blocks:
        block_type = getattr(block, "type", "text")
        if block_type == "thinking":
            thinking = getattr(block, "thinking", "")
            signature = getattr(block, "signature", "")
            if thinking or signature:
                result.append({
                    "type": "thinking",
                    "thinking": thinking,
                    "signature": signature,
                })
        elif block_type == "redacted_thinking":
            data = getattr(block, "data", "")
            if data:
                result.append({
                    "type": "redacted_thinking",
                    "data": data,
                })
        elif block_type == "text":
            text = getattr(block, "text", "")
            if text.strip():  # Only include non-empty text
                result.append({"type": "text", "text": text})
        elif block_type == "tool_use":
            # Preserve client-side tool_use blocks (not server_tool_use)
            result.append({
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}),
            })
        # server_tool_use blocks are intentionally stripped — they're
        # server-side web search internals that can't be replayed
    # API requires at least one content block
    if not result:
        result.append({"type": "text", "text": "(no text response)"})
    return result


def serialize_for_replay(content_blocks) -> list:
    """Serialize content blocks faithfully for tool continuation replay.

    S78 D-180: Unlike content_to_dict_list(), this function preserves EVERY
    block without filtering — no skipping empty text, no dropping thinking
    blocks, no stripping server_tool_use. This is critical when the resulting
    assistant message will be the LATEST in the next API call, because the API
    verifies thinking block signatures byte-for-byte.

    S80 D-184: Now uses SDK model_dump() when available for byte-perfect
    serialization. Manual SimpleNamespace fallback preserved for edge cases.

    Use this ONLY for the tool continuation case in call_guide_with_research().
    For older messages (where context editing clears thinking anyway), use
    content_to_dict_list() which is more compact.
    """
    result = []
    # D-195: Block types to skip entirely during replay. Server-side tool blocks
    # (web_search) are auto-handled by the API and must NOT be replayed — the API
    # rejects them with "tool use without result" because it can't match the
    # model_dump() serialization back to valid input format. Stripping both
    # server_tool_use and web_search_tool_result eliminates the pairing requirement.
    _SKIP_BLOCK_TYPES = {"server_tool_use", "web_search_tool_result"}
    for block in content_blocks:
        block_type = getattr(block, "type", "text")
        if block_type in _SKIP_BLOCK_TYPES:
            continue
        # S80 D-184: SDK objects have model_dump() — use it for byte-perfect replay
        if hasattr(block, "model_dump"):
            # D-195: exclude_none=True strips all null optional fields that the
            # API rejects on input replay. Also pop output-only SDK fields.
            dumped = block.model_dump(exclude_none=True)
            for _strip_key in ("parsed_output", "caller", "citations"):
                dumped.pop(_strip_key, None)
            result.append(dumped)
            continue
        # Fallback: manual serialization for SimpleNamespace or dict objects
        block_type = getattr(block, "type", "text")
        if block_type == "thinking":
            result.append({
                "type": "thinking",
                "thinking": getattr(block, "thinking", ""),
                "signature": getattr(block, "signature", ""),
            })
        elif block_type == "redacted_thinking":
            result.append({
                "type": "redacted_thinking",
                "data": getattr(block, "data", ""),
            })
        elif block_type == "text":
            result.append({
                "type": "text",
                "text": getattr(block, "text", ""),
            })
        elif block_type == "tool_use":
            result.append({
                "type": "tool_use",
                "id": getattr(block, "id", ""),
                "name": getattr(block, "name", ""),
                "input": getattr(block, "input", {}),
            })
        # NOTE: server_tool_use and web_search_tool_result are skipped at the
        # top of the loop via _SKIP_BLOCK_TYPES — they never reach here.
        else:
            # Unknown block type — preserve as-is to avoid losing data
            entry = {"type": block_type}
            for attr in ("text", "thinking", "signature", "data", "id", "name",
                         "input", "tool_use_id", "content"):
                val = getattr(block, attr, None)
                if val is not None:
                    entry[attr] = val
            result.append(entry)
    # API requires at least one content block
    if not result:
        result.append({"type": "text", "text": "(no text response)"})
    return result


def prepare_messages_for_cache(messages: list) -> list:
    """
    Prepare messages for prompt caching by adding cache_control to only the
    last user message. This keeps us within the 4 cache_control limit
    (1 system + 1 last user = 2 total).

    The cache prefix includes everything up to and including the last cached
    block, so caching only the final user message still caches the entire
    conversation history preceding it.

    Returns a deep copy with cache_control applied — does not modify originals.
    """
    if not messages:
        return messages

    # Deep copy to avoid modifying the stored message history
    prepared = copy.deepcopy(messages)

    # Find the last user message and add cache_control
    for i in range(len(prepared) - 1, -1, -1):
        if prepared[i].get("role") == "user":
            content = prepared[i].get("content")
            if isinstance(content, str):
                # Convert string content to block format with cache_control
                # S76: Skip cache_control if content is empty (API rejects it)
                if content.strip():
                    prepared[i]["content"] = [
                        {
                            "type": "text",
                            "text": content,
                            "cache_control": {"type": "ephemeral"},
                        }
                    ]
            elif isinstance(content, list):
                # Add cache_control to the last non-empty text block
                # S76: API rejects cache_control on empty text blocks (400 error)
                for j in range(len(content) - 1, -1, -1):
                    if (isinstance(content[j], dict)
                            and content[j].get("type") == "text"
                            and content[j].get("text", "").strip()):
                        content[j]["cache_control"] = {"type": "ephemeral"}
                        break
            break

    return prepared


# ---------------------------------------------------------------------------
# Cost tracking
# ---------------------------------------------------------------------------

class CostTracker:
    """Track API costs across the entire run."""

    def __init__(self):
        self._lock = threading.Lock()  # D-194: Thread-safe for parallel review
        self.phases = {}
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_cache_read = 0
        self.total_cache_write = 0
        self.total_searches = 0
        self.total_thinking_chars = 0  # S71 3.5: Thinking volume observability
        self.total_external_cost = 0.0  # D-185: Perplexity/Grok API costs
        self.total_cost = 0.0

    def record_call(self, phase: str, role: str, model: str, usage: dict, search_count: int, thinking_chars: int = 0):
        """Record a single API call. Thread-safe (D-194)."""
        with self._lock:
            if phase not in self.phases:
                self.phases[phase] = {
                    "calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "cache_read": 0, "cache_write": 0, "searches": 0,
                    "thinking_chars": 0, "cost": 0.0,
                }

            p = self.phases[phase]
            p["calls"] += 1

            inp = usage["input_tokens"]
            out = usage["output_tokens"]
            cr = usage["cache_read_input_tokens"]
            cw = usage["cache_creation_input_tokens"]

            p["input_tokens"] += inp
            p["output_tokens"] += out
            p["cache_read"] += cr
            p["cache_write"] += cw
            p["searches"] += search_count
            p["thinking_chars"] += thinking_chars

            # Calculate cost — use long-context rates when total input > 200K
            prices = PRICING.get(model, PRICING["claude-opus-4-6"])
            total_input_tokens = inp + cr + cw
            is_long_context = total_input_tokens > 200_000

            if is_long_context:
                cost = (
                    (inp / 1_000_000) * prices.get("input_long", prices["input"])
                    + (out / 1_000_000) * prices.get("output_long", prices["output"])
                    + (cr / 1_000_000) * prices.get("cache_read_long", prices.get("cache_read", 0))
                    + (cw / 1_000_000) * prices.get("cache_write_long", prices.get("cache_write", 0))
                    + search_count * PRICING["web_search_per_query"]
                )
            else:
                cost = (
                    (inp / 1_000_000) * prices["input"]
                    + (out / 1_000_000) * prices["output"]
                    + (cr / 1_000_000) * prices.get("cache_read", 0)
                    + (cw / 1_000_000) * prices.get("cache_write", 0)
                    + search_count * PRICING["web_search_per_query"]
                )
            p["cost"] += cost

            self.total_input_tokens += inp
            self.total_output_tokens += out
            self.total_cache_read += cr
            self.total_cache_write += cw
            self.total_searches += search_count
            self.total_thinking_chars += thinking_chars
            self.total_cost += cost

    def record_external_call(self, phase: str, engine: str, estimated_cost: float):
        """D-185: Record a Perplexity/Grok API call with estimated cost. Thread-safe (D-194)."""
        with self._lock:
            if phase not in self.phases:
                self.phases[phase] = {
                    "calls": 0, "input_tokens": 0, "output_tokens": 0,
                    "cache_read": 0, "cache_write": 0, "searches": 0,
                    "thinking_chars": 0, "cost": 0.0,
                }
            p = self.phases[phase]
            p["cost"] += estimated_cost
            p.setdefault("external_calls", {})[engine] = p.get("external_calls", {}).get(engine, 0) + 1
            self.total_external_cost += estimated_cost
            self.total_cost += estimated_cost

    def print_phase_summary(self, phase: str):
        """Print cost summary for a phase."""
        p = self.phases.get(phase, {})
        print(f"\n  📊 Phase {phase} costs:")
        print(f"     API calls: {p.get('calls', 0)}")
        print(f"     Input tokens: {p.get('input_tokens', 0):,}")
        print(f"     Output tokens: {p.get('output_tokens', 0):,}")
        print(f"     Thinking chars: {p.get('thinking_chars', 0):,}")
        print(f"     Cache read: {p.get('cache_read', 0):,}")
        print(f"     Cache write: {p.get('cache_write', 0):,}")
        print(f"     Web searches: {p.get('searches', 0)}")
        ext = p.get("external_calls", {})
        if ext:
            print(f"     External research: {ext}")
        print(f"     Phase cost: ${p.get('cost', 0):.2f}")
        print(f"     Running total: ${self.total_cost:.2f}")

    def save_report(self):
        """Save full cost report to file."""
        report = {
            "timestamp": datetime.now().isoformat(),
            "total": {
                "input_tokens": self.total_input_tokens,
                "output_tokens": self.total_output_tokens,
                "cache_read_tokens": self.total_cache_read,
                "cache_write_tokens": self.total_cache_write,
                "web_searches": self.total_searches,
                "thinking_chars": self.total_thinking_chars,
                "external_cost_usd": round(self.total_external_cost, 2),
                "total_cost_usd": round(self.total_cost, 2),
            },
            "phases": self.phases,
        }
        # S80 Fix 12: Save timestamped copy to prevent overwrite on restart
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = METRICS_DIR / f"cost-report-{timestamp}.json"
        archive_path.write_text(json.dumps(report, indent=2))
        # Also write latest for convenience (overwrites — archive has history)
        latest_path = METRICS_DIR / "cost-report.json"
        latest_path.write_text(json.dumps(report, indent=2))
        print(f"\n💰 Cost report saved: {archive_path}")
        print(f"   (also copied to {latest_path})")
        print(f"   Total cost: ${self.total_cost:.2f}")


# ---------------------------------------------------------------------------
# Conversation loop
# ---------------------------------------------------------------------------

def run_conversation(
    phase_key,
    master_prompt: str,
    phase_template: str,
    persona: str,
    prior_deliverables: str,
    max_exchanges: int,
    cost_tracker: CostTracker,
    research_caps: dict = None,
) -> list[dict]:
    """
    Run the conversation loop for one phase.

    Returns the full conversation as a list of {role, speaker, text} dicts.
    """
    if research_caps is None:
        research_caps = {"web_search": True, "perplexity": False, "grok": False}

    phase_label = f"Phase {phase_key}"
    print(f"\n{'='*60}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] 🗣  {phase_label} — CONVERSATION")
    print(f"{'='*60}")

    # Build system prompts
    guide_system = (
        GUIDE_PREAMBLE
        + master_prompt
        + "\n\n---\n\n"
        + phase_template
    )

    if prior_deliverables:
        guide_system += (
            "\n\n---\n\n<prior_deliverables>\n"
            + prior_deliverables
            + "\n</prior_deliverables>"
        )

    # S71 F3: Founder Memory — give the Founder context about prior decisions
    founder_system = persona
    if prior_deliverables:
        founder_memory = generate_founder_memory(prior_deliverables, phase_key, cost_tracker)
        if founder_memory:
            founder_system += (
                "\n\n---\n\n<founder_memory>\n"
                "The following is a summary of decisions YOU (the founder) made in prior phases. "
                "Stay consistent with these decisions. Reference them naturally when relevant.\n\n"
                + founder_memory
                + "\n</founder_memory>"
            )

    # S71 3.7: Build tools array based on available research engines
    guide_tools = build_guide_tools(research_caps)
    has_research_tools = research_caps.get("perplexity") or research_caps.get("grok")
    if has_research_tools:
        tool_names = [t.get("name", t.get("type", "?")) for t in guide_tools]
        print(f"  🔬 Research tools: {', '.join(tool_names)}")

    # Conversation state
    guide_messages = []    # Messages for guide API calls
    founder_messages = []  # Messages for founder API calls
    transcript = []        # Full conversation log

    # S71 F8: Phase-aware opening — context-specific instead of generic
    opening_message = PHASE_OPENINGS.get(
        phase_key,
        "Hello! I'm here to plan my platform. Let's get started."
    )

    # Guide opens the conversation
    # When research tools are available, use the tool execution loop
    print(f"\n  Guide: [opening phase {phase_key}...]")
    opening_messages = [{"role": "user", "content": opening_message}]

    if has_research_tools:
        guide_response, opening_research = call_guide_with_research(
            system=guide_system,
            messages=opening_messages,
            tools=guide_tools,
            cost_tracker=cost_tracker,
            phase_key=phase_key,
        )
    else:
        guide_response = call_api(
            model=GUIDE_MODEL,
            system=guide_system,
            messages=opening_messages,
            max_tokens=MAX_GUIDE_TOKENS,
            tools=guide_tools,
            cache_system=True,
            context_management=GUIDE_CONTEXT_MANAGEMENT,
        )
        cost_tracker.record_call(str(phase_key), "guide", GUIDE_MODEL, guide_response["usage"], guide_response["search_count"], guide_response["thinking_chars"])
        opening_research = ""

    guide_text = extract_text(guide_response["content"])
    # S76: Guard against empty text when Guide response has only tool_use blocks
    if not guide_text.strip():
        guide_text = "[The guide is processing research results and will continue the conversation.]"
    print(f"  Guide: {guide_text[:200]}...")

    # Initialize message histories
    # If research tools were used, opening_messages already contains the full
    # tool exchange (user → assistant+tool_use → tool_result → assistant).
    # Otherwise, build manually.
    if has_research_tools:
        # opening_messages was modified in-place by call_guide_with_research.
        # Ensure final assistant response is included.
        guide_messages = list(opening_messages)
        if guide_messages[-1].get("role") != "assistant":
            guide_messages.append({"role": "assistant", "content": content_to_dict_list(guide_response["content"])})
    else:
        guide_messages = [
            {"role": "user", "content": opening_message},
            {"role": "assistant", "content": content_to_dict_list(guide_response["content"])},
        ]
    founder_messages = [
        {"role": "user", "content": guide_text},
    ]
    # S72: Include research data in transcript for synthesis
    transcript_entry = {"role": "guide", "text": guide_text}
    if opening_research:
        transcript_entry["research"] = opening_research
    transcript.append(transcript_entry)

    # D-185: Incremental transcript save path — prevents total data loss on mid-conversation crash.
    # A crash at exchange 30/40 previously lost all 30 exchanges ($3-5 of API cost).
    # Now saves every 5 exchanges. Final save at loop end replaces the partial file.
    partial_conv_path = CONVERSATIONS_DIR / f"phase-{phase_key}-conversation-partial.json"

    # Conversation loop
    guide_signaled_ready = False
    for exchange in range(1, max_exchanges + 1):
        # --- Founder responds ---
        # S71 3.4: Thinking disabled for Founder — conversational role doesn't
        # benefit from extended reasoning, saves output token budget
        print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] [P{phase_key} · {exchange}/{max_exchanges}] Founder responding...")
        founder_response = call_api(
            model=FOUNDER_MODEL,
            system=founder_system,
            messages=founder_messages,
            max_tokens=MAX_FOUNDER_TOKENS,
            cache_system=True,
            enable_thinking=False,
        )
        cost_tracker.record_call(str(phase_key), "founder", FOUNDER_MODEL, founder_response["usage"], 0, 0)

        founder_text = extract_text(founder_response["content"])
        print(f"  Founder: {founder_text[:200]}...")

        transcript.append({"role": "founder", "text": founder_text})

        # Update founder message history
        founder_messages.append({"role": "assistant", "content": content_to_dict_list(founder_response["content"])})

        # Check for founder completion marker
        if FOUNDER_COMPLETE_MARKER in founder_text:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] ✅ Founder confirmed phase complete at exchange {exchange}")
            break

        # --- Guide responds ---
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] [P{phase_key} · {exchange}/{max_exchanges}] Guide responding...")
        guide_messages.append({"role": "user", "content": founder_text})

        if has_research_tools:
            guide_response, loop_research = call_guide_with_research(
                system=guide_system,
                messages=guide_messages,
                tools=guide_tools,
                cost_tracker=cost_tracker,
                phase_key=phase_key,
            )
        else:
            guide_response = call_api(
                model=GUIDE_MODEL,
                system=guide_system,
                messages=guide_messages,
                max_tokens=MAX_GUIDE_TOKENS,
                tools=guide_tools,
                cache_system=True,
                context_management=GUIDE_CONTEXT_MANAGEMENT,
            )
            cost_tracker.record_call(str(phase_key), "guide", GUIDE_MODEL, guide_response["usage"], guide_response["search_count"], guide_response["thinking_chars"])
            loop_research = ""

        guide_text = extract_text(guide_response["content"])
        # S76: Guard against empty text when Guide response has only tool_use blocks
        # (happens when max_tool_rounds is hit and Guide never generated text)
        if not guide_text.strip():
            guide_text = "[The guide is processing research results and will continue the conversation.]"
        print(f"  Guide: {guide_text[:200]}...")

        # S72: Include research data in transcript for synthesis
        guide_entry = {"role": "guide", "text": guide_text}
        if loop_research:
            guide_entry["research"] = loop_research
        transcript.append(guide_entry)

        # Update message histories
        guide_messages.append({"role": "assistant", "content": content_to_dict_list(guide_response["content"])})
        founder_messages.append({"role": "user", "content": guide_text})

        # D-185: Incremental save every 5 exchanges to prevent crash data loss
        if exchange % 5 == 0:
            partial_conv_path.write_text(json.dumps(transcript, indent=2))

        # Check for guide completion marker
        if GUIDE_COMPLETE_MARKER in guide_text:
            guide_signaled_ready = True
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] 🔔 Guide ready for synthesis at exchange {exchange}")
            # Give founder one more turn to confirm
            continue

    else:
        if not guide_signaled_ready:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] ⚠ Hit max exchanges ({max_exchanges}) for {phase_label}")

    # Save conversation transcript (replaces partial file)
    conv_path = CONVERSATIONS_DIR / f"phase-{phase_key}-conversation.json"
    conv_path.write_text(json.dumps(transcript, indent=2))
    # Clean up partial file now that final save succeeded
    if partial_conv_path.exists():
        partial_conv_path.unlink()

    # Also save as readable markdown
    md_path = CONVERSATIONS_DIR / f"phase-{phase_key}-conversation.md"
    md_lines = [f"# {phase_label} — Conversation Transcript\n\n"]
    md_lines.append(f"**Exchanges:** {len([t for t in transcript if t['role'] == 'founder'])}\n")
    md_lines.append(f"**Timestamp:** {datetime.now().isoformat()}\n\n---\n\n")
    for entry in transcript:
        speaker = "**🧭 Guide:**" if entry["role"] == "guide" else "**🏌️ Founder (Rafa):**"
        md_lines.append(f"{speaker}\n\n{entry['text']}\n\n")
        # S84: Include research data in human-readable transcript
        if entry.get("research"):
            md_lines.append(f"*📚 Research data:*\n\n{entry['research']}\n\n")
        md_lines.append("---\n\n")
    md_path.write_text("".join(md_lines))

    print(f"\n  💾 Conversation saved: {conv_path}")
    print(f"  💾 Readable transcript: {md_path}")

    return transcript


# ---------------------------------------------------------------------------
# Synthesis / deliverable generation
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# SYNTHESIS — Convert phase conversation into deliverable document
# ---------------------------------------------------------------------------

def run_synthesis(
    phase_key,
    master_prompt: str,  # S74 D-167: Restored — used in synthesis system prompt
    synthesis_template: str,
    conversation_transcript: list[dict],
    prior_deliverables: str,
    cost_tracker: CostTracker,
    retry_feedback: str = "",  # S72: Critic feedback from failed attempt
    distilled_brief: str = None,  # S73 3e: Pre-distilled transcript brief
) -> str:
    """
    Generate deliverables from a completed phase conversation.

    S72 Architecture: System prompt is focused (preamble + template only).
    S73 3e: If distilled_brief is provided, uses it instead of raw transcript
    for focused signal. Raw transcript available as fallback.

    Returns the deliverable text.
    """
    phase_label = f"Phase {phase_key}"
    print(f"\n{'='*60}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] 📄 {phase_label} — SYNTHESIS")
    print(f"{'='*60}")

    # S74 D-167: Distillation SKIPPED — always use raw transcript.
    # S73 D-163 distillation compressed 77K→10K (87%), but the model treated
    # summary-sized input as a summarization task. Early working versions
    # fed full raw transcripts and produced 93-110KB deliverables.
    # Distillation to be re-evaluated incrementally per D-168.
    #
    # S72: Build conversation text WITH research data for synthesis context
    conv_parts = []
    for e in conversation_transcript:
        speaker = "Guide" if e["role"] == "guide" else "Founder"
        text = f"{speaker}: {e['text']}"
        if e.get("research"):
            text += f"\n\n[Research data from this exchange:]\n{e['research']}"
        conv_parts.append(text)
    conv_text = "\n\n".join(conv_parts)
    print(f"  📋 Using raw transcript ({len(conv_text):,} chars)")

    # S74 D-167: master_prompt RESTORED in synthesis system prompt.
    # S72 removed it claiming signal dilution, but the early working versions
    # (S67-S68) included it and produced 93-110KB deliverables. The master
    # prompt provides methodology context that helps the model understand it's
    # generating a complete specification document, not a summary.
    # To be re-evaluated incrementally per D-168.
    synth_system = (
        SYNTHESIS_PREAMBLE
        + master_prompt
        + "\n\n---\n\n"
        + "<synthesis_template>\n"
        + synthesis_template
        + "\n</synthesis_template>"
    )

    # S72: User message — longform data at top, instructions at end
    # (per Anthropic's long-context guidance: queries at end improve quality ~30%)
    synth_message_parts = []

    # 1. Prior deliverables at top (longform reference data)
    if prior_deliverables:
        synth_message_parts.append(
            "<prior_deliverables>\n"
            + prior_deliverables
            + "\n</prior_deliverables>"
        )

    # 2. Conversation transcript with research data (the raw material)
    synth_message_parts.append(
        "<completed_conversation>\n"
        + conv_text
        + "\n</completed_conversation>"
    )

    # 3. Explicit generation command at the end (highest attention position)
    generation_command = (
        "The phase conversation above is complete. "
        "Generate the COMPLETE deliverable document as specified in the synthesis template "
        "in your system prompt. Produce every section with full substantive content — "
        "not a summary, not an index, not a table of contents. The actual document. "
        "Begin directly with the markdown heading. Do not include any preamble."
    )

    # S72: Append critic feedback for retry attempts
    if retry_feedback:
        generation_command += retry_feedback
        print(f"  📝 Retry feedback appended ({len(retry_feedback):,} chars)")

    synth_message_parts.append(generation_command)

    synth_message = "\n\n".join(synth_message_parts)

    print(f"  Synthesis system: ~{len(synth_system):,} chars")
    print(f"  Synthesis message: ~{len(synth_message):,} chars")
    print(f"  Generating deliverable...")

    # S74 D-167: Thinking DISABLED for synthesis.
    # Regression analysis (synthesis-regression-analysis.md) found that
    # effort:max thinking caused 34K chars of planning followed by a 1.5KB
    # summary instead of the actual 40-110KB deliverable. Early working
    # versions (S67-S68) had no thinking and produced complete deliverables
    # on first attempt. To be re-evaluated incrementally per D-168.
    # S75 D-170: web_search REMOVED from synthesis — not in S67-S68 working baseline.
    # S72 added it for "fact-checking" but it's an uncontrolled variable that
    # may shift the model from generation mode to research mode. Synthesis should
    # generate from the transcript, not search the web. Re-evaluate per D-168.
    synth_response = call_api(
        model=SYNTHESIS_MODEL,
        system=synth_system,
        messages=[{"role": "user", "content": synth_message}],
        max_tokens=MAX_SYNTHESIS_TOKENS,
        show_progress=True,
        cache_system=True,
        enable_thinking=True,  # S76 D-168 step 2: Re-enabled at effort:high (not max)
        thinking_effort="high",  # max caused 34K planning + 1.5KB output; high is the test
    )
    cost_tracker.record_call(str(phase_key), "synthesis", SYNTHESIS_MODEL, synth_response["usage"], synth_response["search_count"], synth_response["thinking_chars"])

    deliverable_text = extract_text(synth_response["content"])

    # Check for truncation
    if synth_response["stop_reason"] == "max_tokens":
        print(f"  ⚠ Deliverable was truncated (hit {MAX_SYNTHESIS_TOKENS} token limit)")
        print(f"  Attempting continuation...")

        # Continuation: ask Claude to continue from where it left off
        # Preserve thinking blocks from the original response for reasoning continuity
        continuation_messages = [
            {"role": "user", "content": synth_message},
            {"role": "assistant", "content": content_to_dict_list(synth_response["content"])},
            {"role": "user", "content": "Your output was truncated. Please continue EXACTLY where you left off. Do not repeat any content — pick up from the last incomplete sentence or section."},
        ]

        for attempt in range(1, 4):  # Up to 3 continuations
            print(f"  Continuation attempt {attempt}/3...")
            cont_response = call_api(
                model=SYNTHESIS_MODEL,
                system=synth_system,
                messages=continuation_messages,
                max_tokens=MAX_SYNTHESIS_TOKENS,
                show_progress=True,
                cache_system=True,
                enable_thinking=True,  # S76 D-168 step 2: Match main synthesis call
                thinking_effort="high",
            )
            cost_tracker.record_call(str(phase_key), "synthesis-cont", SYNTHESIS_MODEL, cont_response["usage"], 0, cont_response["thinking_chars"])

            cont_text = extract_text(cont_response["content"])
            deliverable_text += "\n" + cont_text

            if cont_response["stop_reason"] != "max_tokens":
                print(f"  ✅ Continuation complete after {attempt} attempt(s)")
                break

            continuation_messages.append({"role": "assistant", "content": content_to_dict_list(cont_response["content"])})
            continuation_messages.append({"role": "user", "content": "Continue from where you left off."})
        else:
            print(f"  ⚠ Deliverable still incomplete after 3 continuations")

    # Strip synthesis preamble (AI thinking-out-loud before actual deliverable)
    deliverable_text = strip_synthesis_preamble(deliverable_text)

    # Save deliverable
    deliv_path = DELIVERABLES_DIR / f"phase-{phase_key}-deliverable.md"
    deliv_path.write_text(deliverable_text)
    print(f"\n  💾 Deliverable saved: {deliv_path}")
    print(f"  📏 Size: {len(deliverable_text):,} chars ({len(deliverable_text)/1024:.1f} KB)")

    return deliverable_text


# ---------------------------------------------------------------------------
# Phase execution
# ---------------------------------------------------------------------------

def get_synthesis_template(phase_key, phase_template_content):
    """
    For Phase 1, fetch the separate synthesis template.
    For other phases, the synthesis instructions are embedded in the combined template.
    """
    if phase_key == 1:
        return load_template(PHASE_TEMPLATES[1]["synthesis"])
    else:
        # For combined templates, the same template contains both conversation
        # and synthesis instructions. We pass the full template.
        return phase_template_content


# ---------------------------------------------------------------------------
# Prior Deliverable Loading (D-152: 1M context, full text, attention-optimized)
# ---------------------------------------------------------------------------

# Navigation preambles — help the model focus attention within large contexts.
# Each entry describes what the deliverable contains and what downstream phases
# typically need from it. These are attention anchors, NOT filters.
PHASE_PREAMBLES = {
    1: (
        "PLATFORM VISION — Contains: platform name, market positioning, target audience, "
        "competitive landscape, founder background, core value proposition, business model, "
        "revenue strategy, key differentiators, and initial scope boundaries. "
        "Key references for downstream: platform identity, market context, pricing approach, "
        "competitive gaps to exploit."
    ),
    2: (
        "USER ROLES & PERSONAS — Contains: all user roles with permissions and capabilities, "
        "detailed personas, user journey maps, onboarding flows, pain points, and success metrics. "
        "Key references for downstream: role names and IDs, permission matrices, journey stages, "
        "user-facing terminology."
    ),
    3: (
        "FEATURES & PRIORITIES — Contains: complete feature registry with IDs, descriptions, "
        "priority rankings (P0-P3), user role assignments, acceptance criteria, and feature "
        "dependencies. Key references for downstream: feature IDs, MVP vs future scope, "
        "feature-to-role mappings, interaction requirements."
    ),
    4: (
        "DATA MODEL & ARCHITECTURE — Contains: all entities with fields, types, relationships, "
        "constraints, indexes, validation rules, and data flow diagrams. "
        "Key references for downstream: entity names, field specifications, relationship cardinality, "
        "data validation rules, storage requirements."
    ),
    5: (
        "TECHNICAL ARCHITECTURE — Contains: technology stack selections with rationale, "
        "infrastructure topology, API endpoint specifications, integration patterns, "
        "authentication/authorization design, third-party service selections, and performance targets. "
        "Key references for downstream: tech stack decisions, API contracts, vendor selections, "
        "architecture constraints, security model."
    ),
    "6a": (
        "DESIGN FOUNDATION — Contains: design system (colors, typography, spacing, component library), "
        "brand identity, accessibility standards, responsive breakpoints, and design tokens. "
        "Key references for downstream: design token values, component specifications, "
        "accessibility requirements, visual language."
    ),
    "6b": (
        "PAGE ARCHITECTURE — Contains: page inventory, wireframe specifications, navigation structure, "
        "layout patterns, content hierarchy, and URL structure. "
        "Key references for downstream: page names and routes, navigation model, "
        "layout templates, content zones."
    ),
    "6c": (
        "INTERACTION SYNTHESIS — Contains: interaction patterns, state transitions, animation specs, "
        "error handling UX, loading states, micro-interactions, and cross-page flows. "
        "Key references for downstream: interaction IDs, state machine definitions, "
        "error message catalog, UX flow sequences."
    ),
    7: (
        "BUILD PLANNING — Contains: implementation roadmap, sprint/phase breakdown, "
        "dependency graph, MVP scope definition, resource estimates, and risk mitigations. "
        "Key references for downstream: build sequence, MVP feature set, "
        "dependency order, milestone definitions."
    ),
    8: (
        "LIFECYCLE & OPERATIONS — Contains: deployment strategy, CI/CD pipeline, monitoring/alerting, "
        "scaling triggers, backup/recovery, support workflows, and maintenance procedures. "
        "Key references for downstream: infrastructure requirements, operational constraints, "
        "SLA targets, incident response procedures."
    ),
    9: (
        "REVIEW & VALIDATION — Contains: cross-phase consistency audit, gap analysis, "
        "requirement traceability, risk assessment, and methodology feedback observations. "
        "Key references for downstream: identified gaps, unresolved issues, "
        "cross-reference verification results."
    ),
    10: (
        "GITHUB PUSH & HANDOFF — Contains: final deliverable package manifest, "
        "repository structure, handoff documentation, and implementation notes. "
        "Key references for downstream: package inventory, delivery format."
    ),
}


# S71 F8: Phase-aware conversation openings replace the generic
# "Hello! I'm here to plan my platform. Let's get started."
# Each opening references where the founder is in the journey so the Guide
# has warm, contextualized start material.
PHASE_OPENINGS = {
    1: (
        "Hello! I'm here to plan my software platform. I'm excited to start "
        "from the very beginning — let's define the vision and strategy."
    ),
    2: (
        "We've finished defining the platform vision and strategy. Now I'd like "
        "to work on the user roles and personas — who will actually use this platform."
    ),
    3: (
        "We've mapped out the vision and user roles. Now I'm ready to define "
        "the features and prioritize what gets built first."
    ),
    4: (
        "The vision, users, and features are all defined. Let's work on the data "
        "model — the entities, relationships, and structure behind the scenes."
    ),
    5: (
        "We've completed vision, users, features, and data modeling. Now let's "
        "tackle the technical architecture — the technology stack and infrastructure."
    ),
    "6a": (
        "The core technical planning is done. Let's move into design — starting "
        "with the design foundation: colors, typography, and the component system."
    ),
    "6b": (
        "The design foundation is set. Now let's define the page architecture — "
        "every page, its layout, navigation, and content structure."
    ),
    "6c": (
        "Design foundation and page architecture are done. Let's bring it all "
        "together with the interaction patterns and UX flows."
    ),
    7: (
        "All the design and technical planning is complete. Let's build the "
        "implementation roadmap — what gets built when, and in what order."
    ),
    8: (
        "The build plan is ready. Now let's define how this platform will run "
        "in production — deployment, monitoring, operations, and maintenance."
    ),
    9: (
        "We've been through the entire planning process. Let's do a comprehensive "
        "review — cross-checking everything for consistency and completeness."
    ),
    10: (
        "The review is complete. Let's finalize everything and prepare the "
        "deliverable package for handoff to the development team."
    ),
}


def generate_founder_memory(prior_deliverables: str, phase_key, cost_tracker: CostTracker) -> str:
    """
    S73 Hidden Debt Fix: Incremental Founder Memory assembly.

    BEFORE: Processed ALL prior deliverables through Sonnet every phase.
    Token scaling was O(n²) — by Phase 10, ~200K+ Sonnet input tokens to
    generate a ~3K char summary 95% identical to Phase 9's version.

    NOW: Reads persistent founder-memory.md from disk. After each synthesis,
    generates only the delta for that phase and appends it. Cost drops from
    O(n²) to O(n) with near-zero marginal cost per phase.

    The memory file is managed by update_founder_memory_after_synthesis(),
    called at the end of run_phase.
    """
    if not prior_deliverables:
        return ""

    # S73: Read incremental memory file if it exists
    memory_file = DELIVERABLES_DIR / "founder-memory.md"
    if memory_file.exists():
        memory_text = memory_file.read_text(encoding="utf-8")
        print(f"  🧠 Founder Memory loaded from file: {len(memory_text):,} chars")
        return memory_text

    # Fallback for first phase or missing file: generate from scratch
    phase_label = f"Phase {phase_key}"
    print(f"  🧠 Generating initial Founder Memory for {phase_label}...")

    memory_prompt = (
        "You are helping prepare context for a founder who is about to enter "
        f"{phase_label} of their platform planning process. Below are the deliverables "
        "from all prior phases.\n\n"
        "Generate a concise FOUNDER MEMORY — a summary of the key decisions, names, "
        "choices, and commitments the founder made in prior phases. This will be "
        "injected into the founder's context so they can stay consistent.\n\n"
        "Requirements:\n"
        "- 2000-3000 characters maximum\n"
        "- Focus on DECISIONS and NAMES: platform name, target users, key features, "
        "technology choices, pricing model, design decisions — anything the founder "
        "would need to remember to stay consistent\n"
        "- Use bullet points grouped by phase for easy scanning\n"
        "- Include specific names, IDs, and values — not vague summaries\n"
        "- Write in second person ('You decided...', 'Your platform...')\n\n"
        "<prior_deliverables>\n"
        + prior_deliverables
        + "\n</prior_deliverables>"
    )

    memory_response = call_api(
        model=UTILITY_MODEL,
        system="You are a concise technical summarizer. Output ONLY the founder memory, no preamble.",
        messages=[{"role": "user", "content": memory_prompt}],
        max_tokens=4096,
        enable_thinking=False,
    )
    cost_tracker.record_call(str(phase_key), "founder-memory", UTILITY_MODEL, memory_response["usage"], 0, 0)

    memory_text = extract_text(memory_response["content"])
    print(f"  🧠 Founder Memory generated: {len(memory_text):,} chars")

    # Save initial memory to file
    memory_file.write_text(memory_text, encoding="utf-8")
    print(f"  💾 Founder Memory saved to {memory_file}")

    return memory_text


def update_founder_memory_after_synthesis(
    deliverable_text: str,
    phase_key,
    cost_tracker: CostTracker,
) -> None:
    """
    S73 Hidden Debt Fix: Generate memory delta for just-completed phase
    and append to persistent founder-memory.md.

    Called at the end of each successful phase. Uses Sonnet to extract
    ~500 chars of decisions from the new deliverable, then appends.
    Near-zero marginal cost per phase vs. the old O(n²) approach.
    """
    phase_label = f"Phase {phase_key}"
    memory_file = DELIVERABLES_DIR / "founder-memory.md"

    print(f"  🧠 Generating Founder Memory delta for {phase_label}...")

    delta_prompt = (
        f"A founder just completed {phase_label} of their platform planning. "
        f"Below is the deliverable produced for this phase.\n\n"
        "Generate a CONCISE MEMORY DELTA — a bullet-point summary of ONLY the new "
        "decisions, names, choices, and commitments made in THIS phase.\n\n"
        "Requirements:\n"
        "- 300-600 characters maximum\n"
        f"- Start with: '### {phase_label}'\n"
        "- Focus on decisions and specific names/values\n"
        "- Write in second person ('You decided...')\n"
        "- Do NOT repeat anything from prior phases\n\n"
        f"<deliverable>\n{deliverable_text[:50000]}\n</deliverable>"
    )

    delta_response = call_api(
        model=UTILITY_MODEL,
        system="You are a concise summarizer. Output ONLY the memory delta, no preamble.",
        messages=[{"role": "user", "content": delta_prompt}],
        max_tokens=1024,
        enable_thinking=False,
        show_progress=False,
    )
    cost_tracker.record_call(str(phase_key), "founder-memory-delta", UTILITY_MODEL, delta_response["usage"], 0, 0)

    delta_text = extract_text(delta_response["content"])

    # Append to file
    existing = ""
    if memory_file.exists():
        existing = memory_file.read_text(encoding="utf-8")

    updated = existing + "\n\n" + delta_text if existing else delta_text
    memory_file.write_text(updated, encoding="utf-8")
    print(f"  🧠 Founder Memory updated: +{len(delta_text):,} chars → {len(updated):,} total")


# ---------------------------------------------------------------------------
# S71 3.1: Master prompt adaptation for orchestrator mode
# ---------------------------------------------------------------------------

ORCHESTRATOR_RESEARCH_SECTION_WEBSEARCH_ONLY = """<research_architecture>
**Orchestrator Research Mode — Web Search Only**

In this automated orchestrator environment, you have ONE research tool: `web_search`.
It is a general-purpose internet search engine. You do NOT have access to Perplexity Sonar,
Perplexity Deep Research, or Grok (X Search). Those engines are referenced in the production
methodology but are not available in this simulation.

**How to maximize web_search effectiveness:**
- You can use up to 3 web searches per response. Use all 3 when research matters.
- For service comparisons: search each candidate separately ("Supabase pricing 2026",
  "PlanetScale pricing 2026") rather than one combined query.
- For competitive analysis: search for each competitor individually.
- For technology recommendations: search for "[tool] reviews 2026" and "[tool] alternatives".
- You CANNOT do real-time developer sentiment analysis. When the methodology calls for a
  "sentiment check" or "Grok check", note this as a research gap in the deliverable:
  "⚠ SENTIMENT CHECK UNAVAILABLE: Developer sentiment for [tool] could not be verified via
  real-time social media search. Recommend manual verification before committing."

**What must ALWAYS be live research (never training knowledge):**
- Pricing for any service, tool, or API — prices change constantly
- Competitive landscape — new competitors launch, existing ones pivot or die
- Library and framework versions — what's current, what's deprecated
- Regulatory requirements — laws and standards get updated

**What CAN use training knowledge:**
- Architectural patterns, general UX best practices, fundamental security principles
- Software design patterns that are stable over years

**Staleness thresholds still apply.** When any phase loads data from a prior phase's
deliverable, check the research date against these limits: pricing (30d), competitive (60d),
library versions (90d), regulatory (180d). If stale, re-verify with web_search.

**Stale recommendation protocol** still applies — see methodology instructions for full details.
When live research reveals a prior phase recommendation has materially changed, present the
change to the founder and follow the update protocol.
</research_architecture>"""

ORCHESTRATOR_RESEARCH_SECTION_FULL = """<research_architecture>
**Orchestrator Research Mode — Full Research Stack**

You have access to multiple research tools in this orchestrator environment:

**web_search** (server-side, always available) — General-purpose internet search. Fast,
up to 3 queries per response. Good for quick factual lookups, pricing checks, and targeted
queries. This is your default for simple research needs.

**perplexity_search** (client-side tool) — Grounded search with citations via Perplexity
Sonar API. Use for: market sizing, industry trends, regulatory requirements, integration
ecosystems, multi-source comparisons, and any factual question where you need current data
with source attribution. Returns cited answers. Available models:
- "sonar" (default): Fast general-purpose search. Use for straightforward queries.
- "sonar-pro": Deep multi-source synthesis. Use for service comparisons, competitive analysis,
  and complex questions requiring multiple sources.

**grok_sentiment** (client-side tool) — Developer/community sentiment analysis via Grok (xAI)
with real-time X/Twitter data access. Use for: what developers, users, and the tech community
are saying about a specific tool, service, competitor, or technology. Catches things no other
engine can: recent outages, community backlash, migrations, excitement about new launches.
Use as a community health check before recommending any technology or service.

**Engine selection rules:**
- Quick factual lookup, single source → web_search
- Factual question needing citations → perplexity_search (sonar)
- Multi-source comparison or synthesis → perplexity_search (sonar-pro)
- Community sentiment, recent events, developer reactions → grok_sentiment
- Service or technology recommendation → perplexity_search for the comparison, then
  grok_sentiment for the sentiment check. Always both.

**What must ALWAYS be live research (never training knowledge):**
- Pricing for any service, tool, or API — prices change constantly
- Competitive landscape — new competitors launch, existing ones pivot or die
- Library and framework versions — what's current, what's deprecated
- Regulatory requirements — laws and standards get updated
- Community sentiment — a tool beloved last year may be in crisis today

**What CAN use training knowledge:**
- Architectural patterns, general UX best practices, fundamental security principles
- Software design patterns that are stable over years

When in doubt, research it live. Stale data that the founder trusts is more dangerous than
a knowledge gap that's clearly labeled.

**Staleness thresholds apply.** Pricing (30d), competitive (60d), library versions (90d),
regulatory (180d), community sentiment (45d). When a phase references data from a prior
phase, check the research date against these thresholds before relying on it.

**Synthesis reconciliation protocol.** When perplexity_search and grok_sentiment return
complementary but divergent signals, produce a unified assessment: "Factual comparison favors
X (Perplexity). Developer sentiment is mixed (Grok: [summary]). Recommendation: [decision
with reasoning]." Never silently discard one engine's findings.

**Stale recommendation protocol** still applies — see methodology instructions for full details.
</research_architecture>"""

ORCHESTRATOR_HARD_BOUNDARY_9_WEBSEARCH = (
    "9. **Flag when sentiment checks are unavailable.** Before recommending any third-party "
    "tool, service, or technology, attempt to verify current developer sentiment via web search. "
    "If web search results are insufficient for a sentiment assessment, explicitly flag this "
    "in the deliverable as a gap requiring manual verification."
)

ORCHESTRATOR_HARD_BOUNDARY_9_FULL = (
    "9. **Never recommend a service without a sentiment check.** Before recommending any "
    "third-party tool, service, or technology to the founder, use the grok_sentiment tool to "
    "check current developer sentiment. A tool with great documentation but a community in "
    "revolt is not a safe recommendation. The founder is trusting you with their technology "
    "stack — verify that trust is warranted."
)


def adapt_master_prompt_for_orchestrator(master_prompt: str, research_caps: dict) -> str:
    """
    S71 3.1: Replace the multi-engine research architecture section with
    orchestrator-appropriate guidance based on available research engines.

    If Perplexity + Grok keys are available, the Guide gets the full research
    section describing all available tools. Otherwise, falls back to
    web_search-only guidance.
    """

    original_len = len(master_prompt)

    has_full_research = research_caps.get("perplexity") or research_caps.get("grok")

    if has_full_research:
        research_section = ORCHESTRATOR_RESEARCH_SECTION_FULL
        hard_boundary_9 = ORCHESTRATOR_HARD_BOUNDARY_9_FULL
    else:
        research_section = ORCHESTRATOR_RESEARCH_SECTION_WEBSEARCH_ONLY
        hard_boundary_9 = ORCHESTRATOR_HARD_BOUNDARY_9_WEBSEARCH

    # Replace <research_architecture>...</research_architecture>
    adapted = re.sub(
        r'<research_architecture>.*?</research_architecture>',
        research_section,
        master_prompt,
        flags=re.DOTALL,
    )

    # Replace hard boundary #9 (Grok-specific)
    adapted = re.sub(
        r'9\.\s+\*\*Never recommend a service without a sentiment check\.\*\*.*?(?=\n</hard_boundaries>)',
        hard_boundary_9,
        adapted,
        flags=re.DOTALL,
    )

    new_len = len(adapted)
    delta = original_len - new_len
    mode = "full research stack" if has_full_research else "web_search only"
    print(f"  🔧 Master prompt adapted for orchestrator ({mode}, {delta:+,} chars)")
    return adapted


# ---------------------------------------------------------------------------
# S71 3.7: Research proxy — Perplexity + Grok APIs
# ---------------------------------------------------------------------------

PERPLEXITY_MODELS = {
    "sonar": "sonar",               # Fast general-purpose search
    "sonar-pro": "sonar-pro",       # Deep multi-source synthesis
    "deep-research": "sonar-deep-research",  # Exhaustive report-level
}


def call_perplexity(query: str, model: str = "sonar", api_key: str = None) -> dict:
    """
    Call the Perplexity Sonar API for grounded, cited research.

    Requires PERPLEXITY_API_KEY environment variable.
    Returns dict with 'text' (answer) and 'citations' (list of URLs).
    Returns None if API key not available or call fails.
    """
    key = api_key or os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return None

    pplx_model = PERPLEXITY_MODELS.get(model, model)
    payload = json.dumps({
        "model": pplx_model,
        "messages": [{"role": "user", "content": query}],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.perplexity.ai/chat/completions",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        for attempt in range(2):
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    choice = data.get("choices", [{}])[0]
                    message = choice.get("message", {})
                    content = message.get("content", "")
                    # S84: Guard against empty-but-successful responses
                    if not content.strip():
                        print(f"  ⚠ Perplexity returned empty content")
                        return None
                    return {
                        "text": content,
                        "citations": data.get("citations", []),
                        "model": pplx_model,
                    }
            except Exception as e:
                if attempt == 0:
                    print(f"  ⚠ Perplexity attempt 1 failed ({e}), retrying in 3s...")
                    time.sleep(3)
                else:
                    raise
    except Exception as e:
        print(f"  ⚠ Perplexity API error: {e}")
        return None


# S82: Switched from Legacy Chat Completions to Responses API with x_search + web_search.
# The old /v1/chat/completions endpoint had NO access to real-time X/Twitter data —
# xAI docs: "No access to realtime events without search tools enabled."
# This was the root cause of every Grok "no results" failure across Phases 2-5.
def call_grok(query: str, api_key: str = None) -> dict:
    """
    Call the Grok (xAI) Responses API for sentiment analysis with live X/Twitter search.

    Requires GROK_API_KEY environment variable.
    Uses grok-4-1-fast-reasoning with x_search + web_search server-side tools.
    Grok autonomously searches X and the web before generating its analysis.
    Returns dict with 'text' (analysis) or None on failure.
    """
    key = api_key or os.environ.get("GROK_API_KEY")
    if not key:
        return None

    payload = json.dumps({
        "model": "grok-4-1-fast-reasoning",
        "input": [
            {
                "role": "system",
                "content": (
                    "You are a developer sentiment analyst with access to real-time X/Twitter "
                    "and web search. Use your x_search and web_search tools to find current "
                    "developer discussions, then analyze sentiment. Focus on: recent incidents "
                    "(outages, security issues, pricing changes), community mood (positive/"
                    "negative/mixed), migration trends (are developers moving to or from this "
                    "tool), and any red flags. Be concise — 3-5 sentences max. Always cite "
                    "what you found from X posts or web sources."
                ),
            },
            {"role": "user", "content": query},
        ],
        "tools": [
            {"type": "x_search"},
            {"type": "web_search"},
        ],
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.x.ai/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "PlatformForge/1.0",
        },
        method="POST",
    )

    for attempt in range(2):
        try:
            # Longer timeout — Grok may execute multiple search queries autonomously
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode("utf-8"))

                # Extract text from the Responses API output format.
                # The output is an array of items; text lives in message content blocks.
                text_parts = []
                for item in data.get("output", []):
                    # Direct text content in output items
                    if item.get("type") == "message":
                        for block in item.get("content", []):
                            if block.get("type") == "output_text":
                                text_parts.append(block.get("text", ""))
                            elif block.get("type") == "text":
                                text_parts.append(block.get("text", ""))
                    # Some response formats put text directly
                    elif item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                    # Handle content array at top level
                    elif "content" in item and isinstance(item["content"], str):
                        text_parts.append(item["content"])

                # Fallback: check top-level fields
                if not text_parts:
                    if "output_text" in data:
                        text_parts.append(data["output_text"])
                    elif "choices" in data:
                        # Shouldn't happen with Responses API but handle gracefully
                        choice = data["choices"][0] if data["choices"] else {}
                        msg = choice.get("message", {})
                        text_parts.append(msg.get("content", ""))

                result_text = "\n".join(text_parts).strip()
                if not result_text:
                    print(f"  ⚠ Grok returned empty response. Raw keys: {list(data.keys())}")
                    return None

                return {
                    "text": result_text,
                    "model": "grok-4-1-fast-reasoning",
                }
        except urllib.error.HTTPError as e:
            # S76: Capture response body for debugging (especially 403s)
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            if attempt == 0 and e.code >= 500:
                print(f"  ⚠ Grok attempt 1 failed (HTTP {e.code}), retrying in 3s...")
                time.sleep(3)
                continue
            print(f"  ⚠ Grok API error: HTTP Error {e.code}: {e.reason}")
            if body:
                print(f"    Response body: {body[:500]}")
            return None
        except Exception as e:
            if attempt == 0:
                print(f"  ⚠ Grok attempt 1 failed ({e}), retrying in 3s...")
                time.sleep(3)
                continue
            print(f"  ⚠ Grok API error: {e}")
            return None
    return None


# Client-side tool definitions — these get added to the Guide's tools array
# alongside the server-side web_search tool
RESEARCH_TOOL_SCHEMAS = [
    {
        "name": "perplexity_search",
        "description": (
            "Search using Perplexity Sonar for grounded, cited research answers. "
            "Best for: market sizing, industry trends, service comparisons, pricing lookups, "
            "regulatory requirements, and factual questions needing current data with citations. "
            "Use model 'sonar' for quick lookups, 'sonar-pro' for deep multi-source synthesis."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The research question to answer",
                },
                "model": {
                    "type": "string",
                    "enum": ["sonar", "sonar-pro"],
                    "description": "sonar for quick queries, sonar-pro for deep comparisons",
                    "default": "sonar",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "grok_sentiment",
        "description": (
            "Check developer and community sentiment about a tool, service, or technology "
            "using Grok's real-time X/Twitter data access. Use before recommending any "
            "third-party service. Returns: recent incidents, community mood, migration trends, "
            "and red flags."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The tool, service, or technology to check sentiment for (e.g., 'Supabase developer sentiment 2026')",
                },
            },
            "required": ["query"],
        },
    },
]


def execute_research_tool(tool_name: str, tool_input: dict,
                          cost_tracker: CostTracker = None, phase_key=None) -> str:
    """
    Execute a client-side research tool and return the result as text.

    D-185: Now accepts cost_tracker + phase_key to record external API costs.
    Returns a formatted string suitable for a tool_result content block.
    """
    if tool_name == "perplexity_search":
        query = tool_input.get("query", "")
        model = tool_input.get("model", "sonar")
        print(f"    🔬 Perplexity ({model}): {query[:80]}...")
        result = call_perplexity(query, model=model)
        if result:
            # D-185: Track Perplexity cost (~$5/1K sonar, ~$8/1K sonar-pro)
            if cost_tracker and phase_key is not None:
                est_cost = 0.008 if model == "sonar-pro" else 0.005
                cost_tracker.record_external_call(str(phase_key), "perplexity", est_cost)
            text = result["text"]
            citations = result.get("citations", [])
            cite_str = ""
            if citations:
                cite_str = "\n\nSources:\n" + "\n".join(f"- {c}" for c in citations[:5])
            return f"[Perplexity {model}]\n{text}{cite_str}"
        return "[Perplexity search failed — no results returned]"

    elif tool_name == "grok_sentiment":
        query = tool_input.get("query", "")
        print(f"    🐦 Grok sentiment: {query[:80]}...")
        result = call_grok(query)
        if result:
            # D-185: Track Grok cost (~$5/1K queries estimated)
            if cost_tracker and phase_key is not None:
                cost_tracker.record_external_call(str(phase_key), "grok", 0.005)
            return f"[Grok Sentiment Analysis]\n{result['text']}"
        return "[Grok sentiment check failed — no results returned]"

    return f"[Unknown tool: {tool_name}]"


def build_guide_tools(research_caps: dict) -> list:
    """
    Build the tools array for Guide API calls.

    Always includes web_search (server-side). Adds perplexity_search and
    grok_sentiment as client-side tools when their API keys are available.
    """
    # D-194: Haiku only supports web_search_20250305 (no allowed_callers).
    # Newer web_search_20260209 has implicit allowed_callers that Haiku rejects.
    ws_type = "web_search_20250305" if "haiku" in GUIDE_MODEL else "web_search_20260209"
    tools = [{
        "type": ws_type,
        "name": "web_search",
        "max_uses": WEB_SEARCH_MAX_USES,
    }]

    if research_caps.get("perplexity"):
        tools.append(RESEARCH_TOOL_SCHEMAS[0])  # perplexity_search
    if research_caps.get("grok"):
        tools.append(RESEARCH_TOOL_SCHEMAS[1])  # grok_sentiment

    return tools


def call_guide_with_research(
    system: str,
    messages: list,
    tools: list,
    cost_tracker: CostTracker,
    phase_key,
    max_tool_rounds: int = 3,
) -> tuple:
    """
    Call the Guide API with a tool execution loop for client-side research tools.

    When the Guide's response contains tool_use blocks for perplexity_search or
    grok_sentiment, this function:
    1. Executes the tool calls
    2. Appends the assistant response + tool_results to messages
    3. Calls the API again so the Guide can incorporate the results
    4. Repeats up to max_tool_rounds times

    S78 D-180: Tool continuation rounds use serialize_for_replay() instead of
    content_to_dict_list() to preserve ALL content blocks (including empty text,
    server_tool_use, etc.) faithfully. The API verifies thinking block signatures
    byte-for-byte on the latest assistant message — any filtering causes a 400
    error ("thinking blocks cannot be modified").

    Also: context_management is DISABLED during tool continuation rounds to
    avoid any interaction between clear_thinking and the latest assistant
    message's thinking block verification.

    Returns tuple of (final API response, collected research results text).
    Messages list is modified in-place to include the full tool exchange.
    """
    collected_research = []  # S72: Collect research results for synthesis

    for round_num in range(max_tool_rounds + 1):
        # S78 D-180: First call uses full context_management. Tool continuation
        # rounds disable it to avoid clear_thinking interacting with latest
        # assistant message thinking block verification.
        use_context_mgmt = GUIDE_CONTEXT_MANAGEMENT if round_num == 0 else None

        response = call_api(
            model=GUIDE_MODEL,
            system=system,
            messages=messages,
            max_tokens=MAX_GUIDE_TOKENS,
            tools=tools,
            cache_system=True,
            context_management=use_context_mgmt,
        )
        cost_tracker.record_call(
            str(phase_key), "guide", GUIDE_MODEL,
            response["usage"], response["search_count"], response["thinking_chars"]
        )

        # Check for client-side tool_use blocks
        client_tool_uses = []
        for block in response["content"]:
            if getattr(block, "type", "") == "tool_use":
                name = getattr(block, "name", "")
                if name in ("perplexity_search", "grok_sentiment"):
                    client_tool_uses.append(block)

        # If no client-side tool calls, we're done
        if not client_tool_uses:
            return response, "\n\n".join(collected_research)

        if round_num >= max_tool_rounds:
            print(f"    ⚠ Hit max tool rounds ({max_tool_rounds}), returning last response")
            return response, "\n\n".join(collected_research)

        # Execute tools and build continuation
        print(f"    🔧 Guide requested {len(client_tool_uses)} research tool(s) (round {round_num + 1})")

        # S78 D-180: Use serialize_for_replay() — preserves ALL blocks faithfully.
        # This message will be the LATEST assistant message in the next API call,
        # so thinking blocks must pass signature verification byte-for-byte.
        serialized_content = serialize_for_replay(response["content"])
        # D-195: Debug log — show block types to diagnose replay issues
        _block_types = [b.get("type", "?") for b in serialized_content if isinstance(b, dict)]
        print(f"    📦 Serialized {len(serialized_content)} blocks: {_block_types}")
        messages.append({
            "role": "assistant",
            "content": serialized_content,
        })

        # Execute each tool and add results
        tool_results = []
        for tool_block in client_tool_uses:
            tool_id = getattr(tool_block, "id", "")
            tool_name = getattr(tool_block, "name", "")
            tool_input = getattr(tool_block, "input", {})

            result_text = execute_research_tool(tool_name, tool_input,
                                                cost_tracker=cost_tracker, phase_key=phase_key)
            collected_research.append(result_text)  # S72: Capture for synthesis
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_id,
                "content": result_text,
            })

        messages.append({"role": "user", "content": tool_results})

    return response, "\n\n".join(collected_research)


def check_research_capabilities() -> dict:
    """
    Check which research engines are available based on environment variables.
    Returns dict of capabilities for the startup banner.
    """
    caps = {
        "web_search": True,  # Always available via Anthropic API
        "perplexity": bool(os.environ.get("PERPLEXITY_API_KEY")),
        "grok": bool(os.environ.get("GROK_API_KEY")),
    }
    return caps


# ---------------------------------------------------------------------------
# S71 3.2: Post-synthesis deliverable validation
# ---------------------------------------------------------------------------

def validate_deliverable(
    deliverable_text: str,
    phase_key,
    template_text: str,
    cost_tracker: CostTracker,
) -> dict:
    """
    S71 3.2 / S72: Structural validation of a synthesized deliverable.

    Uses Sonnet (cost-efficient) to check:
    - All required sections present per the template
    - Cross-reference manifest is structurally valid
    - No sections suspiciously short (< 200 chars) that should have substance
    - No obvious truncation artifacts

    S72: Extracts a section checklist from the full template instead of
    truncating to 3000 chars (which only showed ~4% of Phase 1's 81KB template).

    Returns dict with:
      - valid: bool
      - issues: list of issue descriptions
      - section_count: int
    """

    phase_label = f"Phase {phase_key}"
    print(f"\n  🔍 Validating {phase_label} deliverable...")

    # S72: Extract section headings and structural requirements from template
    # This gives the validator the FULL picture of what's required, not just 3.7%
    template_headings = re.findall(r'^#{1,4}\s+.+$', template_text, re.MULTILINE)
    # Also extract key output specifications
    output_markers = re.findall(
        r'(?:required|must include|must contain|produce|generate|output).*?(?:\.|$)',
        template_text[:30000],  # Look in the output spec sections
        re.IGNORECASE
    )
    section_checklist = "\n".join(
        [f"- {h.strip()}" for h in template_headings[:50]]
        + [f"- Requirement: {m.strip()[:150]}" for m in output_markers[:20]]
    )

    validation_prompt = (
        f"You are a structural validator for a {phase_label} deliverable document.\n\n"
        "The following is a checklist of sections and requirements extracted from "
        "the phase template. Use this to check the deliverable:\n\n"
        f"<required_sections_and_outputs>\n{section_checklist}\n</required_sections_and_outputs>\n\n"
        "Analyze the deliverable below and check for:\n"
        "1. MISSING SECTIONS: Compare against the required sections above. "
        "List any sections the template requires that are missing from the deliverable.\n"
        "2. MANIFEST VALIDITY: Check if a cross-reference manifest exists at the end. "
        "If present, verify it has valid YAML structure with exports, imports, sections, "
        "references_out, and references_in fields.\n"
        "3. THIN SECTIONS: Any section with a heading but less than 200 characters of content "
        "is suspiciously thin — flag it.\n"
        "4. TRUNCATION: Check if the document ends mid-sentence or mid-section.\n\n"
        "Respond in JSON format ONLY (no markdown, no preamble):\n"
        '{"valid": true/false, "issues": ["issue 1", "issue 2"], '
        '"section_count": N, "has_manifest": true/false, '
        '"thin_sections": ["section name 1"], "truncated": true/false}\n\n'
        # S73 3b: Full deliverable — 1M context makes 80K truncation unnecessary
        f"<deliverable>\n{deliverable_text}\n</deliverable>"
    )

    val_response = call_api(
        model=UTILITY_MODEL,  # Sonnet — cost-efficient for structural checks
        system="You are a document structure validator. Output ONLY valid JSON, no preamble or markdown.",
        messages=[{"role": "user", "content": validation_prompt}],
        max_tokens=MAX_VALIDATION_TOKENS,
        enable_thinking=False,
    )
    cost_tracker.record_call(str(phase_key), "validation", UTILITY_MODEL, val_response["usage"], 0, 0)

    val_text = extract_text(val_response["content"]).strip()

    # Parse JSON response
    try:
        # Strip markdown fences if present
        clean = val_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
    except json.JSONDecodeError:
        # S73 3a: Fail-safe — unparseable validation = not validated
        print(f"  ⚠ Validation response not valid JSON, treating as FAIL (fail-safe)")
        result = {"valid": False, "issues": ["Validation response unparseable — treating as failed"], "section_count": 0}

    # Report results
    if result.get("valid"):
        print(f"  ✅ Validation passed — {result.get('section_count', '?')} sections, "
              f"manifest: {'yes' if result.get('has_manifest') else 'no'}")
    else:
        issues = result.get("issues", [])
        print(f"  ⚠ Validation found {len(issues)} issue(s):")
        for issue in issues[:5]:
            print(f"     - {issue}")

    return result



# D-188: critic_review_deliverable() REMOVED — replaced by 4-layer review pipeline


def load_prior_deliverables(current_phase_key, cost_tracker=None) -> str:
    """
    Load deliverables from ALL prior phases as context for the current phase.

    D-152: With 1M context window active, every prior deliverable is loaded
    in full text. Zero information loss. No extraction. No budget limits.

    D-195: For Haiku (200K context window), apply a character budget to avoid
    exceeding the context limit. Most recent deliverables get priority (loaded
    in full); older deliverables are truncated to fit the budget.

    Attention optimization:
    - Each deliverable gets a navigation preamble (what it contains, what to look for)
    - Deliverables ordered with most recent LAST (recency-priority positioning)
    - Most recent phase is closest to the conversation, getting strongest attention
    """
    # D-195: Context budget for Haiku. With 200K tokens (~600K chars at ~3
    # chars/token for structured text), reserve space for system prompt (~50K),
    # template (~80K worst case), founder memory (~15K), tools+overhead (~120K),
    # conversation (~100K). Prior deliverables budget: 200K chars.
    # Phase 10 crashed at 300K — total request exceeded 200K tokens.
    # For 1M-context models, no budget (effectively unlimited).
    is_haiku = "haiku" in GUIDE_MODEL
    max_prior_chars = 200_000 if is_haiku else 0  # 0 = unlimited

    prior_phases = []
    for pk in PHASE_ORDER:
        if pk == current_phase_key:
            break
        prior_phases.append(pk)

    if not prior_phases:
        return ""

    # Load all deliverable files from disk, in chronological order
    # (most recent will be last = closest to conversation = strongest attention)
    parts = []
    for pk in prior_phases:
        deliv_path = DELIVERABLES_DIR / f"phase-{pk}-deliverable.md"
        if deliv_path.exists():
            content = deliv_path.read_text()
            preamble = PHASE_PREAMBLES.get(pk, "")
            header = f"## Phase {pk} Deliverable ({len(content):,} chars)"
            if preamble:
                header += f"\n**NAVIGATION:** {preamble}"
            parts.append(f"{header}\n\n{content}")
        else:
            print(f"  ⚠ Missing deliverable for Phase {pk} — skipped from prior context")

    if not parts:
        return ""

    total_chars = sum(len(p) for p in parts)

    # D-195: Apply context budget for Haiku — truncate oldest deliverables first
    if max_prior_chars > 0 and total_chars > max_prior_chars:
        print(f"  ⚠ Prior deliverables ({total_chars:,} chars) exceed Haiku budget "
              f"({max_prior_chars:,} chars) — truncating oldest first")
        # Keep most recent deliverables in full, truncate oldest
        budget_remaining = max_prior_chars
        # Work backwards (most recent first) to allocate budget
        keep_full = []
        for part in reversed(parts):
            if budget_remaining >= len(part):
                keep_full.append(part)
                budget_remaining -= len(part)
            else:
                # Truncate this deliverable to fit remaining budget
                if budget_remaining > 500:  # Only include if meaningful content fits
                    truncated = part[:budget_remaining - 100]
                    truncated += f"\n\n... [TRUNCATED — {len(part) - len(truncated):,} chars omitted to fit Haiku context window]"
                    keep_full.append(truncated)
                    budget_remaining = 0
                else:
                    print(f"  ⚠ Dropping oldest deliverable ({len(part):,} chars) — no budget remaining")
                break  # No more budget
        parts = list(reversed(keep_full))
        total_chars = sum(len(p) for p in parts)
        print(f"  📦 Loaded {len(parts)} prior deliverables: {total_chars:,} chars "
              f"(budget-fitted for Haiku 200K context)")
    else:
        print(f"  📦 Loaded {len(parts)} prior deliverables: {total_chars:,} chars "
              f"(ALL full text, attention-optimized — {'Haiku 200K' if is_haiku else '1M'} context)")

    return "\n\n---\n\n".join(parts)



# ---------------------------------------------------------------------------
# D-188: 4-LAYER EXPERT REVIEW PIPELINE
#
# Replaces critic_review_deliverable() + run_recalibration() with a
# structured, sequential review pipeline:
#   L1 (Compliance) → L2 (Domain Expert) → L3 (Downstream Consumer) →
#   L4 (Founder Comprehension) → Should-Improve Consolidation →
#   Founder Re-engagement → Targeted Update → Final L1 Re-check
#
# All layers use REVIEW_MODEL (single variable for graduated escalation).
# Persona files loaded from personas/ directory at startup.
# ---------------------------------------------------------------------------


def load_review_personas() -> dict:
    """
    Load all persona files at startup. Returns nested dict indexed by layer and phase_key.

    Structure:
      {
        "l2": {1: {role, expertise, focus, concerns}, 2: {...}, ...},
        "l3": {1: {role, consumes_for, focus, needs}, 2: {...}, ...},
        "l4": {role, background, criteria},
        "config": <raw text of review-config.md>
      }
    """
    personas_dir = Path(__file__).parent / "personas"

    result = {"l2": {}, "l3": {}, "l4": {}, "config": ""}

    # Parse L2 domain experts
    l2_path = personas_dir / "l2-domain-experts.md"
    if l2_path.exists():
        l2_text = l2_path.read_text(encoding="utf-8")
        result["l2"] = _parse_persona_file(l2_text, "l2")
        print(f"  📋 L2 personas loaded: {len(result['l2'])} phases")

    # Parse L3 downstream consumers
    l3_path = personas_dir / "l3-downstream-consumers.md"
    if l3_path.exists():
        l3_text = l3_path.read_text(encoding="utf-8")
        result["l3"] = _parse_persona_file(l3_text, "l3")
        print(f"  📋 L3 personas loaded: {len(result['l3'])} phases")

    # Load L4 (single universal persona — not per-phase)
    l4_path = personas_dir / "l4-founder-comprehension.md"
    if l4_path.exists():
        result["l4"] = l4_path.read_text(encoding="utf-8")
        print(f"  📋 L4 persona loaded: founder comprehension reviewer")

    # Load review config
    config_path = personas_dir / "review-config.md"
    if config_path.exists():
        result["config"] = config_path.read_text(encoding="utf-8")

    return result


def _parse_persona_file(text: str, layer: str) -> dict:
    """
    Parse a persona markdown file into a dict indexed by phase key.

    Expects ## Phase N headings followed by bullet points with **Key:** Value format.
    Returns {phase_key: raw_section_text} for prompt assembly at review time.
    """
    personas = {}
    current_phase = None
    current_lines = []

    for line in text.split("\n"):
        # Match phase headers: "## Phase 1", "## Phase 6a", etc.
        phase_match = re.match(r'^## Phase (\w+)', line)
        if phase_match:
            # Save previous phase
            if current_phase is not None:
                personas[current_phase] = "\n".join(current_lines).strip()
            phase_id = phase_match.group(1)
            # Convert numeric strings to int for consistency with PHASE_ORDER
            if phase_id.isdigit():
                current_phase = int(phase_id)
            else:
                current_phase = phase_id
            current_lines = []
        elif current_phase is not None:
            current_lines.append(line)

    # Save last phase
    if current_phase is not None:
        personas[current_phase] = "\n".join(current_lines).strip()

    return personas


def run_l1_compliance(
    deliverable: str,
    template: str,
    phase_key,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    D-188 Layer 1: Binary checklist audit against phase template.

    No opinions — only checks whether the template's required elements are
    present in the deliverable. Returns list of missing/incomplete items.
    Each item is {section, status, detail}.
    """
    phase_label = f"Phase {phase_key}"
    print(f"\n  📋 L1 Compliance check — {phase_label}...")

    l1_prompt = (
        f"You are a specification compliance checker for a {phase_label} deliverable.\n"
        "Your task is a binary audit: for each required element in the template, "
        "determine if it EXISTS in the deliverable. You have NO opinions about quality.\n\n"
        "RULES:\n"
        "1. Read the template to identify ALL required sections, subsections, fields, "
        "   and structural elements (manifests, appendices, cross-references, EOF sentinels).\n"
        "2. For each required element, check if it is PRESENT in the deliverable.\n"
        "3. A section is PRESENT if it has a heading AND substantive content (not just a heading).\n"
        "4. A field is PRESENT if it contains actual data (not placeholder text like 'TBD').\n"
        "5. Do NOT evaluate quality, accuracy, or completeness of content — only presence.\n\n"
        "Output as JSON ONLY (no markdown, no preamble):\n"
        '{"pass": true/false, "missing_items": [\n'
        '  {"section": "section name", "detail": "what is missing"}\n'
        "]}\n\n"
        "If all required elements are present, set pass=true and missing_items=[].\n\n"
        f"<phase_template>\n{template}\n</phase_template>\n\n"
        f"<deliverable>\n{deliverable}\n</deliverable>"
    )

    response = call_api(
        model=REVIEW_MODEL,
        system="You are a specification compliance checker. Output ONLY valid JSON, no preamble or markdown.",
        messages=[{"role": "user", "content": l1_prompt}],
        max_tokens=MAX_L1_TOKENS,
        enable_thinking=False,
        cache_system=True,
    )
    cost_tracker.record_call(str(phase_key), "l1-compliance", REVIEW_MODEL, response["usage"], 0, 0)

    result_text = extract_text(response["content"]).strip()

    try:
        clean = result_text.replace("```json", "").replace("```", "").strip()
        result = json.loads(clean)
    except json.JSONDecodeError:
        print(f"  ⚠ L1 response not valid JSON — treating as fail")
        result = {"pass": False, "missing_items": [{"section": "PARSE_ERROR", "detail": "L1 response was not valid JSON"}]}

    missing = result.get("missing_items", [])
    if result.get("pass", False):
        print(f"  ✅ L1 Compliance: PASS — all required elements present")
    else:
        print(f"  ⚠ L1 Compliance: {len(missing)} missing item(s):")
        for item in missing[:5]:
            print(f"     - {item.get('section', '?')}: {item.get('detail', '?')[:100]}")

    return missing


def run_layer_review(
    deliverable: str,
    template: str,
    phase_key,
    layer: int,
    persona_text: str,
    prior_deliverables: str,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    D-188 Generic reviewer for L2/L3/L4. Assembles prompt from template + persona.

    Returns parsed findings as list of dicts:
      [{id, category, section, issue, evidence, recommendation}, ...]
    """
    layer_names = {2: "Domain Expert", 3: "Downstream Consumer", 4: "Founder Comprehension"}
    layer_name = layer_names.get(layer, f"Layer {layer}")
    phase_label = f"Phase {phase_key}"
    max_tokens = {2: MAX_L2_TOKENS, 3: MAX_L3_TOKENS, 4: MAX_L4_TOKENS}.get(layer, MAX_L2_TOKENS)

    print(f"\n  🔍 L{layer} {layer_name} review — {phase_label}...")

    # Build classification rules (embedded in prompt for model access)
    classification_rules = (
        "CLASSIFICATION DECISION TREE (apply in order, first 'yes' wins):\n"
        "1. Is this factually wrong? (incorrect data, contradicts prior deliverable) → must-fix\n"
        "2. Is a required element missing or empty? (template requires X, deliverable lacks X) → must-fix\n"
        "3. Would this block the next phase's work? (downstream team cannot proceed) → must-fix\n"
        "4. Is this thin/vague where founder's knowledge would produce better content? → should-improve\n"
        "5. Is a technical concept unexplained for non-technical reader? → should-improve\n"
        "6. Everything else (suggestions, alternatives, nice-to-haves) → consider\n\n"
        "BOUNDARY RULES:\n"
        "- 'Thin but not wrong' → should-improve (not must-fix)\n"
        "- Missing subsection → must-fix ONLY if template lists it as required\n"
        "- 'Could be better' → consider\n"
        "- Wrong framework choice → must-fix ONLY if contradicts founder decision; else should-improve\n"
        "- Inconsistency within deliverable → must-fix\n"
        "- Inconsistency with prior deliverable → must-fix\n"
    )

    # System prompt varies by layer
    if layer == 4:
        system_prompt = (
            "You are a non-technical founder reviewing a deliverable for comprehensibility. "
            "You understand business concepts but not technical implementation details. "
            "Evaluate whether this document is understandable to someone who will pay for "
            "the build but has no software engineering background."
        )
    else:
        system_prompt = (
            f"You are a {layer_name} reviewer. You evaluate deliverables from the perspective "
            f"of a senior professional who would {'USE this deliverable in their domain work' if layer == 2 else 'CONSUME this deliverable as input for the next phase'}. "
            "Your review is independent — you have not seen any other reviewer's findings."
        )

    # User prompt with persona + deliverable + template
    user_prompt = (
        f"<your_persona>\n{persona_text}\n</your_persona>\n\n"
        f"<phase_template>\n{template}\n</phase_template>\n\n"
        f"<deliverable_to_review>\n{deliverable}\n</deliverable_to_review>\n\n"
    )

    if prior_deliverables and layer in (2, 3):
        user_prompt += f"<prior_deliverables>\n{prior_deliverables}\n</prior_deliverables>\n\n"

    user_prompt += (
        f"{classification_rules}\n"
        f"Review this {phase_label} deliverable as described in your persona. "
        "For EVERY finding, use this EXACT XML format:\n\n"
        "<finding>\n"
        f"  <id>L{layer}-N</id>\n"
        "  <category>must-fix | should-improve | consider</category>\n"
        "  <section>section name</section>\n"
        "  <issue>one sentence: what is wrong or missing</issue>\n"
        "  <evidence>quote or reference from deliverable OR template</evidence>\n"
        "  <recommendation>one sentence: specific action to resolve</recommendation>\n"
        "</finding>\n\n"
        "If you find no issues, output:\n<findings>NONE</findings>\n\n"
        "Output ALL findings wrapped in a <findings> tag. No preamble or commentary outside the tags."
    )

    # Enable thinking for L2/L3/L4 (deep analysis needed)
    response = call_api(
        model=REVIEW_MODEL,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        max_tokens=max_tokens,
        enable_thinking=True,
        thinking_effort="high",
        cache_system=True,
    )
    cost_tracker.record_call(
        str(phase_key), f"l{layer}-review", REVIEW_MODEL,
        response["usage"], 0, response.get("thinking_chars", 0)
    )

    review_text = extract_text(response["content"]).strip()

    # D-194 2C: Fast-fail for empty/unusable responses
    if not review_text:
        print(f"  ⚠ L{layer} {layer_name}: empty response — skipping layer")
        return []

    # Parse findings from XML
    findings = _parse_review_findings(review_text, layer)

    # Categorize and report
    must_fix = [f for f in findings if f["category"] == "must-fix"]
    should_improve = [f for f in findings if f["category"] == "should-improve"]
    consider = [f for f in findings if f["category"] == "consider"]

    print(f"  L{layer} {layer_name}: {len(must_fix)} must-fix, "
          f"{len(should_improve)} should-improve, {len(consider)} consider")
    for f in must_fix[:3]:
        print(f"     🔴 {f['id']}: {f['issue'][:100]}")
    for f in should_improve[:2]:
        print(f"     🟡 {f['id']}: {f['issue'][:100]}")

    # Save review findings
    review_report = {
        "layer": layer,
        "layer_name": layer_name,
        "phase": str(phase_key),
        "findings": findings,
        "summary": {
            "must_fix": len(must_fix),
            "should_improve": len(should_improve),
            "consider": len(consider),
            "total": len(findings),
        },
    }
    report_path = METRICS_DIR / f"phase-{phase_key}-l{layer}-review.json"
    report_path.write_text(json.dumps(review_report, indent=2))

    return findings


def _parse_review_findings(text: str, layer: int) -> list[dict]:
    """Parse XML findings from reviewer output into list of dicts."""
    if "<findings>NONE</findings>" in text or not text.strip():
        return []

    findings = []
    # Match individual <finding>...</finding> blocks
    pattern = re.compile(r'<finding>(.*?)</finding>', re.DOTALL)
    for match in pattern.finditer(text):
        block = match.group(1)
        finding = {
            "id": _extract_xml_field(block, "id") or f"L{layer}-?",
            "category": _extract_xml_field(block, "category") or "consider",
            "section": _extract_xml_field(block, "section") or "unknown",
            "issue": _extract_xml_field(block, "issue") or "",
            "evidence": _extract_xml_field(block, "evidence") or "",
            "recommendation": _extract_xml_field(block, "recommendation") or "",
        }
        # Normalize category
        cat = finding["category"].strip().lower()
        if cat not in ("must-fix", "should-improve", "consider"):
            cat = "consider"
        finding["category"] = cat
        findings.append(finding)

    return findings


def _extract_xml_field(block: str, field: str) -> str:
    """Extract text content from a simple XML tag within a block."""
    match = re.search(rf'<{field}>(.*?)</{field}>', block, re.DOTALL)
    return match.group(1).strip() if match else ""


# ── D-195: Diff-based correction helpers ─────────────────────────────────

def parse_correction_patches(xml_text: str) -> list[dict]:
    """Parse <corrections> XML into list of patch dicts."""
    patches = []
    patch_blocks = re.findall(r'<patch\s+id="([^"]*)">(.*?)</patch>', xml_text, re.DOTALL)

    for pid, block in patch_blocks:
        patch = {"id": pid}
        # Parse action, anchor, search_text with non-greedy match
        for field in ["action", "anchor", "search_text"]:
            match = re.search(rf'<{field}>(.*?)</{field}>', block, re.DOTALL)
            patch[field] = match.group(1).strip() if match else ""
        # Parse new_text robustly — Haiku often closes <new_text> with </search_text>
        # instead of </new_text>. Capture everything after <new_text> and strip
        # whatever trailing closing tag the model used.
        nt_match = re.search(r'<new_text>(.*)', block, re.DOTALL)
        if nt_match:
            content = nt_match.group(1).strip()
            content = re.sub(r'</\w+>\s*$', '', content).strip()
            patch["new_text"] = content
        else:
            patch["new_text"] = ""
        patches.append(patch)

    return patches


def apply_patches(deliverable: str, patches_xml: str) -> tuple[str, list[dict]]:
    """
    D-195: Apply correction patches to deliverable.
    Returns (patched_deliverable, application_log).

    Each log entry: {id, action, status, detail}
    Status: 'applied', 'applied_fuzzy', 'applied_anchored', 'applied_via_anchor',
            'skipped_not_found', 'skipped_ambiguous', 'skipped_anchor_not_found',
            'skipped_no_search', 'skipped_unknown_action'
    """
    result = deliverable
    log = []

    patches = parse_correction_patches(patches_xml)

    for patch in patches:
        pid = patch["id"]
        action = patch["action"]
        search_text = patch.get("search_text", "")
        new_text = patch.get("new_text", "")
        anchor = patch.get("anchor", "")

        # Verify anchor exists
        if anchor and anchor not in result:
            log.append({"id": pid, "action": action, "status": "skipped_anchor_not_found",
                        "detail": f"Anchor not found: {anchor[:80]}"})
            continue

        if action == "replace":
            if not search_text:
                log.append({"id": pid, "action": action, "status": "skipped_no_search",
                            "detail": "No search_text provided"})
                continue
            # D-195 safeguard: never delete content via empty replacement
            if not new_text:
                log.append({"id": pid, "action": action, "status": "skipped_empty_replacement",
                            "detail": f"new_text empty — refusing to delete {len(search_text)} chars"})
                continue

            count = result.count(search_text)
            if count == 0:
                # Try fuzzy: strip extra whitespace and retry
                normalized_search = " ".join(search_text.split())
                normalized_result = " ".join(result.split())
                if normalized_search in normalized_result:
                    pattern = re.escape(search_text)
                    pattern = re.sub(r'\\ +', r'\\s+', pattern)
                    result, n = re.subn(pattern, new_text, result, count=1)
                    if n:
                        log.append({"id": pid, "action": action, "status": "applied_fuzzy",
                                    "detail": "Applied with whitespace normalization"})
                        continue
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": f"search_text not found: {search_text[:80]}"})
                continue
            elif count > 1:
                # Ambiguous — try to use anchor to narrow scope
                if anchor:
                    anchor_pos = result.find(anchor)
                    search_pos = result.find(search_text, max(0, anchor_pos - 2000))
                    if search_pos != -1 and search_pos < anchor_pos + 5000:
                        result = result[:search_pos] + new_text + result[search_pos + len(search_text):]
                        log.append({"id": pid, "action": action, "status": "applied_anchored",
                                    "detail": f"Resolved ambiguity using anchor (found {count} matches)"})
                        continue
                log.append({"id": pid, "action": action, "status": "skipped_ambiguous",
                            "detail": f"search_text appears {count} times"})
                continue
            else:
                result = result.replace(search_text, new_text, 1)
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Replaced {len(search_text)} chars with {len(new_text)} chars"})

        elif action == "insert_after":
            if search_text and search_text in result:
                pos = result.find(search_text) + len(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Inserted {len(new_text)} chars after search_text"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": "search_text not found for insert_after"})

        elif action == "insert_before":
            if search_text and search_text in result:
                pos = result.find(search_text)
                result = result[:pos] + new_text + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Inserted {len(new_text)} chars before search_text"})
            elif anchor and anchor in result:
                pos = result.find(anchor)
                result = result[:pos] + new_text + "\n\n" + result[pos:]
                log.append({"id": pid, "action": action, "status": "applied_via_anchor",
                            "detail": "Inserted before anchor heading"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_not_found",
                            "detail": "Neither search_text nor anchor found"})

        elif action == "append_to_section":
            if anchor and anchor in result:
                anchor_pos = result.find(anchor)
                heading_level = len(anchor) - len(anchor.lstrip('#'))
                if heading_level < 1:
                    heading_level = 2  # Default to H2 if anchor has no '#' prefix
                pattern = r'\n#{1,' + str(heading_level) + r'} [^\n]+'
                next_heading = re.search(pattern, result[anchor_pos + len(anchor):])
                if next_heading:
                    insert_pos = anchor_pos + len(anchor) + next_heading.start()
                else:
                    insert_pos = len(result)
                result = result[:insert_pos] + "\n\n" + new_text + "\n" + result[insert_pos:]
                log.append({"id": pid, "action": action, "status": "applied",
                            "detail": f"Appended {len(new_text)} chars to section"})
            else:
                log.append({"id": pid, "action": action, "status": "skipped_anchor_not_found",
                            "detail": f"Section anchor not found: {anchor[:80]}"})

        else:
            log.append({"id": pid, "action": action, "status": "skipped_unknown_action",
                        "detail": f"Unknown action type: {action}"})

    return result, log


def run_correction_synthesis(
    deliverable: str,
    findings: list[dict],
    phase_key,
    cost_tracker: CostTracker,
) -> str:
    """
    D-195: Diff-based correction synthesis.

    Instead of regenerating the entire deliverable, asks the model to output
    targeted correction patches in XML format, then applies them programmatically.
    This prevents collateral damage from full-document regeneration on Haiku.

    Returns corrected deliverable markdown.
    """
    must_fix = [f for f in findings if f["category"] == "must-fix"]

    if not must_fix:
        return deliverable

    print(f"\n  🔧 Correction synthesis (diff-based) — {len(must_fix)} must-fix item(s)...")

    # Build findings XML for the correction prompt
    findings_xml = ""
    for f in must_fix:
        findings_xml += (
            "<finding>\n"
            f"  <id>{f['id']}</id>\n"
            f"  <section>{f['section']}</section>\n"
            f"  <issue>{f['issue']}</issue>\n"
            f"  <evidence>{f['evidence']}</evidence>\n"
            f"  <recommendation>{f['recommendation']}</recommendation>\n"
            "</finding>\n"
        )

    correction_prompt = (
        "<correction_request>\n"
        f"  <deliverable>\n{deliverable}\n  </deliverable>\n"
        f"  <findings>\n{findings_xml}  </findings>\n"
        "  <instruction>\n"
        "    For each finding, output ONE patch in the <corrections> block.\n"
        "    Do NOT output the full document. Output ONLY the corrections XML.\n"
        "  </instruction>\n"
        "</correction_request>"
    )

    response = call_api(
        model=REVIEW_MODEL,
        system=(
            "You are a precise document patch generator. For each finding, output a "
            "targeted correction patch. Do NOT output the full document. Output ONLY "
            "the <corrections> XML block with patches for each must-fix finding.\n\n"
            "RULES:\n"
            "1. Each patch targets ONE specific location in the document.\n"
            "2. <anchor> must be an EXACT markdown heading from the document (e.g., '## 1.3 Target Audience').\n"
            "3. <search_text> must be a UNIQUE phrase (10-50 words) that appears EXACTLY once "
            "   in the document near the anchor. Copy it character-for-character.\n"
            "4. <new_text> is the replacement content. Include surrounding context if needed "
            "   for the replacement to read naturally.\n"
            "5. For missing sections/content, use action='append_to_section' or 'insert_after'.\n"
            "6. For incorrect content, use action='replace'.\n"
            "7. Keep patches minimal — change only what the finding requires.\n"
            "8. If a finding requires adding a NEW section that doesn't exist, use "
            "   action='insert_before' with the anchor set to the heading AFTER where "
            "   the new section should appear.\n\n"
            "OUTPUT FORMAT:\n"
            "<corrections>\n"
            '  <patch id="FINDING-ID">\n'
            "    <action>replace|insert_after|insert_before|append_to_section</action>\n"
            "    <anchor>## Exact Heading</anchor>\n"
            "    <search_text>exact phrase from document</search_text>\n"
            "    <new_text>replacement or inserted content</new_text>\n"
            "  </patch>\n"
            "</corrections>"
        ),
        messages=[{"role": "user", "content": correction_prompt}],
        max_tokens=MAX_CORRECTION_TOKENS,
        enable_thinking=True,
        thinking_effort="high",
        cache_system=True,
    )
    cost_tracker.record_call(
        str(phase_key), "correction-synthesis", REVIEW_MODEL,
        response["usage"], 0, response.get("thinking_chars", 0)
    )

    raw_output = extract_text(response["content"]).strip()

    # D-195: Log raw correction XML for debugging
    debug_dir = Path("output/metrics")
    debug_dir.mkdir(parents=True, exist_ok=True)
    _correction_count = getattr(run_correction_synthesis, '_count', 0) + 1
    run_correction_synthesis._count = _correction_count
    debug_file = debug_dir / f"phase-{phase_key}-correction-{_correction_count}-raw.txt"
    debug_file.write_text(raw_output, encoding="utf-8")
    print(f"  📝 Raw correction XML saved: {debug_file} ({len(raw_output)} chars)")

    # D-194 2C: Fast-fail for empty correction — return original deliverable
    if not raw_output:
        print(f"  ⚠ Correction synthesis returned empty — keeping original deliverable")
        return deliverable

    # Parse and apply patches
    patches = parse_correction_patches(raw_output)
    if not patches:
        print(f"  ⚠ No patches parsed from correction output ({len(raw_output)} chars) — keeping original")
        return deliverable

    corrected, log = apply_patches(deliverable, raw_output)

    # Report results
    applied_count = sum(1 for entry in log if "applied" in entry["status"])
    skipped_count = sum(1 for entry in log if "skipped" in entry["status"])

    print(f"  ✅ Patches: {applied_count} applied, {skipped_count} skipped (of {len(patches)} total)")
    for entry in log:
        symbol = "✓" if "applied" in entry["status"] else "✗"
        print(f"     {symbol} {entry['id']}: {entry['status']} — {entry['detail'][:80]}")

    if applied_count == 0 and len(patches) > 0:
        print(f"  ⚠ No patches could be applied — keeping original deliverable")
        return deliverable

    delta = len(corrected) - len(deliverable)
    print(f"  📐 Size: {len(deliverable):,} → {len(corrected):,} chars "
          f"({'+' if delta >= 0 else ''}{delta:,})")
    return corrected


def build_interview_brief(
    findings_l2: list[dict],
    findings_l3: list[dict],
    findings_l4: list[dict],
    phase_key,
    review_personas: dict,
) -> str:
    """
    D-188: Consolidate should-improve items into XML interview brief.

    Applies MAX_REENGAGEMENT_TOPICS cap. Returns brief XML string,
    or empty string if no should-improve items.
    """
    si_l2 = [f for f in findings_l2 if f["category"] == "should-improve"]
    si_l3 = [f for f in findings_l3 if f["category"] == "should-improve"]
    si_l4 = [f for f in findings_l4 if f["category"] == "should-improve"]

    total = len(si_l2) + len(si_l3) + len(si_l4)
    if total == 0:
        return ""

    # Cap total topics — prioritize L2 (deepest), then L3, then L4
    remaining = MAX_REENGAGEMENT_TOPICS
    selected_l2 = si_l2[:remaining]
    remaining -= len(selected_l2)
    selected_l3 = si_l3[:remaining] if remaining > 0 else []
    remaining -= len(selected_l3)
    selected_l4 = si_l4[:remaining] if remaining > 0 else []

    deferred = total - len(selected_l2) - len(selected_l3) - len(selected_l4)
    if deferred > 0:
        print(f"  ℹ {deferred} should-improve item(s) deferred to consider (cap: {MAX_REENGAGEMENT_TOPICS})")

    # Get persona role titles for the brief header
    l2_persona = review_personas.get("l2", {}).get(phase_key, "")
    l3_persona = review_personas.get("l3", {}).get(phase_key, "")
    l2_role = _extract_role_from_persona(l2_persona)
    l3_role = _extract_role_from_persona(l3_persona)

    # Build XML brief
    brief = f'<interview_brief phase="{phase_key}">\n'
    brief += (
        f"  <summary>{total} should-improve items found across "
        f"L2 ({len(si_l2)}), L3 ({len(si_l3)}), L4 ({len(si_l4)}) "
        f"for Phase {phase_key} deliverable.</summary>\n\n"
    )

    if selected_l2:
        brief += f'  <topic_group source="L2 -- Domain Expert ({l2_role})">\n'
        for i, f in enumerate(selected_l2, 1):
            brief += (
                f'    <topic id="SI-{phase_key}-L2-{i}">\n'
                f"      <context>{f['evidence']}</context>\n"
                f"      <gap>{f['issue']}</gap>\n"
                f"      <question>{f['recommendation']}</question>\n"
                f"    </topic>\n"
            )
        brief += "  </topic_group>\n\n"

    if selected_l3:
        brief += f'  <topic_group source="L3 -- Downstream Consumer ({l3_role})">\n'
        for i, f in enumerate(selected_l3, 1):
            brief += (
                f'    <topic id="SI-{phase_key}-L3-{i}">\n'
                f"      <context>{f['evidence']}</context>\n"
                f"      <gap>{f['issue']}</gap>\n"
                f"      <question>{f['recommendation']}</question>\n"
                f"    </topic>\n"
            )
        brief += "  </topic_group>\n\n"

    if selected_l4:
        brief += '  <topic_group source="L4 -- Founder Comprehension">\n'
        for i, f in enumerate(selected_l4, 1):
            brief += (
                f'    <topic id="SI-{phase_key}-L4-{i}">\n'
                f"      <context>{f['evidence']}</context>\n"
                f"      <gap>{f['issue']}</gap>\n"
                f"      <question>{f['recommendation']}</question>\n"
                f"    </topic>\n"
            )
        brief += "  </topic_group>\n\n"

    brief += "</interview_brief>"
    return brief


def _extract_role_from_persona(persona_text: str) -> str:
    """Extract the Role value from a persona section's markdown bullets."""
    match = re.search(r'\*\*Role:\*\*\s*(.+)', persona_text)
    return match.group(1).strip() if match else "Reviewer"


def run_founder_reengagement(
    brief: str,
    persona: str,
    phase_key,
    cost_tracker: CostTracker,
) -> list[dict]:
    """
    D-188: Guide re-engages founder using interview brief.

    One conversation covering all should-improve topics. L2 first, L4 last.
    Returns list of {topic_id, response} dicts.
    """
    phase_label = f"Phase {phase_key}"
    print(f"\n{'='*60}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] 🗣  {phase_label} — FOUNDER RE-ENGAGEMENT")
    print(f"{'='*60}")

    # Guide system prompt for re-engagement
    guide_system = (
        "You are the PlatformForge Guide conducting a focused follow-up conversation "
        f"with the founder about their {phase_label} deliverable.\n\n"
        "You have an interview brief with specific topics that need the founder's input. "
        "Your job is to:\n"
        "1. Weave ALL topics into ONE natural conversation (not separate interviews).\n"
        "2. Cover L2 (technical) topics FIRST, L4 (comprehension) topics LAST.\n"
        "3. Ask open questions — do NOT lead the founder to specific answers.\n"
        "4. Capture the founder's answers VERBATIM. Do not summarize or editorialize.\n"
        "5. After all topics are covered, end with [REENGAGEMENT_COMPLETE].\n\n"
        f"<interview_brief>\n{brief}\n</interview_brief>"
    )

    # Founder system prompt with memory
    founder_system = persona
    founder_memory_file = DELIVERABLES_DIR / "founder-memory.md"
    if founder_memory_file.exists():
        memory_text = founder_memory_file.read_text(encoding="utf-8")
        founder_system += (
            "\n\n---\n\n<founder_memory>\n"
            "The following is a summary of decisions YOU (the founder) made in prior phases. "
            "Stay consistent with these decisions. Reference them naturally when relevant.\n\n"
            + memory_text
            + "\n</founder_memory>"
        )
    founder_system += (
        "\n\n---\n\n<reengagement_context>\n"
        f"The PlatformForge Guide is following up on your {phase_label} deliverable. "
        "They have some clarifying questions based on expert review. Answer directly "
        "and specifically — give clear, decisive answers. Your answers will be used to "
        "improve the deliverable.\n"
        "</reengagement_context>"
    )

    # Conversation state
    guide_messages = []
    founder_messages = []
    transcript = []

    # Guide opens
    guide_messages.append({"role": "user", "content": "Please begin the follow-up conversation with the founder."})

    guide_response = call_api(
        model=REVIEW_MODEL,
        system=guide_system,
        messages=guide_messages,
        max_tokens=MAX_L2_TOKENS,
        enable_thinking=True,
        thinking_effort="high",
        cache_system=True,
    )
    cost_tracker.record_call(
        str(phase_key), "reengagement-guide", REVIEW_MODEL,
        guide_response["usage"], 0, guide_response.get("thinking_chars", 0)
    )

    guide_text = extract_text(guide_response["content"])
    guide_messages.append({"role": "assistant", "content": content_to_dict_list(guide_response["content"])})
    transcript.append({"role": "guide", "speaker": "Guide", "text": guide_text})
    print(f"\n  Guide: {guide_text[:150]}...")

    # Exchange loop
    for exchange in range(MAX_REENGAGEMENT_EXCHANGES):
        if "[REENGAGEMENT_COMPLETE]" in guide_text:
            print(f"\n  ✅ Re-engagement complete after {exchange} exchange(s)")
            break

        # Founder responds
        founder_messages.append({"role": "user", "content": guide_text})
        founder_response = call_api(
            model=FOUNDER_MODEL,
            system=founder_system,
            messages=founder_messages,
            max_tokens=MAX_FOUNDER_TOKENS,
            enable_thinking=False,
            cache_system=True,
        )
        cost_tracker.record_call(
            str(phase_key), "reengagement-founder", FOUNDER_MODEL,
            founder_response["usage"], 0, 0
        )

        founder_text = extract_text(founder_response["content"])
        founder_messages.append({"role": "assistant", "content": content_to_dict_list(founder_response["content"])})
        transcript.append({"role": "founder", "speaker": "Founder", "text": founder_text})
        print(f"  Founder: {founder_text[:150]}...")

        # Guide follows up
        guide_messages.append({"role": "user", "content": founder_text})
        guide_response = call_api(
            model=REVIEW_MODEL,
            system=guide_system,
            messages=guide_messages,
            max_tokens=MAX_L2_TOKENS,
            enable_thinking=True,
            thinking_effort="high",
            cache_system=True,
        )
        cost_tracker.record_call(
            str(phase_key), "reengagement-guide", REVIEW_MODEL,
            guide_response["usage"], 0, guide_response.get("thinking_chars", 0)
        )

        guide_text = extract_text(guide_response["content"])
        guide_messages.append({"role": "assistant", "content": content_to_dict_list(guide_response["content"])})
        transcript.append({"role": "guide", "speaker": "Guide", "text": guide_text})
        print(f"  Guide: {guide_text[:150]}...")

    # Save re-engagement conversation
    reeng_path = CONVERSATIONS_DIR / f"phase-{phase_key}-reengagement.json"
    reeng_path.write_text(json.dumps(transcript, indent=2, ensure_ascii=False))

    reeng_md_parts = []
    for entry in transcript:
        reeng_md_parts.append(f"**{entry['speaker']}:** {entry['text']}")
    reeng_md_path = CONVERSATIONS_DIR / f"phase-{phase_key}-reengagement.md"
    reeng_md_path.write_text("\n\n---\n\n".join(reeng_md_parts), encoding="utf-8")
    print(f"  💾 Re-engagement saved: {reeng_path} ({len(transcript)} entries)")

    # Extract founder responses as topic_id → response mappings
    # The guide's questions map to brief topics; founder's answers follow
    responses = []
    founder_entries = [t for t in transcript if t["role"] == "founder"]
    for entry in founder_entries:
        responses.append({"topic_id": "combined", "response": entry["text"]})

    return responses


def run_targeted_update(
    deliverable: str,
    brief: str,
    responses: list[dict],
    phase_key,
    cost_tracker: CostTracker,
) -> str:
    """
    D-188: Apply founder responses to deliverable sections.

    Returns complete updated deliverable markdown.
    """
    phase_label = f"Phase {phase_key}"
    print(f"\n  📝 Targeted update — incorporating founder responses...")

    # Build founder responses XML
    responses_xml = ""
    for r in responses:
        responses_xml += f'<response topic_id="{r["topic_id"]}">\n{r["response"]}\n</response>\n'

    update_prompt = (
        "<founder_update_request>\n"
        f"  <deliverable>\n{deliverable}\n  </deliverable>\n"
        f"  <interview_brief>\n{brief}\n  </interview_brief>\n"
        f"  <founder_responses>\n{responses_xml}  </founder_responses>\n"
        "  <instruction>\n"
        "    For each founder response, update the deliverable section\n"
        "    identified in the corresponding interview brief topic.\n"
        "    Incorporate the founder's answer as authoritative content —\n"
        "    do not paraphrase, soften, or editorialize. The founder's\n"
        "    words represent ground truth about their business.\n"
        "    Do not modify any section not referenced by a topic ID.\n"
        "    Output the complete updated deliverable.\n"
        "  </instruction>\n"
        "</founder_update_request>"
    )

    response = call_api(
        model=REVIEW_MODEL,
        system=(
            "You are a precise document editor. Incorporate founder responses into the "
            "deliverable sections identified in the interview brief. Preserve all other "
            "content exactly as-is. Output as complete markdown starting with level-1 heading."
        ),
        messages=[{"role": "user", "content": update_prompt}],
        max_tokens=MAX_CORRECTION_TOKENS,
        enable_thinking=True,
        thinking_effort="high",
        cache_system=True,
    )
    cost_tracker.record_call(
        str(phase_key), "targeted-update", REVIEW_MODEL,
        response["usage"], 0, response.get("thinking_chars", 0)
    )

    updated = extract_text(response["content"]).strip()
    updated = strip_synthesis_preamble(updated)

    # Handle truncation
    if response.get("stop_reason") == "max_tokens":
        print(f"  ⚠ Targeted update truncated — requesting continuation")
        cont_messages = [
            {"role": "user", "content": update_prompt},
            {"role": "assistant", "content": updated},
            {"role": "user", "content": "Continue exactly where you left off. Do not repeat any content."},
        ]
        cont_response = call_api(
            model=REVIEW_MODEL,
            system="Continue outputting the deliverable exactly where you left off.",
            messages=cont_messages,
            max_tokens=MAX_CORRECTION_TOKENS,
            enable_thinking=False,
        )
        cost_tracker.record_call(
            str(phase_key), "targeted-update-cont", REVIEW_MODEL,
            cont_response["usage"], 0, 0
        )
        continuation = extract_text(cont_response["content"]).strip()
        updated += "\n" + continuation

    # Sanity check
    if len(updated) < len(deliverable) * 0.5:
        print(f"  ⚠ Updated deliverable <50% of original — keeping original")
        return deliverable

    delta = len(updated) - len(deliverable)
    print(f"  ✅ Targeted update: {len(deliverable):,} → {len(updated):,} chars "
          f"({'+' if delta >= 0 else ''}{delta:,})")
    return updated


def _build_review_notes(
    findings_l2: list[dict],
    findings_l3: list[dict],
    findings_l4: list[dict],
    phase_key,
) -> str:
    """Build companion review notes document from 'consider' items."""
    consider_items = (
        [f for f in findings_l2 if f["category"] == "consider"]
        + [f for f in findings_l3 if f["category"] == "consider"]
        + [f for f in findings_l4 if f["category"] == "consider"]
    )

    if not consider_items:
        return ""

    notes = f"# Phase {phase_key} — Review Notes (Consider Items)\n\n"
    notes += f"> {len(consider_items)} suggestions from expert review. "
    notes += "These are not errors — the deliverable is correct without them.\n\n"

    for f in consider_items:
        notes += f"### {f['id']}: {f['section']}\n"
        notes += f"- **Issue:** {f['issue']}\n"
        notes += f"- **Evidence:** {f['evidence']}\n"
        notes += f"- **Suggestion:** {f['recommendation']}\n\n"

    return notes


def run_review_pipeline(
    deliverable: str,
    template: str,
    phase_key,
    persona: str,
    prior_deliverables: str,
    review_personas: dict,
    cost_tracker: CostTracker,
) -> tuple[str, str]:
    """
    D-188/D-189/D-194 MAIN ORCHESTRATOR: 4-layer review pipeline with parallel L2/L3/L4.

    Pipeline:
      Step 1: L1 → correct → L1 re-check loop
      Step 2: [L2 + L3 + L4 in parallel] — all three review the L1-corrected deliverable
      Step 3: Merge all must-fix findings → ONE correction synthesis → ONE L1 re-check
      Step 4: Consolidate should-improve → founder re-engagement → targeted update
      Step 5: Final L1 re-check

    Returns (final_deliverable, review_notes).
    """
    phase_label = f"Phase {phase_key}"
    print(f"\n{'='*60}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] 🔬 {phase_label} — D-188 EXPERT REVIEW PIPELINE")
    print(f"{'='*60}")

    pipeline_start = time.time()
    current = deliverable

    # ── Step 1: L1 Compliance ──────────────────────────────────────────
    print(f"\n  {'─'*50}")
    print(f"  Step 1: L1 Compliance Check")
    print(f"  {'─'*50}")
    l1_start = time.time()
    l1_missing = run_l1_compliance(current, template, phase_key, cost_tracker)

    if l1_missing:
        # Build pseudo-findings for correction synthesis
        l1_findings = [{
            "id": f"L1-{i+1}",
            "category": "must-fix",
            "section": item.get("section", "unknown"),
            "issue": item.get("detail", "Missing required element"),
            "evidence": "Required by phase template",
            "recommendation": f"Add missing element: {item.get('detail', '')}",
        } for i, item in enumerate(l1_missing)]

        current = run_correction_synthesis(current, l1_findings, phase_key, cost_tracker)

        # L1 re-check
        for retry in range(MAX_L1_RETRIES):
            l1_recheck = run_l1_compliance(current, template, phase_key, cost_tracker)
            if not l1_recheck:
                break
            print(f"  ⚠ L1 re-check {retry+1}: still {len(l1_recheck)} missing item(s)")
            if retry < MAX_L1_RETRIES - 1:
                recheck_findings = [{
                    "id": f"L1-R{retry+1}-{i+1}",
                    "category": "must-fix",
                    "section": item.get("section", "unknown"),
                    "issue": item.get("detail", "Still missing"),
                    "evidence": "Required by phase template",
                    "recommendation": f"Add missing element: {item.get('detail', '')}",
                } for i, item in enumerate(l1_recheck)]
                current = run_correction_synthesis(current, recheck_findings, phase_key, cost_tracker)

    l1_elapsed = time.time() - l1_start

    # ── Step 2: L2 + L3 + L4 Parallel Expert Review (D-194) ─────────────
    print(f"\n  {'─'*50}")
    print(f"  Step 2: L2 + L3 + L4 Parallel Expert Review")
    print(f"  {'─'*50}")

    l2_persona = review_personas.get("l2", {}).get(phase_key, "Senior domain expert reviewer.")
    l3_persona = review_personas.get("l3", {}).get(phase_key, "Downstream phase consumer reviewer.")
    l4_persona = review_personas.get("l4", "Non-technical founder comprehension reviewer.")

    findings_l2, findings_l3, findings_l4 = [], [], []
    parallel_start = time.time()

    with ThreadPoolExecutor(max_workers=3, thread_name_prefix="review") as executor:
        futures = {
            executor.submit(
                run_layer_review, current, template, phase_key, 2,
                l2_persona, prior_deliverables, cost_tracker
            ): "L2",
            executor.submit(
                run_layer_review, current, template, phase_key, 3,
                l3_persona, prior_deliverables, cost_tracker
            ): "L3",
            executor.submit(
                run_layer_review, current, template, phase_key, 4,
                l4_persona, "", cost_tracker
            ): "L4",
        }

        for future in as_completed(futures):
            layer_label = futures[future]
            try:
                result = future.result()
                if layer_label == "L2":
                    findings_l2 = result
                elif layer_label == "L3":
                    findings_l3 = result
                elif layer_label == "L4":
                    findings_l4 = result
            except Exception as e:
                print(f"  ❌ {layer_label} review failed: {type(e).__name__}: {str(e)[:200]}")
                print(f"  ⚠ Continuing with remaining review layers")

    parallel_elapsed = time.time() - parallel_start
    print(f"\n  ⏱ Parallel review complete in {parallel_elapsed:.0f}s")

    # ── Step 3: Merged Correction Synthesis (D-194) ──────────────────────
    print(f"\n  {'─'*50}")
    print(f"  Step 3: Merged Correction Synthesis")
    print(f"  {'─'*50}")

    correction_start = time.time()
    l2_must_fix = [f for f in findings_l2 if f["category"] == "must-fix"]
    l3_must_fix = [f for f in findings_l3 if f["category"] == "must-fix"]
    l4_must_fix = [f for f in findings_l4 if f["category"] == "must-fix"]
    all_must_fix = l2_must_fix + l3_must_fix + l4_must_fix

    if all_must_fix:
        print(f"  {len(all_must_fix)} must-fix finding(s) across L2/L3/L4 — merging into one correction pass")
        all_findings = findings_l2 + findings_l3 + findings_l4
        current = run_correction_synthesis(current, all_findings, phase_key, cost_tracker)

        # ONE L1 re-check after merged corrections
        l1_post_review = run_l1_compliance(current, template, phase_key, cost_tracker)
        if l1_post_review:
            print(f"  ⚠ L1 re-check post-review: {len(l1_post_review)} item(s) — correcting")
            l1_findings = [{
                "id": f"L1-PR-{i+1}", "category": "must-fix",
                "section": item.get("section", "unknown"),
                "issue": item.get("detail", "Missing after review correction"),
                "evidence": "Required by phase template",
                "recommendation": f"Restore missing element: {item.get('detail', '')}",
            } for i, item in enumerate(l1_post_review)]
            current = run_correction_synthesis(current, l1_findings, phase_key, cost_tracker)
    else:
        print(f"  ✅ No must-fix findings across L2/L3/L4 — skipping correction")
    correction_elapsed = time.time() - correction_start

    # ── Step 4: Should-Improve Consolidation & Founder Re-engagement ──
    print(f"\n  {'─'*50}")
    print(f"  Step 4: Should-Improve Consolidation")
    print(f"  {'─'*50}")
    reengagement_start = time.time()
    brief = build_interview_brief(findings_l2, findings_l3, findings_l4, phase_key, review_personas)

    final_l1_start = time.time()
    if brief:
        # Save the interview brief
        brief_path = METRICS_DIR / f"phase-{phase_key}-interview-brief.xml"
        brief_path.write_text(brief, encoding="utf-8")
        print(f"  💾 Interview brief saved: {brief_path}")

        # Founder re-engagement
        responses = run_founder_reengagement(brief, persona, phase_key, cost_tracker)

        if responses:
            # Targeted synthesis update
            current = run_targeted_update(current, brief, responses, phase_key, cost_tracker)

            reengagement_elapsed = time.time() - reengagement_start

            # Final L1 re-check
            print(f"\n  {'─'*50}")
            print(f"  Step 5: Final L1 Re-check")
            print(f"  {'─'*50}")
            final_l1_start = time.time()
            l1_final = run_l1_compliance(current, template, phase_key, cost_tracker)
            if l1_final:
                print(f"  ⚠ Final L1: {len(l1_final)} item(s) — correcting")
                l1_findings = [{
                    "id": f"L1-FINAL-{i+1}", "category": "must-fix",
                    "section": item.get("section", "unknown"),
                    "issue": item.get("detail", "Missing after targeted update"),
                    "evidence": "Required by phase template",
                    "recommendation": f"Restore missing element: {item.get('detail', '')}",
                } for i, item in enumerate(l1_final)]
                current = run_correction_synthesis(current, l1_findings, phase_key, cost_tracker)
        else:
            reengagement_elapsed = time.time() - reengagement_start
    else:
        print(f"  ✅ No should-improve items — skipping founder re-engagement")
        reengagement_elapsed = time.time() - reengagement_start
    final_l1_elapsed = time.time() - final_l1_start

    # ── Build Review Notes ──────────────────────────────────────────────
    review_notes = _build_review_notes(findings_l2, findings_l3, findings_l4, phase_key)

    # Pipeline summary
    elapsed = time.time() - pipeline_start
    total_must_fix = len(l2_must_fix) + len(l3_must_fix) + len(l4_must_fix) + len(l1_missing)
    total_si = sum(1 for f in findings_l2 + findings_l3 + findings_l4 if f["category"] == "should-improve")
    total_consider = sum(1 for f in findings_l2 + findings_l3 + findings_l4 if f["category"] == "consider")

    print(f"\n{'='*60}")
    print(f"  {phase_label} REVIEW PIPELINE COMPLETE ({elapsed/60:.1f} min)")
    print(f"  Findings: {total_must_fix} must-fix (corrected), "
          f"{total_si} should-improve {'(re-engaged)' if brief else '(none)'}, "
          f"{total_consider} consider")
    print(f"  Deliverable: {len(deliverable):,} → {len(current):,} chars")
    print(f"{'='*60}")

    # Save pipeline summary
    summary = {
        "phase": str(phase_key),
        "review_model": REVIEW_MODEL,
        "pipeline_elapsed_seconds": round(elapsed),
        "l1_initial_missing": len(l1_missing),
        "l2_findings": {"must_fix": len(l2_must_fix), "should_improve": len([f for f in findings_l2 if f["category"] == "should-improve"]), "consider": len([f for f in findings_l2 if f["category"] == "consider"])},
        "l3_findings": {"must_fix": len(l3_must_fix), "should_improve": len([f for f in findings_l3 if f["category"] == "should-improve"]), "consider": len([f for f in findings_l3 if f["category"] == "consider"])},
        "l4_findings": {"must_fix": len(l4_must_fix), "should_improve": len([f for f in findings_l4 if f["category"] == "should-improve"]), "consider": len([f for f in findings_l4 if f["category"] == "consider"])},
        "reengagement_triggered": bool(brief),
        "deliverable_delta_chars": len(current) - len(deliverable),
        "timing": {
            "l1_initial_seconds": round(l1_elapsed),
            "parallel_review_wall_seconds": round(parallel_elapsed),
            "correction_synthesis_seconds": round(correction_elapsed),
            "reengagement_seconds": round(reengagement_elapsed),
            "final_l1_seconds": round(final_l1_elapsed),
        },
    }
    summary_path = METRICS_DIR / f"phase-{phase_key}-review-pipeline.json"
    summary_path.write_text(json.dumps(summary, indent=2))

    return current, review_notes


def run_phase(
    phase_key,
    master_prompt: str,
    persona: str,
    max_exchanges: int,
    cost_tracker: CostTracker,
    research_caps: dict = None,
    review_personas: dict = None,
):
    """Execute a complete phase: conversation + synthesis + D-188 review pipeline."""
    phase_label = f"Phase {phase_key}"
    print(f"\n{'#'*60}")
    print(f"  🚀 STARTING {phase_label.upper()}")
    print(f"{'#'*60}")

    start_time = time.time()

    # Load phase template
    templates = PHASE_TEMPLATES[phase_key]
    if "combined" in templates:
        conversation_template = load_template(templates["combined"])
        synthesis_template = conversation_template  # Same file
    else:
        conversation_template = load_template(templates["conversation"])
        synthesis_template = load_template(templates["synthesis"])

    print(f"  Template loaded: {len(conversation_template):,} chars")

    # Load prior deliverables
    prior_deliverables = load_prior_deliverables(phase_key, cost_tracker=cost_tracker)
    if prior_deliverables:
        print(f"  Prior deliverables loaded: {len(prior_deliverables):,} chars")
    elif phase_key != 1:
        # Every phase after Phase 1 MUST have prior deliverables
        # If they're missing, the conversation will restart from zero — useless
        raise RuntimeError(
            f"No prior deliverables found for {phase_label}. "
            f"Phases before this one likely failed to generate output. "
            f"Check the deliverables folder: {DELIVERABLES_DIR}"
        )

    # D-194 3A: Per-segment timing
    conversation_start = time.time()

    # Run conversation
    transcript = run_conversation(
        phase_key=phase_key,
        master_prompt=master_prompt,
        phase_template=conversation_template,
        persona=persona,
        prior_deliverables=prior_deliverables,
        max_exchanges=max_exchanges,
        cost_tracker=cost_tracker,
        research_caps=research_caps,
    )

    conversation_elapsed = time.time() - conversation_start

    # S74 D-167: Distillation skipped — raw transcript goes directly to synthesis.

    synthesis_start = time.time()

    # Run synthesis
    deliverable = run_synthesis(
        phase_key=phase_key,
        master_prompt=master_prompt,
        synthesis_template=synthesis_template,
        conversation_transcript=transcript,
        prior_deliverables=prior_deliverables,
        cost_tracker=cost_tracker,
    )

    synthesis_elapsed = time.time() - synthesis_start

    # ---------------------------------------------------------------------------
    # D-188/D-194: 4-Layer Expert Review Pipeline (parallel L2/L3/L4)
    # ---------------------------------------------------------------------------
    review_elapsed = 0.0
    if review_personas:
        review_start = time.time()
        deliverable, review_notes = run_review_pipeline(
            deliverable=deliverable,
            template=synthesis_template,
            phase_key=phase_key,
            persona=persona,
            prior_deliverables=prior_deliverables,
            review_personas=review_personas,
            cost_tracker=cost_tracker,
        )
        review_elapsed = time.time() - review_start

        # Save reviewed deliverable (overwrite synthesis output)
        deliv_path = DELIVERABLES_DIR / f"phase-{phase_key}-deliverable.md"
        deliv_path.write_text(deliverable, encoding="utf-8")
        print(f"  💾 Reviewed deliverable saved: {deliv_path}")

        # Save review notes (consider items) if any
        if review_notes:
            notes_path = DELIVERABLES_DIR / f"phase-{phase_key}-review-notes.md"
            notes_path.write_text(review_notes, encoding="utf-8")
            print(f"  💾 Review notes saved: {notes_path}")
    else:
        print(f"\n  ⚠ No review personas loaded — skipping review pipeline")

    elapsed = time.time() - start_time
    print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] ⏱  {phase_label} completed in {elapsed/60:.1f} minutes")
    cost_tracker.print_phase_summary(str(phase_key))

    # S73 Hidden Debt Fix: Update persistent Founder Memory with this phase's decisions
    # Incremental: generates only ~500 char delta vs. reprocessing all prior deliverables
    update_founder_memory_after_synthesis(
        deliverable_text=deliverable,
        phase_key=phase_key,
        cost_tracker=cost_tracker,
    )

    # Save phase metrics (D-188/D-194: review pipeline with timing)
    metrics = {
        "phase": str(phase_key),
        "status": "COMPLETED",
        "synthesis_attempts": 1,
        "exchanges": len([t for t in transcript if t["role"] == "founder"]),
        "deliverable_chars": len(deliverable),
        "review_model": REVIEW_MODEL,
        "elapsed_seconds": round(elapsed),
        "timestamp": datetime.now().isoformat(),
        "timing": {
            "conversation_seconds": round(conversation_elapsed),
            "synthesis_seconds": round(synthesis_elapsed),
            "review_pipeline_seconds": round(review_elapsed),
        },
    }
    metrics_path = METRICS_DIR / f"phase-{phase_key}-metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2))

    # S77 D-179: Push deliverables + metrics to GitHub immediately
    git_push_output(phase_key, f"{len(deliverable):,} chars, reviewed ({REVIEW_MODEL})")

    return deliverable


# ---------------------------------------------------------------------------
# S73 3g: CROSS-PHASE CONSISTENCY VALIDATOR
#
# After all phases complete, loads all deliverables and checks for naming
# conflicts, entity inconsistencies, and cross-phase contradictions that
# per-phase critics can't catch (they only see their own output + tail
# of prior phases).
# ---------------------------------------------------------------------------

def run_cross_phase_consistency_check(cost_tracker: CostTracker) -> dict:
    """
    Post-run consistency check across all deliverables.

    Loads every phase deliverable and uses Opus to identify:
    - Naming conflicts (same entity with different names across phases)
    - Feature ID inconsistencies
    - Technology/service selection contradictions
    - User role/persona naming mismatches
    - Architectural contradictions

    Returns dict with issues found. Does NOT block — informational only.
    """
    print(f"\n{'='*60}")
    print(f"  🔍 CROSS-PHASE CONSISTENCY CHECK")
    print(f"{'='*60}")

    # Load all deliverables
    all_deliverables = []
    for pk in PHASE_ORDER:
        deliv_path = DELIVERABLES_DIR / f"phase-{pk}-deliverable.md"
        if deliv_path.exists():
            text = deliv_path.read_text(encoding="utf-8")
            all_deliverables.append(f"<phase_{pk}_deliverable>\n{text}\n</phase_{pk}_deliverable>")

    if len(all_deliverables) < 2:
        print("  ⏭ Fewer than 2 deliverables found, skipping consistency check")
        return {"skipped": True, "reason": "insufficient deliverables"}

    combined = "\n\n".join(all_deliverables)
    print(f"  📄 Loaded {len(all_deliverables)} deliverables ({len(combined):,} chars)")

    consistency_prompt = (
        "You are a cross-phase consistency auditor. Below are all deliverables from a "
        "multi-phase platform planning process. Your job is to find CONTRADICTIONS and "
        "INCONSISTENCIES across phases.\n\n"
        "Check for:\n"
        "1. NAMING CONFLICTS: Same entity referred to by different names across phases "
        "(e.g., 'UserProfile' in Phase 3 but 'AccountProfile' in Phase 5)\n"
        "2. FEATURE ID MISMATCHES: Feature IDs that don't match between the feature "
        "catalog and later references\n"
        "3. TECHNOLOGY CONTRADICTIONS: Different technology choices for the same component "
        "(e.g., 'PostgreSQL' in Phase 4 but 'MongoDB' in Phase 5)\n"
        "4. USER ROLE INCONSISTENCIES: User personas or roles that change names or "
        "definitions between phases\n"
        "5. ARCHITECTURAL CONFLICTS: Design decisions that contradict earlier technical "
        "architecture (e.g., component counts, service boundaries, API patterns)\n\n"
        "Respond in JSON format ONLY (no markdown, no preamble):\n"
        '{"consistency_score": N, '
        '"naming_conflicts": [{"entity": "...", "phase_a": "...", "phase_b": "...", "description": "..."}], '
        '"technology_contradictions": [{"component": "...", "phase_a": "...", "phase_b": "...", "description": "..."}], '
        '"other_inconsistencies": [{"type": "...", "description": "..."}], '
        '"total_issues": N}\n\n'
        f"{combined}"
    )

    response = call_api(
        model=SYNTHESIS_MODEL,  # Opus — needs deep cross-referencing
        system=(
            "You are a meticulous cross-phase consistency auditor. "
            "Find every naming conflict, technology contradiction, and inconsistency. "
            "Output ONLY valid JSON, no preamble or markdown."
        ),
        messages=[{"role": "user", "content": consistency_prompt}],
        max_tokens=16_384,
        show_progress=True,
        cache_system=True,
    )
    cost_tracker.record_call("cross-phase", "consistency", SYNTHESIS_MODEL,
                             response["usage"], response.get("search_count", 0),
                             response.get("thinking_chars", 0))

    result_text = extract_text(response["content"])

    try:
        result = json.loads(result_text)
    except json.JSONDecodeError:
        print(f"  ⚠ Consistency check response not valid JSON")
        result = {"error": "unparseable", "raw": result_text[:500]}

    # Report results
    total = result.get("total_issues", 0)
    score = result.get("consistency_score", "?")
    naming = len(result.get("naming_conflicts", []))
    tech = len(result.get("technology_contradictions", []))
    other = len(result.get("other_inconsistencies", []))

    print(f"\n  Consistency Score: {score}/10")
    print(f"  Naming conflicts: {naming}")
    print(f"  Technology contradictions: {tech}")
    print(f"  Other inconsistencies: {other}")
    print(f"  Total issues: {total}")

    if naming > 0:
        print(f"\n  🔴 Naming conflicts found:")
        for nc in result.get("naming_conflicts", [])[:5]:
            print(f"     - {nc.get('entity', '?')}: {nc.get('description', '?')}")

    if tech > 0:
        print(f"\n  🔴 Technology contradictions found:")
        for tc in result.get("technology_contradictions", [])[:5]:
            print(f"     - {tc.get('component', '?')}: {tc.get('description', '?')}")

    # Save report
    report_path = METRICS_DIR / "cross-phase-consistency.json"
    report_path.write_text(json.dumps(result, indent=2))
    print(f"\n  💾 Consistency report saved: {report_path}")

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="PlatformForge Methodology Dry Run")
    parser.add_argument("--phase", type=str, default="1",
                        help="Start from this phase (default: 1). Use '6a' for sub-phases.")
    parser.add_argument("--max-exchanges", type=int, default=MAX_EXCHANGES,
                        help=f"Max conversation exchanges per phase (default: {MAX_EXCHANGES})")
    parser.add_argument("--max-phases", type=int, default=0,
                        help="Max number of phases to run (0 = all). Use 1 for Phase 1 only test.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print config and exit without making API calls")
    args = parser.parse_args()

    # Validate API key
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key and not args.dry_run:
        print("❌ ANTHROPIC_API_KEY not found!")
        print("   Option 1: Create a .env file next to main.py with:")
        print('     ANTHROPIC_API_KEY="sk-ant-..."')
        print('     PERPLEXITY_API_KEY="pplx-..."')
        print('     GROK_API_KEY="xai-..."')
        print("   Option 2: export ANTHROPIC_API_KEY='your-key-here'")
        sys.exit(1)

    if _env_loaded:
        print(f"📂 Loaded {_env_loaded} variable(s) from .env")

    # Setup
    setup_directories()

    # Determine starting phase
    start_key = args.phase
    if start_key.isdigit():
        start_key = int(start_key)
    if start_key not in PHASE_ORDER:
        print(f"❌ Invalid phase: {start_key}. Valid phases: {PHASE_ORDER}")
        sys.exit(1)

    start_index = PHASE_ORDER.index(start_key)
    phases_to_run = PHASE_ORDER[start_index:]
    if args.max_phases > 0:
        phases_to_run = phases_to_run[:args.max_phases]

    # S71 3.7: Check available research engines
    research_caps = check_research_capabilities()
    research_status = []
    if research_caps["web_search"]:
        research_status.append("web_search")
    if research_caps["perplexity"]:
        research_status.append("perplexity")
    if research_caps["grok"]:
        research_status.append("grok")
    research_str = " + ".join(research_status)

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║        PlatformForge Methodology Dry Run Orchestrator       ║
╠══════════════════════════════════════════════════════════════╣
║  Scenario:    Ocean Golf (Cabo luxury golf concierge)       ║
║  Guide:       {GUIDE_MODEL:<45s} ║
║  Founder:     {FOUNDER_MODEL:<45s} ║
║  Synthesis:   {SYNTHESIS_MODEL:<45s} ║
║  Review:      {REVIEW_MODEL:<45s} ║
║  Thinking:    Guide=adaptive/max, Synth=high, Founder=off   ║
║  Research:    {research_str:<45s} ║
║  Pipeline:    D-194 parallel (L1→[L2+L3+L4]→merge)         ║
║  Start Phase: {str(start_key):<45s} ║
║  Phases:      {str(phases_to_run):<45s} ║
║  Max Exch.:   {args.max_exchanges:<45d} ║
╚══════════════════════════════════════════════════════════════╝
""")

    if args.dry_run:
        print("🏁 Dry run — exiting without API calls.")
        return

    # Load master system prompt (used for every phase)
    print("📥 Loading master system prompt...")
    master_prompt = load_template("master-system-prompt.md")
    print(f"   Loaded: {len(master_prompt):,} chars ({len(master_prompt)/1024:.1f} KB)")

    # S71 3.1: Adapt master prompt for orchestrator mode
    # Replaces multi-engine research section with orchestrator-appropriate guidance
    # based on available research engines
    master_prompt = adapt_master_prompt_for_orchestrator(master_prompt, research_caps)

    # Load persona
    print("📥 Loading founder persona...")
    persona = load_persona()
    print(f"   Loaded: {len(persona):,} chars")

    # D-188: Load review personas from external files
    print("📥 Loading review personas...")
    review_personas = load_review_personas()

    # Initialize cost tracker
    cost_tracker = CostTracker()

    # D-194 3D: Run-level timing waterfall
    run_start = datetime.now()
    phase_timings = []

    # Run phases
    for phase_key in phases_to_run:
        # S73 3h: Cost ceiling — check before starting each phase
        if cost_tracker.total_cost >= MAX_RUN_COST_USD:
            print(f"\n🛑 Cost ceiling reached: ${cost_tracker.total_cost:.2f} >= ${MAX_RUN_COST_USD:.2f}")
            print(f"   Halting before Phase {phase_key}. Completed phases preserved.")
            print(f"   Adjust MAX_RUN_COST_USD ({MAX_RUN_COST_USD}) to increase limit.")
            cost_tracker.save_report()
            sys.exit(1)

        try:
            phase_t_start = time.time()
            run_phase(
                phase_key=phase_key,
                master_prompt=master_prompt,
                persona=persona,
                max_exchanges=args.max_exchanges,
                cost_tracker=cost_tracker,
                research_caps=research_caps,
                review_personas=review_personas,
            )
            # D-194 3D: Collect per-phase timing from metrics file
            phase_metrics_path = METRICS_DIR / f"phase-{phase_key}-metrics.json"
            pipeline_metrics_path = METRICS_DIR / f"phase-{phase_key}-review-pipeline.json"
            phase_timing_entry = {"phase": str(phase_key), "total_seconds": round(time.time() - phase_t_start)}
            if phase_metrics_path.exists():
                pm = json.loads(phase_metrics_path.read_text())
                phase_timing_entry.update(pm.get("timing", {}))
            if pipeline_metrics_path.exists():
                pp = json.loads(pipeline_metrics_path.read_text())
                phase_timing_entry["review_detail"] = pp.get("timing", {})
            phase_timings.append(phase_timing_entry)
        except KeyboardInterrupt:
            print(f"\n\n⚠ Interrupted during Phase {phase_key}!")
            cost_tracker.save_report()
            sys.exit(1)
        except Exception as e:
            print(f"\n\n[{datetime.now().strftime('%H:%M:%S')}] ❌ Error in Phase {phase_key}: {e}")
            traceback.print_exc()
            print("\n🛑 Halting run — subsequent phases depend on this deliverable.")
            print(f"   Fix the issue, then resume with: python3 main.py --phase {phase_key}")
            cost_tracker.save_report()
            git_push_output(f"{phase_key}-crash", f"halted — {type(e).__name__}")
            sys.exit(1)

    # S73 3g: Cross-phase consistency check — run if multiple phases completed
    completed_deliverables = list(DELIVERABLES_DIR.glob("phase-*-deliverable.md"))
    if len(completed_deliverables) >= 2:
        try:
            consistency = run_cross_phase_consistency_check(cost_tracker)
        except Exception as e:
            print(f"\n  ⚠ Cross-phase consistency check failed: {e}")
            print(f"     This is informational only — deliverables are still valid.")

    # D-194 3D: Write timing waterfall
    run_end = datetime.now()
    total_elapsed_hours = (run_end - run_start).total_seconds() / 3600
    waterfall = {
        "run_start": run_start.isoformat(),
        "run_end": run_end.isoformat(),
        "total_elapsed_hours": round(total_elapsed_hours, 2),
        "model": REVIEW_MODEL,
        "phases": phase_timings,
    }
    waterfall_path = METRICS_DIR / "timing-waterfall.json"
    waterfall_path.write_text(json.dumps(waterfall, indent=2))
    print(f"\n  💾 Timing waterfall saved: {waterfall_path}")

    # Final report
    cost_tracker.save_report()

    # S77 D-179: Final push to catch cost report + consistency check
    git_push_output("final", f"run complete — ${cost_tracker.total_cost:.2f} total")

    print(f"""
╔══════════════════════════════════════════════════════════════╗
║                    🎉 DRY RUN COMPLETE                      ║
╠══════════════════════════════════════════════════════════════╣
║  Conversations: {str(CONVERSATIONS_DIR):<43s} ║
║  Deliverables:  {str(DELIVERABLES_DIR):<43s} ║
║  Metrics:       {str(METRICS_DIR):<43s} ║
║  Total Cost:    ${cost_tracker.total_cost:<43.2f} ║
╚══════════════════════════════════════════════════════════════╝
""")


if __name__ == "__main__":
    main()
