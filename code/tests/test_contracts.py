"""Tests for contracts.py -- all shared types and helper functions."""

import pytest
from src.contracts import (
    CanonicalFact,
    DeliverableArtifact,
    MessageJob,
    PhaseKey,
    PhaseTemplateSpec,
    RequiredElement,
    RoleName,
    SectionSpec,
    fact_key,
    phase_key,
    role_name,
    section_hash,
)


class TestPhaseKey:
    VALID = ["1","2","3","4","5","6a","6b","6c","7","8","9","10"]

    def test_count(self):
        assert len(PhaseKey) == 12

    @pytest.mark.parametrize("v", VALID)
    def test_from_string(self, v):
        r = phase_key(v)
        assert isinstance(r, PhaseKey)
        assert r.value == v

    def test_from_int(self):
        assert phase_key(1) == PhaseKey.P1

    def test_case_insensitive(self):
        assert phase_key("6A") == PhaseKey.P6A

    def test_strips_whitespace(self):
        assert phase_key("  3  ") == PhaseKey.P3

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid phase key"):
            phase_key("11")

    def test_empty_raises(self):
        with pytest.raises(ValueError):
            phase_key("")


class TestRoleName:
    VALID = ["guide","founder","synthesis","l1","l2","l3","l4","correction","consistency"]

    def test_count(self):
        assert len(RoleName) == 9

    @pytest.mark.parametrize("v", VALID)
    def test_from_string(self, v):
        r = role_name(v)
        assert isinstance(r, RoleName)
        assert r.value == v

    def test_case_insensitive(self):
        assert role_name("GUIDE") == RoleName.GUIDE

    def test_strips_whitespace(self):
        assert role_name("  founder  ") == RoleName.FOUNDER

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid role name"):
            role_name("unknown")


class TestFactKey:
    def test_basic_format(self):
        assert fact_key("pricing","sub","cost") == "pricing:sub.cost"

    def test_parts(self):
        r = fact_key("a","b","c")
        assert ":" in r and "." in r


class TestSectionHash:
    def test_deterministic(self):
        t = "# Hello\nContent"
        assert section_hash(t) == section_hash(t)

    def test_strips_whitespace(self):
        assert section_hash("  hello  ") == section_hash("hello")

    def test_normalizes_crlf(self):
        assert section_hash("a\nb") == section_hash("a\r\nb")
        assert section_hash("a\nb") == section_hash("a\rb")

    def test_hex_64(self):
        r = section_hash("test")
        assert len(r) == 64
        assert all(c in "0123456789abcdef" for c in r)

    def test_different_content(self):
        assert section_hash("hello") != section_hash("world")


class TestCanonicalFact:
    def test_string_value(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value="v",source_phase=PhaseKey.P1)
        assert f.value == "v"

    def test_int_value(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value=42,source_phase=PhaseKey.P2)
        assert f.value == 42

    def test_float_value(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value=9.99,source_phase=PhaseKey.P3)
        assert f.value == 9.99

    def test_list_value(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value=["x","y"],source_phase=PhaseKey.P4)
        assert f.value == ["x","y"]

    def test_dict_value(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value={"k":"v"},source_phase=PhaseKey.P5)
        assert isinstance(f.value, dict)

    def test_default_confidence(self):
        f = CanonicalFact(namespace="n",subject="s",attribute="a",value="v",source_phase=PhaseKey.P1)
        assert f.confidence == 1.0

    def test_confidence_bounds(self):
        with pytest.raises(Exception):
            CanonicalFact(namespace="n",subject="s",attribute="a",value="v",source_phase=PhaseKey.P1,confidence=1.5)


class TestModels:
    def test_required_element(self):
        e = RequiredElement(name="t",description="d")
        assert e.validation_rule == ""

    def test_section_spec(self):
        s = SectionSpec(section_id="s1",title="Intro")
        assert s.depends_on_fact_keys == []

    def test_phase_template_spec(self):
        p = PhaseTemplateSpec(phase=PhaseKey.P1,deliverable_name="Overview")
        assert p.sections == []

    def test_deliverable_artifact(self):
        a = DeliverableArtifact(phase=PhaseKey.P1,deliverable_name="D",markdown_content="# T",section_hashes={"s1":"h"})
        assert a.section_hashes == {"s1":"h"}
        assert a.fact_keys_used == []

    def test_message_job(self):
        j = MessageJob(role=RoleName.GUIDE,phase=PhaseKey.P1,label="test")
        assert j.role == RoleName.GUIDE
