"""
Level 2: Pipeline tests for Agent 3.5 (Validation).

Tests run_validation_pipeline() with mock TranscriptOutput and EnrichedNotes.
All checks are deterministic — no LLM, no I/O.
"""

from __future__ import annotations

import pytest

from lecture_agents.agents.validation_agent import (
    _check_confidence,
    _check_content_density,
    _check_cross_reference_consistency,
    _check_empty_enrichment,
    _check_enriched_markdown_repetition,
    _check_language_consistency,
    _check_segment_gaps,
    _check_sliding_window_repetition,
    _check_verification_rate,
    run_validation_pipeline,
)
from lecture_agents.exceptions import ValidationError
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
    VocabularyLog,
)
from lecture_agents.schemas.validation_output import CheckSeverity


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_transcript(
    segments: list[dict] | None = None,
    duration: float = 600.0,
    full_text: str | None = None,
) -> TranscriptOutput:
    """Build a mock TranscriptOutput."""
    if segments is None:
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Segment {i} text content here."}
            for i in range(60)
        ]
    segs = [Segment(**s) for s in segments]
    if full_text is None:
        full_text = " ".join(s["text"] for s in segments)
    return TranscriptOutput(
        source_audio="/tmp/test.wav",
        segments=segs,
        full_text=full_text,
        duration_seconds=duration,
        language="en",
        whisper_model="large-v3",
        vocabulary_log=VocabularyLog(),
        summary="Test transcript",
    )


def _make_enriched(
    refs: int = 3,
    verified: int = 2,
    glossary: int = 2,
    enriched_markdown: str | None = None,
) -> EnrichedNotes:
    """Build a mock EnrichedNotes."""
    references = [
        Reference(
            scripture="BG",
            chapter="2",
            verse=str(i + 1),
            canonical_ref=f"BG 2.{i + 1}",
            segment_index=i,
            context_text=f"Lord Krishna says in BG 2.{i + 1} that the soul is eternal.",
        )
        for i in range(refs)
    ]
    verifications = [
        VerificationResult(
            reference=references[i],
            status="verified",
            vedabase_url=f"https://vedabase.io/en/library/bg/2/{i + 1}/",
            translation=f"Translation for BG 2.{i + 1}",
        )
        for i in range(min(verified, refs))
    ]
    unverified = references[verified:]
    glossary_entries = [
        GlossaryEntry(
            term=f"Term{i}",
            definition=f"Definition for term {i} from Prabhupada's books",
            category="sanskrit",
        )
        for i in range(glossary)
    ]
    themes = [
        ThematicTag(
            tag="Karma Yoga",
            confidence=0.9,
            evidence="Discussed extensively",
            related_references=[f"BG 2.{i + 1}" for i in range(min(verified, refs))],
        ),
    ]
    return EnrichedNotes(
        source_transcript="/tmp/test_transcript.json",
        transcript_text="Lord Krishna says in Bhagavad-gita that the soul is eternal.",
        references_found=references,
        verifications=verifications,
        unverified_references=unverified,
        glossary=glossary_entries,
        thematic_index=ThematicIndex(
            themes=themes,
            primary_topic="Karma Yoga",
            scripture_focus="Bhagavad-gita",
        ),
        summary="Test enrichment with verified references.",
        enriched_markdown=enriched_markdown,
    )


# ---------------------------------------------------------------------------
# Transcription check tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestSlidingWindowRepetition:

    def test_normal_transcript_passes(self):
        transcript = _make_transcript()
        result = _check_sliding_window_repetition(transcript)
        assert result.passed
        assert result.severity == CheckSeverity.CRITICAL

    def test_hallucinated_transcript_fails(self):
        """100% repeated text should fail."""
        segments = [
            {"start": i * 2.0, "end": (i + 1) * 2.0 - 0.1, "text": "Subtitles by the Amara.org community"}
            for i in range(100)
        ]
        transcript = _make_transcript(segments=segments, duration=200.0)
        result = _check_sliding_window_repetition(transcript)
        assert not result.passed
        assert result.severity == CheckSeverity.CRITICAL
        assert "Repetition" in result.message

    def test_short_transcript_skipped(self):
        """Fewer segments than window size should skip."""
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Segment {i}"}
            for i in range(5)
        ]
        transcript = _make_transcript(segments=segments, duration=50.0)
        result = _check_sliding_window_repetition(transcript)
        assert result.passed
        assert "Skipped" in result.message


@pytest.mark.pipeline
class TestContentDensity:

    def test_normal_density_passes(self):
        transcript = _make_transcript()
        result = _check_content_density(transcript)
        assert result.passed

    def test_sparse_content_fails(self):
        """50 words in 60 minutes = 0.83 wpm, should fail."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": " ".join(["word"] * 50)}
        ]
        transcript = _make_transcript(segments=segments, duration=3600.0)
        result = _check_content_density(transcript)
        assert not result.passed
        assert result.severity == CheckSeverity.CRITICAL

    def test_short_audio_skipped(self):
        segments = [
            {"start": 0.0, "end": 20.0, "text": "Hello world this is short audio"}
        ]
        transcript = _make_transcript(segments=segments, duration=20.0)
        result = _check_content_density(transcript)
        assert result.passed
        assert "Skipped" in result.message


@pytest.mark.pipeline
class TestSegmentGaps:

    def test_no_gaps_passes(self):
        transcript = _make_transcript()
        result = _check_segment_gaps(transcript)
        assert result.passed

    def test_large_gap_warns(self):
        segments = [
            {"start": 0.0, "end": 10.0, "text": "First segment"},
            {"start": 60.0, "end": 70.0, "text": "After a 50s gap"},
        ]
        transcript = _make_transcript(segments=segments, duration=70.0)
        result = _check_segment_gaps(transcript)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING
        assert result.details["gap_count"] == 1


@pytest.mark.pipeline
class TestConfidence:

    def test_no_confidence_skipped(self):
        transcript = _make_transcript()
        result = _check_confidence(transcript)
        assert result.passed
        assert "Skipped" in result.message

    def test_good_confidence_passes(self):
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Seg {i}", "confidence": 0.8}
            for i in range(10)
        ]
        transcript = _make_transcript(segments=segments, duration=100.0)
        result = _check_confidence(transcript)
        assert result.passed

    def test_low_confidence_warns(self):
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Seg {i}", "confidence": 0.1}
            for i in range(10)
        ]
        transcript = _make_transcript(segments=segments, duration=100.0)
        result = _check_confidence(transcript)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING


@pytest.mark.pipeline
class TestLanguageConsistency:

    def test_no_language_data_skipped(self):
        transcript = _make_transcript()
        result = _check_language_consistency(transcript)
        assert result.passed

    def test_consistent_language_passes(self):
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Seg {i}", "language": "en"}
            for i in range(10)
        ]
        transcript = _make_transcript(segments=segments, duration=100.0)
        result = _check_language_consistency(transcript)
        assert result.passed

    def test_inconsistent_language_warns(self):
        segments = [
            {"start": i * 10.0, "end": (i + 1) * 10.0 - 0.5, "text": f"Seg {i}", "language": "zh" if i < 5 else "en"}
            for i in range(10)
        ]
        transcript = _make_transcript(segments=segments, duration=100.0)
        result = _check_language_consistency(transcript)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING


# ---------------------------------------------------------------------------
# Enrichment check tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestVerificationRate:

    def test_good_rate_passes(self):
        enriched = _make_enriched(refs=4, verified=3)
        result = _check_verification_rate(enriched)
        assert result.passed

    def test_low_rate_warns(self):
        enriched = _make_enriched(refs=10, verified=2)
        result = _check_verification_rate(enriched)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING

    def test_no_refs_skipped(self):
        enriched = _make_enriched(refs=0, verified=0)
        result = _check_verification_rate(enriched)
        assert result.passed
        assert "Skipped" in result.message


@pytest.mark.pipeline
class TestCrossReferenceConsistency:

    def test_consistent_refs_passes(self):
        enriched = _make_enriched(refs=3, verified=3)
        result = _check_cross_reference_consistency(enriched)
        assert result.passed

    def test_orphaned_ref_warns(self):
        enriched = _make_enriched(refs=3, verified=2)
        # Add a theme with a reference that isn't verified
        enriched.thematic_index.themes.append(
            ThematicTag(
                tag="Devotion",
                confidence=0.8,
                evidence="Discussed in lecture",
                related_references=["SB 1.1.1"],
            )
        )
        result = _check_cross_reference_consistency(enriched)
        assert not result.passed
        assert "SB 1.1.1" in result.message


@pytest.mark.pipeline
class TestEnrichedMarkdownRepetition:

    def test_no_markdown_skipped(self):
        enriched = _make_enriched(enriched_markdown=None)
        result = _check_enriched_markdown_repetition(enriched)
        assert result.passed

    def test_normal_markdown_passes(self):
        md = "\n\n".join([f"Paragraph {i} with unique content here." for i in range(10)])
        enriched = _make_enriched(enriched_markdown=md)
        result = _check_enriched_markdown_repetition(enriched)
        assert result.passed

    def test_repeated_markdown_fails(self):
        repeated_para = "This is a hallucinated repeated paragraph that keeps showing up."
        md = "\n\n".join([repeated_para] * 10)
        enriched = _make_enriched(enriched_markdown=md)
        result = _check_enriched_markdown_repetition(enriched)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING


@pytest.mark.pipeline
class TestEmptyEnrichment:

    def test_normal_enrichment_passes(self):
        enriched = _make_enriched()
        result = _check_empty_enrichment(enriched)
        assert result.passed

    def test_empty_enrichment_warns(self):
        enriched = _make_enriched(refs=0, verified=0, glossary=0, enriched_markdown=None)
        result = _check_empty_enrichment(enriched)
        assert not result.passed
        assert result.severity == CheckSeverity.WARNING


# ---------------------------------------------------------------------------
# Full pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestValidationPipeline:

    def test_good_data_passes(self):
        """Normal transcript + enrichment should pass all checks."""
        transcript = _make_transcript()
        enriched = _make_enriched()
        report = run_validation_pipeline(transcript, enriched)
        assert report.overall_pass
        assert report.critical_failures == 0

    def test_hallucinated_transcript_raises(self):
        """Hallucinated transcript should raise ValidationError."""
        segments = [
            {"start": i * 2.0, "end": (i + 1) * 2.0 - 0.1, "text": "Subtitles by the Amara.org community"}
            for i in range(100)
        ]
        transcript = _make_transcript(segments=segments, duration=200.0)
        enriched = _make_enriched()
        with pytest.raises(ValidationError, match="CRITICAL"):
            run_validation_pipeline(transcript, enriched)

    def test_sparse_transcript_raises(self):
        """Very sparse content should raise ValidationError."""
        segments = [
            {"start": 0.0, "end": 10.0, "text": "Just a few words here"}
        ]
        transcript = _make_transcript(segments=segments, duration=3600.0)
        enriched = _make_enriched()
        with pytest.raises(ValidationError, match="CRITICAL"):
            run_validation_pipeline(transcript, enriched)

    def test_warnings_do_not_raise(self):
        """Warnings should not raise, just be counted."""
        # Create a gap but no critical issues
        segments = [
            {"start": 0.0, "end": 10.0, "text": f"Segment with enough words to pass density check. Word {i}" }
            for i in range(60)
        ]
        # Override with gap
        segments[30] = {"start": 400.0, "end": 410.0, "text": "After a gap of many seconds with content"}
        for i in range(31, 60):
            segments[i] = {"start": 410.0 + (i - 31) * 10.0, "end": 420.0 + (i - 31) * 10.0 - 0.5, "text": f"Segment {i} text content here."}
        transcript = _make_transcript(segments=segments, duration=700.0)
        enriched = _make_enriched(refs=10, verified=2)  # Low verification rate
        report = run_validation_pipeline(transcript, enriched)
        assert report.overall_pass  # No critical failures
        assert report.warnings > 0

    def test_repeated_markdown_warns(self):
        """Repeated enriched markdown should warn but not raise."""
        repeated = "This hallucinated text keeps repeating over and over."
        md = "\n\n".join([repeated] * 10)
        transcript = _make_transcript()
        enriched = _make_enriched(enriched_markdown=md)
        # Downgraded to WARNING — should not raise
        report = run_validation_pipeline(transcript, enriched)
        assert report.warnings > 0
