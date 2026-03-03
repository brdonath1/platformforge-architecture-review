"""Tests for review_pipeline.py — Step 6."""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.contracts import (
    CallUsage,
    MessageResult,
    PatchEntry,
    PatchResult,
    PhaseKey,
    ReviewFinding,
    ReviewPipelineResult,
    RoleName,
)
from src.review_pipeline import (
    MAX_REENGAGEMENT_TOPICS,
    REENGAGEMENT_COMPLETE_MARKER,
    ReviewPipeline,
    _parse_persona_file,
    apply_patches,
    extract_role_from_persona,
    extract_xml_field,
    load_review_personas,
    parse_correction_patches,
    parse_review_findings_xml,
)
from src.run_store import CostLedger, RunStore
from src.settings import AppConfig, load_app_config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_result(
    text: str = "",
    role: RoleName = RoleName.L1,
    phase: PhaseKey = PhaseKey.P1,
    stop_reason: str = "end_turn",
) -> MessageResult:
    """Create a MessageResult with the given text."""
    return MessageResult(
        role=role,
        phase=phase,
        label="test",
        text=text,
        stop_reason=stop_reason,
        usage=CallUsage(
            role=role,
            model_id="test-model",
            input_tokens=100,
            output_tokens=50,
            cost_usd=Decimal("0.001"),
        ),
    )


def _make_pipeline(
    tmp_path: Path,
    gateway_mock: Any = None,
) -> tuple[ReviewPipeline, MagicMock]:
    """Create a ReviewPipeline with mocked gateway."""
    if gateway_mock is None:
        gateway_mock = MagicMock()
    store = RunStore(root=tmp_path)
    ledger = CostLedger(hard_ceiling_usd=Decimal("100"))
    config_path = Path(__file__).parent.parent.parent / "config.json"
    if config_path.exists():
        config = load_app_config(config_path)
    else:
        config = load_app_config()
    pipeline = ReviewPipeline(
        gateway=gateway_mock,
        store=store,
        ledger=ledger,
        config=config,
        persona="You are a test founder.",
        review_personas={"l2": {}, "l3": {}, "l4": "", "config": ""},
    )
    return pipeline, gateway_mock


# ===========================================================================
# Pure function tests — no mocking needed
# ===========================================================================


class TestParseReviewFindingsXml:
    def test_basic(self) -> None:
        xml = (
            "<findings>\n"
            "<finding>\n"
            "  <id>L2-1</id>\n"
            "  <category>must-fix</category>\n"
            "  <section>Pricing</section>\n"
            "  <issue>Missing pricing tiers</issue>\n"
            "  <evidence>Template requires tiers</evidence>\n"
            "  <recommendation>Add pricing tiers</recommendation>\n"
            "</finding>\n"
            "<finding>\n"
            "  <id>L2-2</id>\n"
            "  <category>should-improve</category>\n"
            "  <section>Architecture</section>\n"
            "  <issue>Vague description</issue>\n"
            "  <evidence>Section 3.1</evidence>\n"
            "  <recommendation>Elaborate</recommendation>\n"
            "</finding>\n"
            "<finding>\n"
            "  <id>L2-3</id>\n"
            "  <category>consider</category>\n"
            "  <section>UX</section>\n"
            "  <issue>Could add wireframes</issue>\n"
            "  <evidence>Best practice</evidence>\n"
            "  <recommendation>Add wireframes</recommendation>\n"
            "</finding>\n"
            "</findings>"
        )
        result = parse_review_findings_xml(xml, 2)
        assert len(result) == 3
        assert result[0].id == "L2-1"
        assert result[0].category == "must-fix"
        assert result[0].section == "Pricing"
        assert result[1].category == "should-improve"
        assert result[2].category == "consider"

    def test_none(self) -> None:
        result = parse_review_findings_xml("<findings>NONE</findings>", 2)
        assert result == []

    def test_empty(self) -> None:
        result = parse_review_findings_xml("", 2)
        assert result == []

    def test_normalizes_category(self) -> None:
        xml = (
            "<finding>\n"
            "  <id>L2-1</id>\n"
            "  <category>MUST-FIX</category>\n"
            "  <section>Test</section>\n"
            "  <issue>Test issue</issue>\n"
            "</finding>"
        )
        result = parse_review_findings_xml(xml, 2)
        assert len(result) == 1
        assert result[0].category == "must-fix"

    def test_invalid_category_defaults_to_consider(self) -> None:
        xml = (
            "<finding>\n"
            "  <id>L2-1</id>\n"
            "  <category>urgent</category>\n"
            "  <section>Test</section>\n"
            "  <issue>Test issue</issue>\n"
            "</finding>"
        )
        result = parse_review_findings_xml(xml, 2)
        assert len(result) == 1
        assert result[0].category == "consider"


class TestExtractXmlField:
    def test_basic(self) -> None:
        block = "<id>L2-1</id><section>Pricing</section>"
        assert extract_xml_field(block, "id") == "L2-1"
        assert extract_xml_field(block, "section") == "Pricing"

    def test_missing(self) -> None:
        assert extract_xml_field("<id>test</id>", "section") == ""


class TestParseCorrectionPatches:
    def test_basic(self) -> None:
        xml = (
            '<corrections>\n'
            '  <patch id="L2-1">\n'
            '    <action>replace</action>\n'
            '    <anchor>## Pricing</anchor>\n'
            '    <search_text>old text here</search_text>\n'
            '    <new_text>new text here</new_text>\n'
            '  </patch>\n'
            '  <patch id="L3-1">\n'
            '    <action>insert_after</action>\n'
            '    <anchor>## Architecture</anchor>\n'
            '    <search_text>after this</search_text>\n'
            '    <new_text>inserted content</new_text>\n'
            '  </patch>\n'
            '</corrections>'
        )
        patches = parse_correction_patches(xml)
        assert len(patches) == 2
        assert patches[0].id == "L2-1"
        assert patches[0].action == "replace"
        assert patches[0].anchor == "## Pricing"
        assert patches[0].search_text == "old text here"
        assert patches[0].new_text == "new text here"
        assert patches[1].id == "L3-1"
        assert patches[1].action == "insert_after"

    def test_malformed_new_text_tag(self) -> None:
        xml = (
            '<corrections>\n'
            '  <patch id="L2-1">\n'
            '    <action>replace</action>\n'
            '    <anchor>## Test</anchor>\n'
            '    <search_text>old</search_text>\n'
            '    <new_text>new content here</search_text>\n'
            '  </patch>\n'
            '</corrections>'
        )
        patches = parse_correction_patches(xml)
        assert len(patches) == 1
        assert patches[0].new_text == "new content here"


class TestApplyPatches:
    def test_replace(self) -> None:
        doc = "# Title\n\n## Section\n\nold content here\n"
        patches = [PatchEntry(
            id="P1", action="replace",
            search_text="old content here",
            new_text="new content here",
        )]
        result, log = apply_patches(doc, patches)
        assert "new content here" in result
        assert "old content here" not in result
        assert log[0].status == "applied"

    def test_replace_fuzzy(self) -> None:
        doc = "# Title\n\nold   content   here\n"
        patches = [PatchEntry(
            id="P1", action="replace",
            search_text="old content here",
            new_text="new content",
        )]
        result, log = apply_patches(doc, patches)
        assert log[0].status == "applied_fuzzy"

    def test_replace_ambiguous_with_anchor(self) -> None:
        doc = (
            "## Section A\n\nsome text\n\n"
            "## Section B\n\nsome text\n"
        )
        patches = [PatchEntry(
            id="P1", action="replace",
            anchor="## Section B",
            search_text="some text",
            new_text="new text",
        )]
        result, log = apply_patches(doc, patches)
        assert log[0].status == "applied_anchored"
        # Second occurrence should be replaced
        assert result.count("some text") == 1
        assert "new text" in result

    def test_replace_ambiguous_no_anchor(self) -> None:
        doc = "some text\nsome text\n"
        patches = [PatchEntry(
            id="P1", action="replace",
            search_text="some text",
            new_text="new",
        )]
        result, log = apply_patches(doc, patches)
        assert log[0].status == "skipped_ambiguous"

    def test_replace_empty_new_text_skipped(self) -> None:
        doc = "old content here"
        patches = [PatchEntry(
            id="P1", action="replace",
            search_text="old content here",
            new_text="",
        )]
        result, log = apply_patches(doc, patches)
        assert result == doc
        assert log[0].status == "skipped_empty_replacement"

    def test_insert_after(self) -> None:
        doc = "## Section\n\nmarker text\n\nmore content"
        patches = [PatchEntry(
            id="P1", action="insert_after",
            search_text="marker text",
            new_text="\nINSERTED",
        )]
        result, log = apply_patches(doc, patches)
        assert "marker text\nINSERTED" in result
        assert log[0].status == "applied"

    def test_insert_before(self) -> None:
        doc = "## Section\n\nmarker text\n"
        patches = [PatchEntry(
            id="P1", action="insert_before",
            search_text="marker text",
            new_text="BEFORE\n",
        )]
        result, log = apply_patches(doc, patches)
        assert result.index("BEFORE") < result.index("marker text")
        assert log[0].status == "applied"

    def test_append_to_section(self) -> None:
        doc = "## Section A\n\ncontent A\n\n## Section B\n\ncontent B\n"
        patches = [PatchEntry(
            id="P1", action="append_to_section",
            anchor="## Section A",
            new_text="APPENDED",
        )]
        result, log = apply_patches(doc, patches)
        assert "APPENDED" in result
        # Should be before Section B
        assert result.index("APPENDED") < result.index("## Section B")
        assert log[0].status == "applied"

    def test_unknown_action(self) -> None:
        doc = "test"
        patches = [PatchEntry(
            id="P1", action="delete",
            search_text="test",
            new_text="new",
        )]
        result, log = apply_patches(doc, patches)
        assert result == doc
        assert log[0].status == "skipped_unknown_action"


class TestExtractRoleFromPersona:
    def test_basic(self) -> None:
        text = "Some context\n**Role:** Senior Architect\n**Focus:** Design"
        assert extract_role_from_persona(text) == "Senior Architect"

    def test_fallback(self) -> None:
        assert extract_role_from_persona("no role here") == "Reviewer"


class TestParsePersonaFile:
    def test_basic(self) -> None:
        text = (
            "# Personas\n\n"
            "## Phase 1\n\nPhase 1 content\n\n"
            "## Phase 6a\n\nPhase 6a content\n"
        )
        result = _parse_persona_file(text)
        assert "1" in result
        assert "6a" in result
        assert "Phase 1 content" in result["1"]
        assert "Phase 6a content" in result["6a"]


class TestLoadReviewPersonas:
    def test_missing_files(self, tmp_path: Path) -> None:
        result = load_review_personas(tmp_path)
        assert isinstance(result["l2"], dict)
        assert isinstance(result["l3"], dict)
        assert result["l4"] == ""
        assert result["config"] == ""


# ===========================================================================
# ReviewPipeline tests — mocked gateway
# ===========================================================================


class TestL1Compliance:
    def test_pass(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result(
            '{"pass": true, "missing_items": []}'
        )
        result = pipeline._run_l1_compliance(
            PhaseKey.P1, "deliverable", "template"
        )
        assert result == []

    def test_fail(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result(
            '{"pass": false, "missing_items": ['
            '{"section": "Pricing", "detail": "Missing tiers"}'
            "]}"
        )
        result = pipeline._run_l1_compliance(
            PhaseKey.P1, "deliverable", "template"
        )
        assert len(result) == 1
        assert result[0].category == "must-fix"
        assert result[0].section == "Pricing"

    def test_json_parse_error(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result("not json at all")
        result = pipeline._run_l1_compliance(
            PhaseKey.P1, "deliverable", "template"
        )
        assert len(result) == 1
        assert result[0].section == "PARSE_ERROR"


class TestLayerReview:
    def test_basic(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        xml = (
            "<findings>\n"
            "<finding>\n"
            "  <id>L2-1</id>\n"
            "  <category>must-fix</category>\n"
            "  <section>Pricing</section>\n"
            "  <issue>Missing tiers</issue>\n"
            "  <evidence>Template</evidence>\n"
            "  <recommendation>Add</recommendation>\n"
            "</finding>\n"
            "<finding>\n"
            "  <id>L2-2</id>\n"
            "  <category>consider</category>\n"
            "  <section>UX</section>\n"
            "  <issue>Nice to have</issue>\n"
            "  <evidence>None</evidence>\n"
            "  <recommendation>Consider</recommendation>\n"
            "</finding>\n"
            "</findings>"
        )
        gw.run.return_value = _make_result(xml)
        result = pipeline._run_layer_review(
            PhaseKey.P1, 2, "deliverable", "template", "persona", ""
        )
        assert len(result) == 2
        assert result[0].category == "must-fix"

    def test_empty_response(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result("")
        result = pipeline._run_layer_review(
            PhaseKey.P1, 2, "deliverable", "template", "persona", ""
        )
        assert result == []


class TestCorrectionSynthesis:
    def test_basic(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        corrections_xml = (
            '<corrections>\n'
            '  <patch id="L2-1">\n'
            '    <action>replace</action>\n'
            '    <anchor>## Section</anchor>\n'
            '    <search_text>old text</search_text>\n'
            '    <new_text>new text</new_text>\n'
            '  </patch>\n'
            '</corrections>'
        )
        gw.run.return_value = _make_result(corrections_xml)
        findings = [ReviewFinding(
            id="L2-1", category="must-fix",
            section="Section", issue="Wrong text",
        )]
        deliverable = "# Doc\n\n## Section\n\nold text\n"
        result = pipeline._run_correction_synthesis(
            PhaseKey.P1, deliverable, findings
        )
        assert "new text" in result
        assert "old text" not in result

    def test_empty_response(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result("")
        findings = [ReviewFinding(
            id="L2-1", category="must-fix",
            section="Section", issue="Wrong",
        )]
        result = pipeline._run_correction_synthesis(
            PhaseKey.P1, "original text", findings
        )
        assert result == "original text"

    def test_no_must_fix(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        findings = [ReviewFinding(
            id="L2-1", category="should-improve",
            section="Section", issue="Vague",
        )]
        result = pipeline._run_correction_synthesis(
            PhaseKey.P1, "original text", findings
        )
        assert result == "original text"
        gw.run.assert_not_called()


class TestBuildInterviewBrief:
    def test_basic(self, tmp_path: Path) -> None:
        pipeline, _ = _make_pipeline(tmp_path)
        l2 = [ReviewFinding(
            id="L2-1", category="should-improve",
            section="Arch", issue="Vague", evidence="Section 3",
            recommendation="Elaborate",
        )]
        l4 = [ReviewFinding(
            id="L4-1", category="should-improve",
            section="UX", issue="Confusing", evidence="Page 5",
            recommendation="Simplify",
        )]
        result = pipeline._build_interview_brief(
            PhaseKey.P1, l2, [], l4
        )
        assert "<interview_brief" in result
        assert "topic_group" in result
        assert "SI-1-L2-1" in result
        assert "SI-1-L4-1" in result

    def test_empty(self, tmp_path: Path) -> None:
        pipeline, _ = _make_pipeline(tmp_path)
        result = pipeline._build_interview_brief(
            PhaseKey.P1, [], [], []
        )
        assert result == ""

    def test_caps_topics(self, tmp_path: Path) -> None:
        pipeline, _ = _make_pipeline(tmp_path)
        many = [
            ReviewFinding(
                id=f"L2-{i}", category="should-improve",
                section=f"S{i}", issue=f"Issue {i}",
            )
            for i in range(15)
        ]
        result = pipeline._build_interview_brief(
            PhaseKey.P1, many, [], []
        )
        topic_count = result.count("<topic id=")
        assert topic_count == MAX_REENGAGEMENT_TOPICS


class TestFounderReengagement:
    def test_basic(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        # Guide opens → founder responds → guide completes
        gw.run.side_effect = [
            _make_result("Hello founder, let's discuss."),  # guide opens
            _make_result("Here are my answers."),  # founder responds
            _make_result(
                f"Thank you. {REENGAGEMENT_COMPLETE_MARKER}"
            ),  # guide completes
        ]
        result = pipeline._run_founder_reengagement(
            PhaseKey.P1, "<interview_brief>test</interview_brief>"
        )
        assert len(result) >= 1
        assert result[0]["topic_id"] == "combined"
        # Transcript should be saved
        transcript_path = (
            tmp_path / "output" / "conversations"
            / "phase-1-reengagement.json"
        )
        assert transcript_path.exists()


class TestTargetedUpdate:
    def test_basic(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result(
            "# Updated Doc\n\nUpdated content here."
        )
        result = pipeline._run_targeted_update(
            PhaseKey.P1,
            "# Original Doc\n\nOriginal content here.",
            "<brief>test</brief>",
            [{"topic_id": "combined", "response": "my answer"}],
        )
        assert "Updated content" in result

    def test_size_safety(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        gw.run.return_value = _make_result("tiny")
        original = "# Doc\n\n" + "x" * 1000
        result = pipeline._run_targeted_update(
            PhaseKey.P1, original,
            "<brief>test</brief>",
            [{"topic_id": "combined", "response": "my answer"}],
        )
        assert result == original


class TestBuildReviewNotes:
    def test_basic(self, tmp_path: Path) -> None:
        findings = [
            ReviewFinding(
                id="L2-5", category="consider",
                section="Design", issue="Could add diagrams",
                evidence="N/A", recommendation="Add diagrams",
            ),
        ]
        result = ReviewPipeline._build_review_notes(
            findings, [], [], PhaseKey.P1
        )
        assert "Consider Items" in result
        assert "L2-5" in result
        assert "Could add diagrams" in result


class TestRunFullPipeline:
    def test_no_findings(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        # L1 pass, then L2/L3/L4 all NONE
        gw.run.return_value = _make_result(
            '{"pass": true, "missing_items": []}'
        )
        # Override for L2/L3/L4 — they return NONE
        call_count = 0

        def side_effect(job: Any) -> MessageResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # L1
                return _make_result('{"pass": true, "missing_items": []}')
            # L2/L3/L4
            return _make_result("<findings>NONE</findings>")

        gw.run.side_effect = side_effect

        result = pipeline.run(
            PhaseKey.P1, "# Doc\n\nContent.", "template", ""
        )
        assert isinstance(result, ReviewPipelineResult)
        assert result.deliverable_text == "# Doc\n\nContent."
        assert result.total_must_fix == 0
        assert not result.reengagement_triggered

    def test_with_must_fix(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        call_count = 0

        def side_effect(job: Any) -> MessageResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Initial L1 pass
                return _make_result('{"pass": true, "missing_items": []}')
            elif call_count <= 4:
                # L2 returns must-fix, L3/L4 return NONE
                if "L2" in job.label:
                    return _make_result(
                        "<findings><finding>"
                        "<id>L2-1</id>"
                        "<category>must-fix</category>"
                        "<section>Pricing</section>"
                        "<issue>Missing tiers</issue>"
                        "<evidence>Template</evidence>"
                        "<recommendation>Add tiers</recommendation>"
                        "</finding></findings>"
                    )
                return _make_result("<findings>NONE</findings>")
            elif call_count == 5:
                # Correction synthesis
                return _make_result(
                    '<corrections>'
                    '<patch id="L2-1">'
                    '<action>replace</action>'
                    '<anchor>## Pricing</anchor>'
                    '<search_text>basic pricing</search_text>'
                    '<new_text>tiered pricing model</new_text>'
                    '</patch>'
                    '</corrections>'
                )
            else:
                # Post-correction L1
                return _make_result('{"pass": true, "missing_items": []}')

        gw.run.side_effect = side_effect

        result = pipeline.run(
            PhaseKey.P1,
            "# Doc\n\n## Pricing\n\nbasic pricing\n",
            "template",
            "",
        )
        assert isinstance(result, ReviewPipelineResult)
        assert result.total_must_fix >= 1

    def test_with_reengagement(self, tmp_path: Path) -> None:
        pipeline, gw = _make_pipeline(tmp_path)
        call_count = 0

        def side_effect(job: Any) -> MessageResult:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Initial L1
                return _make_result('{"pass": true, "missing_items": []}')
            elif call_count <= 4:
                # L2 returns should-improve, L3/L4 NONE
                if "L2" in job.label:
                    return _make_result(
                        "<findings><finding>"
                        "<id>L2-1</id>"
                        "<category>should-improve</category>"
                        "<section>Pricing</section>"
                        "<issue>Vague pricing</issue>"
                        "<evidence>Section 2</evidence>"
                        "<recommendation>Ask founder about tiers</recommendation>"
                        "</finding></findings>"
                    )
                return _make_result("<findings>NONE</findings>")
            elif call_count == 5:
                # Guide opens reengagement
                return _make_result("Hello, I'd like to discuss pricing.")
            elif call_count == 6:
                # Founder responds
                return _make_result("We charge $50/month per course.")
            elif call_count == 7:
                # Guide completes
                return _make_result(
                    f"Great, thank you. {REENGAGEMENT_COMPLETE_MARKER}"
                )
            elif call_count == 8:
                # Targeted update
                return _make_result(
                    "# Doc\n\n## Pricing\n\n$50/month per course.\n" + "x" * 100
                )
            else:
                # Final L1
                return _make_result('{"pass": true, "missing_items": []}')

        gw.run.side_effect = side_effect

        result = pipeline.run(
            PhaseKey.P1,
            "# Doc\n\n## Pricing\n\nSome pricing.\n" + "x" * 100,
            "template",
            "",
        )
        assert result.reengagement_triggered
