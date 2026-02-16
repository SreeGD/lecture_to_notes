"""
Level 1: Schema validation tests for Agent 03 (Enrichment).

Tests Pydantic model constraints without any I/O or LLM calls.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lecture_agents.schemas.enrichment_output import (
    EnrichedNotes,
    GlossaryEntry,
    Reference,
    ThematicIndex,
    ThematicTag,
    VerificationResult,
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_reference(**overrides) -> Reference:
    defaults = {
        "scripture": "BG",
        "chapter": "2",
        "verse": "47",
        "canonical_ref": "BG 2.47",
        "segment_index": 0,
        "context_text": "Krishna says in the Bhagavad-gita chapter 2 verse 47",
    }
    return Reference(**(defaults | overrides))


def _make_verification(**overrides) -> VerificationResult:
    defaults = {
        "reference": _make_reference(),
        "status": "verified",
        "vedabase_url": "https://vedabase.io/en/library/bg/2/47/",
        "translation": "You have a right to perform your prescribed duty...",
        "verse_text": "karmany evadhikaras te",
    }
    return VerificationResult(**(defaults | overrides))


def _make_glossary(**overrides) -> GlossaryEntry:
    defaults = {
        "term": "bhakti",
        "definition": "Devotional service to the Supreme Lord.",
        "category": "philosophical",
        "source": "BG Glossary",
    }
    return GlossaryEntry(**(defaults | overrides))


def _make_thematic_index(**overrides) -> ThematicIndex:
    defaults = {
        "themes": [ThematicTag(
            tag="Devotional Service",
            confidence=0.8,
            evidence="Keywords: bhakti, devotion, service",
        )],
        "primary_topic": "Devotional Service (Bhakti)",
    }
    return ThematicIndex(**(defaults | overrides))


def _make_enriched(**overrides) -> EnrichedNotes:
    ref = _make_reference()
    ver = _make_verification(reference=ref)
    defaults = {
        "source_transcript": "/audio/lecture.wav",
        "transcript_text": "Krishna says in the Bhagavad-gita chapter 2 verse 47 about duty.",
        "references_found": [ref],
        "verifications": [ver],
        "glossary": [_make_glossary()],
        "thematic_index": _make_thematic_index(),
        "summary": "Enriched transcript with 1 verified reference.",
    }
    return EnrichedNotes(**(defaults | overrides))


# ---------------------------------------------------------------------------
# Reference tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestReference:

    def test_valid_reference(self):
        r = _make_reference()
        assert r.canonical_ref == "BG 2.47"

    def test_canonical_ref_min_length(self):
        with pytest.raises(ValidationError):
            _make_reference(canonical_ref="BG")

    def test_context_text_min_length(self):
        with pytest.raises(ValidationError):
            _make_reference(context_text="hi")

    def test_segment_index_non_negative(self):
        with pytest.raises(ValidationError):
            _make_reference(segment_index=-1)

    def test_various_scripture_types(self):
        for scripture, ref in [
            ("SB", "SB 1.2.6"),
            ("CC", "CC Adi 1.1"),
            ("NOI", "NOI 1"),
        ]:
            r = _make_reference(scripture=scripture, canonical_ref=ref)
            assert r.scripture == scripture


# ---------------------------------------------------------------------------
# VerificationResult tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestVerificationResult:

    def test_valid_verification(self):
        v = _make_verification()
        assert v.status == "verified"

    def test_verified_requires_translation(self):
        with pytest.raises(ValidationError, match="translation"):
            _make_verification(status="verified", translation=None)

    def test_verified_requires_url(self):
        with pytest.raises(ValidationError, match="vedabase.io URL"):
            _make_verification(status="verified", vedabase_url=None)

    def test_not_found_allows_no_translation(self):
        v = _make_verification(
            status="not_found", translation=None, vedabase_url=None,
            error="HTTP 404",
        )
        assert v.status == "not_found"

    def test_status_enum(self):
        for status in ["verified", "not_found", "partial_match", "cache_only"]:
            kwargs = {"status": status}
            if status in ("not_found", "partial_match"):
                kwargs["translation"] = None
                kwargs["vedabase_url"] = None
            v = _make_verification(**kwargs)
            assert v.status == status


# ---------------------------------------------------------------------------
# GlossaryEntry tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestGlossaryEntry:

    def test_valid_glossary(self):
        g = _make_glossary()
        assert g.term == "bhakti"

    def test_category_enum(self):
        for cat in ["sanskrit", "bengali", "philosophical", "historical", "general"]:
            g = _make_glossary(category=cat)
            assert g.category == cat

    def test_definition_min_length(self):
        with pytest.raises(ValidationError):
            _make_glossary(definition="hi")


# ---------------------------------------------------------------------------
# EnrichedNotes tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestEnrichedNotes:

    def test_valid_enriched(self):
        e = _make_enriched()
        assert len(e.verifications) == 1

    def test_all_refs_must_have_verification(self):
        ref1 = _make_reference(canonical_ref="BG 2.47")
        ref2 = _make_reference(canonical_ref="SB 1.2.6", scripture="SB",
                               chapter="1.2", verse="6")
        ver1 = _make_verification(reference=ref1)
        # ref2 has no verification and is not in unverified_references
        with pytest.raises(ValidationError, match="without verification"):
            _make_enriched(
                references_found=[ref1, ref2],
                verifications=[ver1],
                unverified_references=[],
            )

    def test_unverified_refs_satisfy_coverage(self):
        ref1 = _make_reference(canonical_ref="BG 2.47")
        ref2 = _make_reference(canonical_ref="SB 1.2.6", scripture="SB",
                               chapter="1.2", verse="6")
        ver1 = _make_verification(reference=ref1)
        # ref2 is explicitly unverified — this should be valid
        e = _make_enriched(
            references_found=[ref1, ref2],
            verifications=[ver1],
            unverified_references=[ref2],
        )
        assert len(e.unverified_references) == 1

    def test_verification_rate_auto_computed(self):
        e = _make_enriched()
        assert e.verification_rate == 1.0

    def test_transcript_text_min_length(self):
        with pytest.raises(ValidationError):
            _make_enriched(transcript_text="Too short")
