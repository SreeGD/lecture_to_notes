"""
Tests for checkpoint save/load functionality.

Validates round-trip serialization for all schema types and
upfront validation logic for --from-agent.
"""

from __future__ import annotations

import pytest

from lecture_agents.checkpoint import (
    load_book_checkpoint,
    load_enriched_checkpoint,
    load_manifest_checkpoint,
    load_transcript_checkpoint,
    save_book_checkpoint,
    save_enriched_checkpoint,
    save_manifest_checkpoint,
    save_transcript_checkpoint,
    validate_checkpoints_for_from_agent,
)
from lecture_agents.exceptions import PipelineError
from lecture_agents.schemas.compiler_output import (
    BookOutput,
    Chapter,
    CompilationReport,
)
from lecture_agents.schemas.download_output import (
    BatchSummary,
    DownloadManifest,
    DownloadResult,
    MediaMetadata,
)
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


# ---------------------------------------------------------------------------
# Test data factories
# ---------------------------------------------------------------------------


def _make_manifest() -> DownloadManifest:
    return DownloadManifest(
        results=[DownloadResult(
            url="https://example.com/audio.mp3",
            order=1,
            success=True,
            audio_path="/output/audio/lecture_001.wav",
            sha256="a" * 64,
            metadata=MediaMetadata(
                url="https://example.com/audio.mp3",
                title="Test Lecture",
                source_type="direct_http",
            ),
        )],
        batch_summary=BatchSummary(total_urls=1, successful=1, failed=0),
        output_dir="/output/audio",
        summary="Downloaded 1 file.",
    )


def _make_transcript() -> TranscriptOutput:
    return TranscriptOutput(
        source_audio="/output/audio/lecture_001.wav",
        segments=[
            Segment(start=0, end=10, text="Hello world"),
            Segment(start=10, end=20, text="BG 2.47 karmany evadhikaras te"),
        ],
        full_text="Hello world. BG 2.47 karmany evadhikaras te.",
        duration_seconds=20.0,
        whisper_model="tiny",
        summary="Test transcript.",
    )


def _make_enriched() -> EnrichedNotes:
    ref = Reference(
        scripture="BG", chapter="2", verse="47",
        canonical_ref="BG 2.47", segment_index=0,
        context_text="BG 2.47 karmany evadhikaras te",
    )
    ver = VerificationResult(
        reference=ref, status="verified",
        vedabase_url="https://vedabase.io/en/library/bg/2/47/",
        translation="You have a right to perform your prescribed duty.",
        verse_text="karmany evadhikaras te",
    )
    return EnrichedNotes(
        source_transcript="/output/audio/lecture_001.wav",
        transcript_text="Hello world. BG 2.47 karmany evadhikaras te.",
        references_found=[ref],
        verifications=[ver],
        glossary=[GlossaryEntry(
            term="bhakti",
            definition="Devotional service.",
            category="philosophical",
        )],
        thematic_index=ThematicIndex(
            themes=[ThematicTag(
                tag="Karma Yoga", confidence=0.9,
                evidence="Duty and devotion",
            )],
            primary_topic="Karma Yoga",
        ),
        summary="1 verified reference.",
    )


def _make_book(output_dir: str = "/output") -> BookOutput:
    return BookOutput(
        title="Test Book",
        chapters=[Chapter(
            number=1,
            title="Chapter 1",
            content_markdown="# Chapter 1: Karma Yoga Discussion\n\nContent about duty and devotion.",
        )],
        front_matter_markdown="# Test Book\n\nFront matter content for the test book here.",
        full_book_markdown=(
            "# Test Book\n\nFront matter.\n\n"
            "# Chapter 1: Karma Yoga Discussion\n\nContent about duty and devotion.\n\n"
            "---\nBack matter with glossary and index information."
        ),
        report=CompilationReport(total_chapters=1, total_words=100),
        output_path=f"{output_dir}/final_book.md",
        summary="Compiled 1 chapter with 100 words.",
    )


# ---------------------------------------------------------------------------
# Round-trip save/load tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestCheckpointRoundTrip:

    def test_manifest_round_trip(self, tmp_path):
        original = _make_manifest()
        save_manifest_checkpoint(original, str(tmp_path))
        loaded = load_manifest_checkpoint(str(tmp_path))

        assert len(loaded.results) == len(original.results)
        assert loaded.results[0].url == original.results[0].url
        assert loaded.results[0].audio_path == original.results[0].audio_path
        assert loaded.batch_summary.total_urls == original.batch_summary.total_urls

    def test_transcript_round_trip(self, tmp_path):
        original = _make_transcript()
        save_transcript_checkpoint(original, str(tmp_path), order=1)
        loaded = load_transcript_checkpoint(str(tmp_path), order=1)

        assert len(loaded.segments) == len(original.segments)
        assert loaded.full_text == original.full_text
        assert loaded.duration_seconds == original.duration_seconds
        assert loaded.whisper_model == original.whisper_model

    def test_enriched_round_trip(self, tmp_path):
        original = _make_enriched()
        save_enriched_checkpoint(original, str(tmp_path), order=1)
        loaded = load_enriched_checkpoint(str(tmp_path), order=1)

        assert len(loaded.references_found) == len(original.references_found)
        assert loaded.references_found[0].canonical_ref == "BG 2.47"
        assert len(loaded.verifications) == len(original.verifications)
        assert loaded.verifications[0].status == "verified"

    def test_book_round_trip(self, tmp_path):
        original = _make_book(str(tmp_path))
        save_book_checkpoint(original, str(tmp_path))
        loaded = load_book_checkpoint(str(tmp_path))

        assert loaded.title == original.title
        assert len(loaded.chapters) == len(original.chapters)
        assert loaded.full_book_markdown == original.full_book_markdown
        assert loaded.report.total_chapters == original.report.total_chapters

    def test_multi_url_transcript_round_trip(self, tmp_path):
        """Verify different order numbers produce distinct files."""
        t1 = _make_transcript()
        t2 = TranscriptOutput(
            source_audio="/output/audio/lecture_002.wav",
            segments=[Segment(start=0, end=5, text="Second lecture about Bhagavad-gita")],
            full_text="Second lecture about Bhagavad-gita and devotional service to the Lord.",
            duration_seconds=5.0,
            whisper_model="tiny",
            summary="Second transcript for testing multi-URL checkpoint.",
        )
        save_transcript_checkpoint(t1, str(tmp_path), order=1)
        save_transcript_checkpoint(t2, str(tmp_path), order=2)

        loaded1 = load_transcript_checkpoint(str(tmp_path), order=1)
        loaded2 = load_transcript_checkpoint(str(tmp_path), order=2)

        assert loaded1.full_text == t1.full_text
        assert loaded2.full_text == t2.full_text


# ---------------------------------------------------------------------------
# Missing file tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestCheckpointMissingFiles:

    def test_load_missing_manifest_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="file not found"):
            load_manifest_checkpoint(str(tmp_path))

    def test_load_missing_transcript_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="file not found"):
            load_transcript_checkpoint(str(tmp_path), order=1)

    def test_load_missing_enriched_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="file not found"):
            load_enriched_checkpoint(str(tmp_path), order=1)

    def test_load_missing_book_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="file not found"):
            load_book_checkpoint(str(tmp_path))


# ---------------------------------------------------------------------------
# Validation tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestValidateCheckpoints:

    def test_from_agent_1_always_valid(self, tmp_path):
        """from_agent=1 needs no checkpoints."""
        validate_checkpoints_for_from_agent(1, str(tmp_path))

    def test_from_agent_2_needs_manifest(self, tmp_path):
        with pytest.raises(PipelineError, match="manifest"):
            validate_checkpoints_for_from_agent(2, str(tmp_path), url_count=1)

    def test_from_agent_2_with_manifest_valid(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        validate_checkpoints_for_from_agent(2, str(tmp_path), url_count=1)

    def test_from_agent_3_needs_transcripts(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        with pytest.raises(PipelineError, match="missing checkpoint"):
            validate_checkpoints_for_from_agent(3, str(tmp_path), url_count=1)

    def test_from_agent_3_with_all_checkpoints_valid(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        save_transcript_checkpoint(_make_transcript(), str(tmp_path), order=1)
        validate_checkpoints_for_from_agent(3, str(tmp_path), url_count=1)

    def test_from_agent_4_needs_enriched(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        save_transcript_checkpoint(_make_transcript(), str(tmp_path), order=1)
        with pytest.raises(PipelineError, match="missing checkpoint"):
            validate_checkpoints_for_from_agent(4, str(tmp_path), url_count=1)

    def test_from_agent_5_needs_book(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        save_transcript_checkpoint(_make_transcript(), str(tmp_path), order=1)
        save_enriched_checkpoint(_make_enriched(), str(tmp_path), order=1)
        with pytest.raises(PipelineError, match="missing checkpoint"):
            validate_checkpoints_for_from_agent(5, str(tmp_path), url_count=1)

    def test_from_agent_5_with_all_checkpoints_valid(self, tmp_path):
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        save_transcript_checkpoint(_make_transcript(), str(tmp_path), order=1)
        save_enriched_checkpoint(_make_enriched(), str(tmp_path), order=1)
        save_book_checkpoint(_make_book(str(tmp_path)), str(tmp_path))
        validate_checkpoints_for_from_agent(5, str(tmp_path), url_count=1)

    def test_infers_url_count_from_manifest(self, tmp_path):
        """When url_count is None, reads manifest to determine count."""
        save_manifest_checkpoint(_make_manifest(), str(tmp_path))
        save_transcript_checkpoint(_make_transcript(), str(tmp_path), order=1)
        # url_count=None — should infer 1 URL from manifest
        validate_checkpoints_for_from_agent(3, str(tmp_path))
