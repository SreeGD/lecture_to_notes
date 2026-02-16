"""
Level 1: Schema validation tests for Agent 02 (Transcriber).

Tests Pydantic model constraints without any I/O or LLM calls.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lecture_agents.schemas.transcript_output import (
    DetectedSloka,
    Segment,
    TranscriptOutput,
    VocabularyCorrection,
    VocabularyLog,
)


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------


def _make_segment(**overrides) -> Segment:
    defaults = {
        "start": 0.0,
        "end": 10.0,
        "text": "Hare Krsna, welcome to today's class.",
    }
    return Segment(**(defaults | overrides))


def _make_correction(**overrides) -> VocabularyCorrection:
    defaults = {
        "original": "krishna",
        "corrected": "Krsna",
        "category": "name",
    }
    return VocabularyCorrection(**(defaults | overrides))


def _make_transcript(**overrides) -> TranscriptOutput:
    defaults = {
        "source_audio": "/audio/lecture.wav",
        "segments": [_make_segment()],
        "full_text": "Hare Krsna, welcome to today's class on Bhagavad-gita.",
        "duration_seconds": 3600.0,
        "whisper_model": "large-v3",
        "summary": "Transcribed 3600s of audio. 1 segments.",
    }
    return TranscriptOutput(**(defaults | overrides))


# ---------------------------------------------------------------------------
# Segment tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestSegment:

    def test_valid_segment_parses(self):
        s = _make_segment()
        assert s.text == "Hare Krsna, welcome to today's class."

    def test_end_must_be_after_start(self):
        with pytest.raises(ValidationError, match="end.*must be > start"):
            _make_segment(start=10.0, end=5.0)

    def test_equal_start_end_rejected(self):
        with pytest.raises(ValidationError, match="end.*must be > start"):
            _make_segment(start=5.0, end=5.0)

    def test_negative_start_rejected(self):
        with pytest.raises(ValidationError):
            _make_segment(start=-1.0)

    def test_confidence_range(self):
        s = _make_segment(confidence=0.95)
        assert s.confidence == 0.95

    def test_confidence_out_of_range(self):
        with pytest.raises(ValidationError):
            _make_segment(confidence=1.5)

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            _make_segment(text="")

    def test_speaker_label(self):
        s = _make_segment(speaker="Speaker")
        assert s.speaker == "Speaker"


# ---------------------------------------------------------------------------
# VocabularyCorrection tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestVocabularyCorrection:

    def test_valid_correction(self):
        c = _make_correction()
        assert c.corrected == "Krsna"

    def test_category_enum(self):
        for cat in ["sanskrit", "bengali", "name", "scripture"]:
            c = _make_correction(category=cat)
            assert c.category == cat

    def test_invalid_category(self):
        with pytest.raises(ValidationError):
            _make_correction(category="unknown")

    def test_empty_original_rejected(self):
        with pytest.raises(ValidationError):
            _make_correction(original="")


# ---------------------------------------------------------------------------
# VocabularyLog tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestVocabularyLog:

    def test_empty_log(self):
        v = VocabularyLog()
        assert v.total_corrections == 0

    def test_log_with_corrections(self):
        v = VocabularyLog(
            corrections=[_make_correction()],
            total_corrections=1,
            unique_terms_corrected=1,
        )
        assert v.total_corrections == 1

    def test_auto_count_correction(self):
        v = VocabularyLog(corrections=[_make_correction(), _make_correction()])
        assert v.total_corrections >= 2


# ---------------------------------------------------------------------------
# DetectedSloka tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestDetectedSloka:

    def test_valid_sloka(self):
        s = DetectedSloka(
            segment_index=0,
            text="karmany evadhikaras te",
            probable_reference="BG 2.47",
            confidence=0.9,
        )
        assert s.probable_reference == "BG 2.47"

    def test_confidence_range(self):
        with pytest.raises(ValidationError):
            DetectedSloka(segment_index=0, text="test text", confidence=1.5)

    def test_short_text_rejected(self):
        with pytest.raises(ValidationError):
            DetectedSloka(segment_index=0, text="abc")


# ---------------------------------------------------------------------------
# TranscriptOutput tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestTranscriptOutput:

    def test_valid_transcript(self):
        t = _make_transcript()
        assert t.whisper_model == "large-v3"

    def test_segments_required(self):
        with pytest.raises(ValidationError):
            _make_transcript(segments=[])

    def test_full_text_min_length(self):
        with pytest.raises(ValidationError):
            _make_transcript(full_text="Too short")

    def test_segments_within_duration(self):
        seg = _make_segment(start=0, end=5000)
        with pytest.raises(ValidationError, match="exceeds"):
            _make_transcript(segments=[seg], duration_seconds=100)

    def test_post_processing_source_enum(self):
        for src in ["llm", "regex", "none"]:
            t = _make_transcript(post_processing_source=src)
            assert t.post_processing_source == src

    def test_invalid_post_processing_source(self):
        with pytest.raises(ValidationError):
            _make_transcript(post_processing_source="unknown")

    def test_multiple_segments(self):
        segs = [
            _make_segment(start=0, end=10, text="First segment."),
            _make_segment(start=10, end=20, text="Second segment."),
            _make_segment(start=20, end=30, text="Third segment."),
        ]
        t = _make_transcript(segments=segs, duration_seconds=35)
        assert len(t.segments) == 3
