"""
Level 2: Pipeline tests for Agent 03 (Enrichment).

Tests run_enrichment_pipeline() with mocked vedabase fetcher.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from lecture_agents.agents.enrichment_agent import run_enrichment_pipeline
from lecture_agents.exceptions import EnrichmentError
from lecture_agents.schemas.transcript_output import (
    Segment,
    TranscriptOutput,
    VocabularyLog,
)
from tests.fixtures.conftest import (
    SAMPLE_VEDABASE_BG_2_47,
    SAMPLE_VEDABASE_SB_1_2_6,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_transcript(**overrides) -> TranscriptOutput:
    defaults = {
        "source_audio": "/audio/test.wav",
        "segments": [
            Segment(start=0, end=15, text="In the Bhagavad-gita chapter 2, verse 47, Krishna says"),
            Segment(start=15, end=30, text="karmany evadhikaras te ma phaleshu kadachana"),
            Segment(start=30, end=50, text="You have a right to perform your prescribed duty"),
            Segment(start=50, end=70, text="In the Srimad-Bhagavatam canto 1, chapter 2, verse 6"),
            Segment(start=70, end=90, text="sa vai pumsam paro dharmo about bhakti and dharma"),
        ],
        "full_text": (
            "In the Bhagavad-gita chapter 2, verse 47, Krishna says "
            "karmany evadhikaras te ma phaleshu kadachana. "
            "You have a right to perform your prescribed duty. "
            "In the Srimad-Bhagavatam canto 1, chapter 2, verse 6, "
            "sa vai pumsam paro dharmo about bhakti and dharma."
        ),
        "duration_seconds": 90.0,
        "whisper_model": "large-v3",
        "summary": "Test transcript for enrichment testing.",
    }
    return TranscriptOutput(**(defaults | overrides))


def _mock_fetch_verse(scripture, chapter, verse, **kwargs):
    """Mock vedabase fetch that returns test data."""
    key = f"{scripture.upper()}_{chapter}_{verse}"
    if key == "BG_2_47":
        return {**SAMPLE_VEDABASE_BG_2_47, "fetch_source": "cache", "cross_refs_in_purport": []}
    elif key == "SB_1.2_6":
        return {**SAMPLE_VEDABASE_SB_1_2_6, "fetch_source": "cache", "cross_refs_in_purport": []}
    else:
        return {
            "url": None,
            "verified": False,
            "fetch_source": "not_found",
            "error": f"Not found: {key}",
        }


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestRunEnrichmentPipeline:

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_pipeline_produces_valid_output(self, mock_fetch):
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        assert len(result.references_found) >= 1
        assert len(result.verifications) >= 1
        assert result.verification_rate > 0

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_pipeline_identifies_bg_reference(self, mock_fetch):
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        bg_refs = [r for r in result.references_found if r.scripture == "BG"]
        assert len(bg_refs) >= 1
        assert bg_refs[0].canonical_ref == "BG 2.47"

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_pipeline_verifies_against_vedabase(self, mock_fetch):
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        verified = [v for v in result.verifications if v.status in ("verified", "cache_only")]
        assert len(verified) >= 1
        # Check that translation is from vedabase, not generated
        for v in verified:
            assert v.translation is not None
            assert v.vedabase_url is not None

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse")
    def test_pipeline_handles_unverified_refs(self, mock_fetch):
        mock_fetch.return_value = {
            "url": None,
            "verified": False,
            "fetch_source": "not_found",
            "error": "Not found",
        }
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        # All references should be in unverified list
        assert len(result.unverified_references) == len(result.references_found)
        assert len(result.verifications) == 0
        assert result.verification_rate == 0.0

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_pipeline_builds_glossary(self, mock_fetch):
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        assert len(result.glossary) > 0
        terms = {g.term.lower() for g in result.glossary}
        # bhakti and dharma are in the transcript text
        assert "bhakti" in terms or "dharma" in terms

    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_pipeline_builds_thematic_index(self, mock_fetch):
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=False)

        assert result.thematic_index.primary_topic is not None
        assert len(result.thematic_index.primary_topic) >= 3

    def test_pipeline_rejects_short_text(self):
        transcript = _make_transcript(
            full_text="This text is short but valid.",
            segments=[Segment(start=0, end=5, text="This text is short but valid.")],
        )
        with pytest.raises(EnrichmentError, match="too short"):
            run_enrichment_pipeline(transcript, enable_llm=False)


# ---------------------------------------------------------------------------
# LLM reference identification tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestLlmReferenceIdentification:

    @patch("lecture_agents.agents.enrichment_agent.identify_references_llm")
    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_llm_identification_called_when_enabled(self, mock_fetch, mock_llm_id):
        """When enable_llm=True, LLM reference identification is called."""
        mock_llm_id.return_value = []
        transcript = _make_transcript()
        run_enrichment_pipeline(transcript, enable_llm=True)
        mock_llm_id.assert_called_once()

    @patch("lecture_agents.agents.enrichment_agent.identify_references_llm")
    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_llm_identification_not_called_when_disabled(self, mock_fetch, mock_llm_id):
        """When enable_llm=False, LLM reference identification is NOT called."""
        transcript = _make_transcript()
        run_enrichment_pipeline(transcript, enable_llm=False)
        mock_llm_id.assert_not_called()

    @patch("lecture_agents.agents.enrichment_agent.identify_references_llm")
    @patch("lecture_agents.agents.enrichment_agent.fetch_verse", side_effect=_mock_fetch_verse)
    def test_llm_refs_merged_and_verified(self, mock_fetch, mock_llm_id):
        """LLM-found references get merged and sent to vedabase verification."""
        mock_llm_id.return_value = [{
            "scripture": "SB",
            "chapter": "3.25",
            "verse": "21",
            "canonical_ref": "SB 3.25.21",
            "segment_index": 0,
            "context_text": "Kapiladeva describes a sadhu",
        }]
        transcript = _make_transcript()
        result = run_enrichment_pipeline(transcript, enable_llm=True)

        # Should have regex refs + LLM ref
        all_canonicals = {r.canonical_ref for r in result.references_found}
        assert "SB 3.25.21" in all_canonicals
        # BG 2.47 from regex should still be there
        assert "BG 2.47" in all_canonicals
