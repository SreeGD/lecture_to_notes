"""
Level 2: Pipeline tests for Agent 04 (Compiler).

Tests run_compiler_pipeline() with mock enriched notes and transcripts.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from lecture_agents.agents.compiler_agent import run_compiler_pipeline
from lecture_agents.exceptions import CompilationError
from lecture_agents.schemas.enrichment_output import (
    EnrichedNotes,
    GlossaryEntry,
    Reference,
    ThematicIndex,
    ThematicTag,
    VerificationResult,
)
from lecture_agents.schemas.transcript_output import (
    Segment,
    TranscriptOutput,
)
from tests.fixtures.conftest import (
    SAMPLE_VEDABASE_BG_2_47,
    SAMPLE_VEDABASE_SB_1_2_6,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_segment(start: float, end: float, text: str) -> Segment:
    return Segment(start=start, end=end, text=text, speaker="SPEAKER_00")


def _make_transcript(**overrides) -> TranscriptOutput:
    defaults = {
        "source_audio": "/audio/test.wav",
        "segments": [
            _make_segment(0, 15, "In the Bhagavad-gita chapter 2, verse 47, Krishna says"),
            _make_segment(15, 30, "karmany evadhikaras te ma phaleshu kadachana"),
            _make_segment(30, 50, "You have a right to perform your prescribed duty"),
            _make_segment(50, 70, "In the Srimad-Bhagavatam canto 1, chapter 2, verse 6"),
            _make_segment(70, 90, "sa vai pumsam paro dharmo about bhakti and dharma"),
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
        "summary": "Test transcript for compiler testing.",
    }
    return TranscriptOutput(**(defaults | overrides))


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


def _make_verification(ref: Reference, **overrides) -> VerificationResult:
    defaults = {
        "reference": ref,
        "status": "verified",
        "vedabase_url": SAMPLE_VEDABASE_BG_2_47["url"],
        "translation": SAMPLE_VEDABASE_BG_2_47["translation"],
        "verse_text": SAMPLE_VEDABASE_BG_2_47["verse_text"],
    }
    return VerificationResult(**(defaults | overrides))


def _make_enriched(**overrides) -> EnrichedNotes:
    ref = _make_reference()
    ver = _make_verification(ref)
    defaults = {
        "source_transcript": "/audio/test.wav",
        "transcript_text": (
            "In the Bhagavad-gita chapter 2, verse 47, Krishna says "
            "karmany evadhikaras te ma phaleshu kadachana. "
            "You have a right to perform your prescribed duty."
        ),
        "references_found": [ref],
        "verifications": [ver],
        "glossary": [
            GlossaryEntry(
                term="bhakti",
                definition="Devotional service to the Supreme Lord.",
                category="philosophical",
                source="BG Glossary",
            ),
            GlossaryEntry(
                term="dharma",
                definition="Occupational duty; religious principles.",
                category="philosophical",
                source="BG Glossary",
            ),
        ],
        "thematic_index": ThematicIndex(
            themes=[
                ThematicTag(
                    tag="Karma Yoga",
                    confidence=0.9,
                    evidence="Discussion of duty without attachment",
                ),
            ],
            primary_topic="Karma Yoga (Action in Devotion)",
        ),
        "summary": "Enriched transcript with 1 verified reference.",
    }
    return EnrichedNotes(**(defaults | overrides))


# ---------------------------------------------------------------------------
# Pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestRunCompilerPipeline:

    def test_pipeline_produces_valid_output(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Test Book",
            output_dir=str(tmp_path),
        )
        assert result.title == "Test Book"
        assert len(result.chapters) >= 1
        assert result.report.total_chapters == len(result.chapters)

    def test_pipeline_writes_output_file(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Output File Test",
            output_dir=str(tmp_path),
        )
        output_path = Path(result.output_path)
        assert output_path.exists()
        content = output_path.read_text()
        assert "Output File Test" in content

    def test_pipeline_includes_front_matter(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Front Matter Test",
            output_dir=str(tmp_path),
            speaker="Srila Prabhupada",
        )
        assert "Front Matter Test" in result.front_matter_markdown
        assert "Srila Prabhupada" in result.front_matter_markdown

    def test_pipeline_includes_glossary(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Glossary Test",
            output_dir=str(tmp_path),
        )
        assert result.glossary is not None
        assert result.glossary.total_entries >= 2
        terms = {e["term"].lower() for e in result.glossary.entries}
        assert "bhakti" in terms

    def test_pipeline_includes_verse_index(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Index Test",
            output_dir=str(tmp_path),
        )
        assert result.index is not None
        assert "BG 2.47" in result.index.verse_index

    def test_pipeline_reports_word_count(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Word Count Test",
            output_dir=str(tmp_path),
        )
        assert result.report.total_words > 0

    def test_pipeline_multi_source_mode(self, tmp_path):
        ref1 = _make_reference()
        ver1 = _make_verification(ref1)
        enriched1 = _make_enriched()

        ref2 = _make_reference(
            scripture="SB", chapter="1.2", verse="6",
            canonical_ref="SB 1.2.6", segment_index=0,
            context_text="In the Srimad-Bhagavatam canto 1 chapter 2 verse 6",
        )
        ver2 = _make_verification(
            ref2,
            vedabase_url=SAMPLE_VEDABASE_SB_1_2_6["url"],
            translation=SAMPLE_VEDABASE_SB_1_2_6["translation"],
            verse_text=SAMPLE_VEDABASE_SB_1_2_6["verse_text"],
        )
        enriched2 = _make_enriched(
            source_transcript="/audio/test2.wav",
            references_found=[ref2],
            verifications=[ver2],
        )

        transcript2 = _make_transcript(source_audio="/audio/test2.wav")

        result = run_compiler_pipeline(
            [enriched1, enriched2],
            [_make_transcript(), transcript2],
            title="Multi Source Test",
            output_dir=str(tmp_path),
            mode="multi",
        )
        assert len(result.chapters) == 2
        assert result.report.total_chapters == 2

    def test_pipeline_rejects_empty_input(self, tmp_path):
        with pytest.raises(CompilationError, match="No enriched notes"):
            run_compiler_pipeline(
                [], [],
                title="Empty Test",
                output_dir=str(tmp_path),
            )

    def test_pipeline_source_references(self, tmp_path):
        enriched = _make_enriched()
        transcript = _make_transcript()
        result = run_compiler_pipeline(
            [enriched], [transcript],
            title="Source Refs Test",
            output_dir=str(tmp_path),
        )
        assert len(result.source_references) == 1
        assert result.source_references[0].url == "/audio/test.wav"
