"""
Tests for template_parser.py

Tests run against REAL templates where available, with synthetic
fallbacks for environments without the full repo.

Decision Authority: D-196, D-197
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from src.contracts import (
    PhaseKey,
    PhaseTemplateSpec,
    RawTemplateBundle,
    RequiredElement,
    SectionSpec,
)
from src.template_parser import (
    TEMPLATE_FILE_MAP,
    build_required_element_index,
    load_phase_template,
    parse_phase_template,
    _extract_tag_content,
    _parse_completion_gate,
    _strip_code_blocks,
)

# ---------------------------------------------------------------------------
# Template root resolution
# ---------------------------------------------------------------------------

# Real templates: relative to this test file -> dry-run/output/templates_cache/
_REAL_TEMPLATE_ROOT = (
    Path(__file__).resolve().parent.parent.parent / "templates_cache"
)

# Synthetic templates: for CI/container environments
_SYNTH_TEMPLATE_ROOT = Path(__file__).resolve().parent / "fixtures" / "templates"

HAS_REAL_TEMPLATES = _REAL_TEMPLATE_ROOT.exists() and (
    _REAL_TEMPLATE_ROOT / "phase-2-users.md"
).exists()


def get_template_root() -> Path:
    """Return the best available template root."""
    if HAS_REAL_TEMPLATES:
        return _REAL_TEMPLATE_ROOT
    return _SYNTH_TEMPLATE_ROOT


# Create synthetic templates for fallback testing
def _ensure_synthetic_templates() -> None:
    """Create minimal synthetic templates if they don't exist."""
    root = _SYNTH_TEMPLATE_ROOT
    root.mkdir(parents=True, exist_ok=True)

    # Phase 1 conversation
    conv = root / "phase-1-conversation.md"
    if not conv.exists():
        conv.write_text(
            "# PlatformForge — Phase 1: Vision & Opportunity\n\n"
            "<phase_conversation_structure>\n"
            "Talk about the idea.\n"
            "</phase_conversation_structure>\n",
            encoding="utf-8",
        )

    # Phase 1 synthesis
    synth = root / "phase-1-synthesis.md"
    if not synth.exists():
        synth.write_text(
            "# PlatformForge — Phase 1: Synthesis & Output\n\n"
            "<phase_completion_gate>\n"
            "- [ ] **Core problem defined.** Description here.\n"
            "- [ ] **Target audience identified.** Must be specific.\n"
            "</phase_completion_gate>\n\n"
            "<phase_outputs>\n"
            "**1. Platform Vision Document**\n"
            "The master document.\n\n"
            "**2. Glossary**\n"
            "Terms defined.\n"
            "</phase_outputs>\n",
            encoding="utf-8",
        )

    # Phase 2 combined
    p2 = root / "phase-2-users.md"
    if not p2.exists():
        p2.write_text(
            "# PlatformForge — Phase 2: User Universe Mapping\n\n"
            "<phase_role>\nYou are a researcher.\n</phase_role>\n\n"
            "<phase_conversation_structure>\n"
            "Map users.\n"
            "</phase_conversation_structure>\n\n"
            "<!-- CONVERSATION_END -->\n"
            "<!-- SYNTHESIS_START: Phase 2 synthesis -->\n\n"
            "<phase_completion_gate>\n"
            "- [ ] **User roles mapped.** All roles identified.\n"
            "- [ ] **Permissions defined.** RBAC documented.\n"
            "- [ ] **Lifecycles described.** For each role.\n"
            "</phase_completion_gate>\n\n"
            "<phase_outputs>\n"
            "**1. User Role Matrix**\n"
            "The complete matrix.\n\n"
            "**2. Permission Model**\n"
            "RBAC tables.\n\n"
            "**3. Lifecycle Maps**\n"
            "Per-role flows.\n"
            "</phase_outputs>\n",
            encoding="utf-8",
        )


# Ensure synthetics exist at import time
_ensure_synthetic_templates()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def template_root() -> Path:
    return get_template_root()


# ===========================================================================
# LOADING TESTS
# ===========================================================================

class TestLoadPhaseTemplate:
    """Test load_phase_template() file loading."""

    def test_load_phase_1_separate_files(self, template_root: Path) -> None:
        """Phase 1 loads two files; both raw fields non-empty."""
        bundle = load_phase_template(template_root, PhaseKey.P1)
        assert bundle.conversation_raw != ""
        assert bundle.synthesis_raw != ""
        assert len(bundle.source_paths) == 2

    def test_load_phase_2_combined_file(self, template_root: Path) -> None:
        """Phase 2 loads one file; splits on SYNTHESIS_START."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert bundle.conversation_raw != ""
        assert bundle.synthesis_raw != ""
        assert len(bundle.source_paths) == 1

    @pytest.mark.skipif(
        not HAS_REAL_TEMPLATES,
        reason="Real templates not available",
    )
    def test_load_all_phases(self, template_root: Path) -> None:
        """All 12 phases load successfully."""
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            assert bundle.phase == pk
            assert bundle.synthesis_raw != "" or bundle.conversation_raw != ""

    def test_load_missing_file_raises(self) -> None:
        """Non-existent template_root raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_phase_template(Path("/nonexistent/path"), PhaseKey.P2)

    def test_load_source_paths_recorded(self, template_root: Path) -> None:
        """source_paths contains correct file paths."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert len(bundle.source_paths) >= 1
        assert "phase-2" in bundle.source_paths[0]

    def test_load_phase_key_preserved(self, template_root: Path) -> None:
        """Bundle phase matches requested phase."""
        bundle = load_phase_template(template_root, PhaseKey.P5)
        assert bundle.phase == PhaseKey.P5


# ===========================================================================
# SYNTHESIS_START SPLITTING TESTS
# ===========================================================================

class TestSynthesisSplit:
    """Test SYNTHESIS_START marker splitting."""

    def test_split_phase_2_has_conversation(self, template_root: Path) -> None:
        """Combined template: conversation_raw is non-empty."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert len(bundle.conversation_raw) > 100

    def test_split_phase_2_has_synthesis(self, template_root: Path) -> None:
        """Combined template: synthesis_raw is non-empty."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert len(bundle.synthesis_raw) > 100

    def test_split_conversation_excludes_marker(
        self, template_root: Path
    ) -> None:
        """conversation_raw does NOT contain SYNTHESIS_START."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert "SYNTHESIS_START" not in bundle.conversation_raw

    def test_split_synthesis_excludes_conversation_end(
        self, template_root: Path
    ) -> None:
        """synthesis_raw does NOT contain CONVERSATION_END."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        assert "CONVERSATION_END" not in bundle.synthesis_raw

    def test_phase_1_no_synthesis_start_in_conversation(
        self, template_root: Path
    ) -> None:
        """Phase 1 conversation file has no SYNTHESIS_START."""
        bundle = load_phase_template(template_root, PhaseKey.P1)
        assert "SYNTHESIS_START" not in bundle.conversation_raw


# ===========================================================================
# PARSING TESTS
# ===========================================================================

class TestParsePhaseTemplate:
    """Test parse_phase_template() structured extraction."""

    def test_parse_phase_title(self, template_root: Path) -> None:
        """deliverable_name extracted from first '# ' line."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        assert "Phase 2" in spec.deliverable_name or "User" in spec.deliverable_name

    def test_parse_completion_gate_not_empty(
        self, template_root: Path
    ) -> None:
        """All phases have at least 1 completion gate item."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        assert len(spec.completion_gate) >= 1

    @pytest.mark.skipif(
        not HAS_REAL_TEMPLATES,
        reason="Real templates not available",
    )
    def test_parse_output_sections_phase_5(
        self, template_root: Path
    ) -> None:
        """Phase 5 produces 8 sections for its numbered deliverables."""
        bundle = load_phase_template(template_root, PhaseKey.P5)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) == 8

    def test_parse_output_sections_phase_2(
        self, template_root: Path
    ) -> None:
        """Phase 2 produces at least 1 section."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 1

    @pytest.mark.skipif(
        not HAS_REAL_TEMPLATES,
        reason="Real templates not available",
    )
    def test_parse_all_phases_have_sections(
        self, template_root: Path
    ) -> None:
        """Every phase produces at least 1 SectionSpec."""
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            spec = parse_phase_template(bundle)
            assert len(spec.sections) >= 1, (
                f"Phase {pk.value} has no sections"
            )

    @pytest.mark.skipif(
        not HAS_REAL_TEMPLATES,
        reason="Real templates not available",
    )
    def test_parse_all_phases_have_gates(
        self, template_root: Path
    ) -> None:
        """Every phase has at least 1 completion gate item."""
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            spec = parse_phase_template(bundle)
            assert len(spec.completion_gate) >= 1, (
                f"Phase {pk.value} has no gate items"
            )

    def test_parse_conversation_instructions_stored(
        self, template_root: Path
    ) -> None:
        """conversation_instructions field is populated."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        assert len(spec.conversation_instructions) > 0

    def test_parse_synthesis_instructions_stored(
        self, template_root: Path
    ) -> None:
        """synthesis_instructions field is populated."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        assert len(spec.synthesis_instructions) > 0


# ===========================================================================
# SECTION ID STABILITY TESTS
# ===========================================================================

class TestSectionIdStability:
    """Test section ID determinism and format."""

    def test_section_ids_deterministic(self, template_root: Path) -> None:
        """Parsing twice produces identical section_ids."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec1 = parse_phase_template(bundle)
        spec2 = parse_phase_template(bundle)
        ids1 = [s.section_id for s in spec1.sections]
        ids2 = [s.section_id for s in spec2.sections]
        assert ids1 == ids2

    def test_section_ids_format(self, template_root: Path) -> None:
        """All section_ids match pattern '{phase}-s{N}'."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        pattern = re.compile(r"^[a-z0-9]+-s\d+$")
        for sec in spec.sections:
            assert pattern.match(sec.section_id), (
                f"Bad format: {sec.section_id}"
            )

    def test_section_ids_unique_within_phase(
        self, template_root: Path
    ) -> None:
        """No duplicate section_ids within a phase."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        ids = [s.section_id for s in spec.sections]
        assert len(ids) == len(set(ids))

    @pytest.mark.skipif(
        not HAS_REAL_TEMPLATES,
        reason="Real templates not available",
    )
    def test_section_ids_unique_across_all_phases(
        self, template_root: Path
    ) -> None:
        """No duplicate section_ids across ALL phases."""
        all_ids: list[str] = []
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            spec = parse_phase_template(bundle)
            all_ids.extend(s.section_id for s in spec.sections)
        assert len(all_ids) == len(set(all_ids))

    def test_section_ids_lowercase(self, template_root: Path) -> None:
        """Section IDs are lowercase."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        for sec in spec.sections:
            assert sec.section_id == sec.section_id.lower()


# ===========================================================================
# REQUIRED ELEMENT TESTS
# ===========================================================================

class TestRequiredElements:
    """Test required element construction."""

    def test_required_elements_from_gate(
        self, template_root: Path
    ) -> None:
        """Completion gate items produce RequiredElement objects."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        # Gate items + section items
        gate_count = len(spec.completion_gate)
        section_count = len(spec.sections)
        assert len(spec.required_elements) == gate_count + section_count

    def test_required_elements_include_sections(
        self, template_root: Path
    ) -> None:
        """Each section generates a section-kind required element."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        section_elements = [
            e for e in spec.required_elements
            if e.name.startswith("Section: ")
        ]
        assert len(section_elements) == len(spec.sections)

    def test_build_required_element_index_matches_spec(
        self, template_root: Path
    ) -> None:
        """build_required_element_index() returns same as spec.required_elements."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        index = build_required_element_index(spec)
        assert len(index) == len(spec.required_elements)
        for a, b in zip(index, spec.required_elements):
            assert a.name == b.name

    def test_required_element_has_description(
        self, template_root: Path
    ) -> None:
        """All required elements have non-empty descriptions."""
        bundle = load_phase_template(template_root, PhaseKey.P2)
        spec = parse_phase_template(bundle)
        for elem in spec.required_elements:
            assert elem.description != ""


# ===========================================================================
# EDGE CASE TESTS
# ===========================================================================

class TestEdgeCases:
    """Test defensive parsing behavior."""

    def test_parse_empty_bundle(self) -> None:
        """Empty bundle produces valid but minimal PhaseTemplateSpec."""
        bundle = RawTemplateBundle(
            phase=PhaseKey.P2,
            conversation_raw="",
            synthesis_raw="",
        )
        spec = parse_phase_template(bundle)
        assert spec.phase == PhaseKey.P2
        assert spec.deliverable_name == "Untitled Phase"
        assert spec.completion_gate == []
        assert len(spec.sections) == 1  # fallback section
        assert spec.sections[0].section_id == "2-s0"

    def test_parse_missing_phase_outputs_tag(self) -> None:
        """Missing <phase_outputs> produces a single fallback section."""
        bundle = RawTemplateBundle(
            phase=PhaseKey.P3,
            synthesis_raw="# Phase 3\n\nSome content, no outputs tag.\n",
        )
        spec = parse_phase_template(bundle)
        assert len(spec.sections) == 1
        assert spec.sections[0].section_id == "3-s0"
        assert spec.sections[0].title == "Complete Deliverable"

    def test_parse_missing_completion_gate_tag(self) -> None:
        """Missing <phase_completion_gate> produces empty gate list."""
        bundle = RawTemplateBundle(
            phase=PhaseKey.P4,
            synthesis_raw="# Phase 4\n\n<phase_outputs>\n**1. ERD**\nDiagram.\n</phase_outputs>\n",
        )
        spec = parse_phase_template(bundle)
        assert spec.completion_gate == []
        assert len(spec.sections) >= 1


# ===========================================================================
# TAG EXTRACTION UNIT TESTS
# ===========================================================================

class TestExtractTagContent:
    """Test _extract_tag_content() helper."""

    def test_extract_basic(self) -> None:
        """Extracts content between tags."""
        text = "before <my_tag>inner content</my_tag> after"
        result = _extract_tag_content(text, "my_tag")
        assert result == "inner content"

    def test_extract_missing_tag(self) -> None:
        """Returns empty string for missing tag."""
        text = "no tags here"
        result = _extract_tag_content(text, "nonexistent")
        assert result == ""

    def test_extract_multiline(self) -> None:
        """Handles multiline content correctly."""
        text = "<phase_gate>\nline 1\nline 2\nline 3\n</phase_gate>"
        result = _extract_tag_content(text, "phase_gate")
        assert "line 1" in result
        assert "line 3" in result

    def test_extract_first_occurrence_only(self) -> None:
        """Only first tag occurrence is extracted."""
        text = "<tag>first</tag> <tag>second</tag>"
        result = _extract_tag_content(text, "tag")
        assert result == "first"


# ===========================================================================
# CODE BLOCK STRIPPING
# ===========================================================================

class TestStripCodeBlocks:
    """Test _strip_code_blocks() helper."""

    def test_strips_fenced_blocks(self) -> None:
        text = "before\n```\ncode line\n```\nafter"
        result = _strip_code_blocks(text)
        assert "code line" not in result
        assert "before" in result
        assert "after" in result

    def test_preserves_non_code(self) -> None:
        text = "line 1\nline 2\nline 3"
        result = _strip_code_blocks(text)
        assert result == text

    def test_handles_labeled_fences(self) -> None:
        text = "before\n```python\nprint('hi')\n```\nafter"
        result = _strip_code_blocks(text)
        assert "print" not in result


# ===========================================================================
# COMPLETION GATE PARSING
# ===========================================================================

class TestParseCompletionGate:
    """Test _parse_completion_gate() helper."""

    def test_parses_checkbox_items(self) -> None:
        text = (
            "- [ ] **Item one.** Description.\n"
            "- [ ] **Item two.** More text.\n"
        )
        items = _parse_completion_gate(text)
        assert len(items) == 2
        assert "Item one." in items[0]
        assert "Item two." in items[1]

    def test_strips_bold_markers(self) -> None:
        text = "- [ ] **Bold title.** Rest of text.\n"
        items = _parse_completion_gate(text)
        assert items[0].startswith("Bold title.")

    def test_empty_input(self) -> None:
        assert _parse_completion_gate("") == []

    def test_multiline_item(self) -> None:
        text = (
            "- [ ] **Item one.** Start of desc\n"
            "  continuation of desc.\n"
            "- [ ] **Item two.** Another.\n"
        )
        items = _parse_completion_gate(text)
        assert len(items) == 2
        assert "continuation" in items[0]


# ===========================================================================
# REAL TEMPLATE INTEGRATION TESTS
# ===========================================================================

@pytest.mark.skipif(
    not HAS_REAL_TEMPLATES,
    reason="Real templates not available",
)
class TestRealTemplateIntegration:
    """Integration tests against real templates."""

    def test_phase_5_has_8_sections(self, template_root: Path) -> None:
        bundle = load_phase_template(template_root, PhaseKey.P5)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) == 8

    def test_phase_6a_uses_sub_completion_gate(
        self, template_root: Path
    ) -> None:
        """Phase 6a has no phase_completion_gate, uses sub_phase_completion_gate."""
        bundle = load_phase_template(template_root, PhaseKey.P6A)
        spec = parse_phase_template(bundle)
        assert len(spec.completion_gate) >= 10

    def test_phase_6c_has_deliverable_sections(
        self, template_root: Path
    ) -> None:
        """Phase 6c uses Deliverable+Section format, produces many sections."""
        bundle = load_phase_template(template_root, PhaseKey.P6C)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 15

    def test_phase_7_section_format(self, template_root: Path) -> None:
        """Phase 7 uses Section N — Title format."""
        bundle = load_phase_template(template_root, PhaseKey.P7)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 10

    def test_phase_8_deliverable_format(
        self, template_root: Path
    ) -> None:
        """Phase 8 uses Deliverable N: Title format."""
        bundle = load_phase_template(template_root, PhaseKey.P8)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 8

    def test_phase_9_has_sections(self, template_root: Path) -> None:
        """Phase 9 has at least 1 section (Validation Report)."""
        bundle = load_phase_template(template_root, PhaseKey.P9)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 1
        assert any("Validation" in s.title for s in spec.sections)

    def test_phase_10_has_sections(self, template_root: Path) -> None:
        """Phase 10 has at least 1 section (Build Handoff)."""
        bundle = load_phase_template(template_root, PhaseKey.P10)
        spec = parse_phase_template(bundle)
        assert len(spec.sections) >= 1

    def test_all_phases_output_artifacts_match_sections(
        self, template_root: Path
    ) -> None:
        """output_artifacts count <= sections count for all phases.

        Artifact names correspond to top-level deliverables;
        sections include sub-sections within deliverables.
        """
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            spec = parse_phase_template(bundle)
            assert len(spec.output_artifacts) <= len(spec.sections), (
                f"Phase {pk.value}: more artifacts ({len(spec.output_artifacts)}) "
                f"than sections ({len(spec.sections)})"
            )

    def test_no_phase_has_empty_title(self, template_root: Path) -> None:
        """Every phase has a non-empty deliverable_name."""
        for pk in PhaseKey:
            bundle = load_phase_template(template_root, pk)
            spec = parse_phase_template(bundle)
            assert spec.deliverable_name != ""
            assert spec.deliverable_name != "Untitled Phase"
