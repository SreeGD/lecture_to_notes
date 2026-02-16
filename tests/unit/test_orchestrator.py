"""
Level 2: Pipeline tests for the Orchestrator.

Tests run_single_url_pipeline() and run_multi_url_pipeline()
with all agents mocked.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lecture_agents.checkpoint import (
    save_book_checkpoint,
    save_enriched_checkpoint,
    save_manifest_checkpoint,
    save_transcript_checkpoint,
)
from lecture_agents.exceptions import PipelineError
from lecture_agents.orchestrator import (
    run_multi_url_pipeline,
    run_single_url_pipeline,
)
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
# Mock data factories
# ---------------------------------------------------------------------------


def _mock_manifest(urls: list[str], output_dir: str = "/output/audio") -> DownloadManifest:
    results = []
    for i, url in enumerate(urls, 1):
        results.append(DownloadResult(
            url=url,
            order=i,
            success=True,
            audio_path=f"/output/audio/lecture_{i}.wav",
            sha256="a" * 64,
            metadata=MediaMetadata(url=url, title=f"Lecture {i}", source_type="youtube"),
        ))
    return DownloadManifest(
        results=results,
        batch_summary=BatchSummary(
            total_urls=len(urls),
            successful=len(urls),
            failed=0,
        ),
        output_dir=output_dir,
        summary=f"Downloaded {len(urls)} files.",
    )


def _mock_transcript(source_audio: str = "/output/audio/lecture_1.wav") -> TranscriptOutput:
    return TranscriptOutput(
        source_audio=source_audio,
        segments=[
            Segment(start=0, end=15, text="Krishna says in the Bhagavad-gita chapter 2 verse 47"),
            Segment(start=15, end=30, text="karmany evadhikaras te ma phaleshu kadachana"),
            Segment(start=30, end=50, text="You have a right to perform your prescribed duty"),
        ],
        full_text=(
            "Krishna says in the Bhagavad-gita chapter 2 verse 47. "
            "karmany evadhikaras te ma phaleshu kadachana. "
            "You have a right to perform your prescribed duty."
        ),
        duration_seconds=50.0,
        whisper_model="tiny",
        summary="Test transcript for orchestrator.",
    )


def _mock_enriched(source_audio: str = "/output/audio/lecture_1.wav") -> EnrichedNotes:
    ref = Reference(
        scripture="BG", chapter="2", verse="47",
        canonical_ref="BG 2.47", segment_index=0,
        context_text="Krishna says in the Bhagavad-gita chapter 2 verse 47",
    )
    ver = VerificationResult(
        reference=ref, status="verified",
        vedabase_url="https://vedabase.io/en/library/bg/2/47/",
        translation="You have a right to perform your prescribed duty.",
        verse_text="karmany evadhikaras te",
    )
    return EnrichedNotes(
        source_transcript=source_audio,
        transcript_text=(
            "Krishna says in the Bhagavad-gita chapter 2 verse 47. "
            "karmany evadhikaras te ma phaleshu kadachana."
        ),
        references_found=[ref],
        verifications=[ver],
        glossary=[GlossaryEntry(
            term="bhakti",
            definition="Devotional service to the Supreme Lord.",
            category="philosophical",
        )],
        thematic_index=ThematicIndex(
            themes=[ThematicTag(
                tag="Karma Yoga",
                confidence=0.9,
                evidence="Discussion of duty without attachment",
            )],
            primary_topic="Karma Yoga",
        ),
        summary="Enriched with 1 verified reference.",
    )


def _mock_book(output_dir: str = "/output") -> BookOutput:
    return BookOutput(
        title="Test Book",
        chapters=[Chapter(
            number=1,
            title="Karma Yoga Discussion",
            content_markdown="# Chapter 1: Karma Yoga Discussion\n\nContent about duty and devotion.",
        )],
        front_matter_markdown="# Test Book\n\nFront matter for the test book.",
        full_book_markdown=(
            "# Test Book\n\nFront matter.\n\n"
            "# Chapter 1: Karma Yoga Discussion\n\nContent about duty and devotion.\n\n"
            "---\nBack matter with glossary and index information."
        ),
        report=CompilationReport(total_chapters=1, total_words=500),
        output_path=f"{output_dir}/final_book.md",
        summary="Compiled 1 chapter, 500 words.",
    )


# ---------------------------------------------------------------------------
# Single URL pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestRunSingleUrlPipeline:

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_single_url_success(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        mock_download.return_value = _mock_manifest(["https://youtube.com/watch?v=TEST"])
        mock_transcribe.return_value = _mock_transcript()
        mock_enrich.return_value = _mock_enriched()
        mock_compile.return_value = _mock_book(str(tmp_path))

        result, pdf_result = run_single_url_pipeline(
            url="https://youtube.com/watch?v=TEST",
            title="Test Book",
            output_dir=str(tmp_path),
        )

        assert result.title == "Test Book"
        assert pdf_result is None
        mock_download.assert_called_once()
        mock_transcribe.assert_called_once()
        mock_enrich.assert_called_once()
        mock_compile.assert_called_once()

    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_single_url_download_failure(self, mock_download, tmp_path):
        manifest = _mock_manifest(["https://youtube.com/watch?v=FAIL"])
        manifest.results[0].success = False
        manifest.results[0].error = "404 Not Found"
        manifest.results[0].audio_path = None
        mock_download.return_value = manifest

        with pytest.raises(PipelineError, match="Download failed"):
            run_single_url_pipeline(
                url="https://youtube.com/watch?v=FAIL",
                output_dir=str(tmp_path),
            )

    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_single_url_transcription_failure(
        self, mock_download, mock_transcribe, tmp_path,
    ):
        mock_download.return_value = _mock_manifest(["https://youtube.com/watch?v=TEST"])
        mock_transcribe.side_effect = Exception("Whisper OOM")

        with pytest.raises(PipelineError, match="Whisper OOM"):
            run_single_url_pipeline(
                url="https://youtube.com/watch?v=TEST",
                output_dir=str(tmp_path),
            )


# ---------------------------------------------------------------------------
# Multi URL pipeline tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestRunMultiUrlPipeline:

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_multi_url_success(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        urls = ["https://youtube.com/watch?v=A", "https://youtube.com/watch?v=B"]
        mock_download.return_value = _mock_manifest(urls)
        mock_transcribe.return_value = _mock_transcript()
        mock_enrich.return_value = _mock_enriched()

        book = _mock_book(str(tmp_path))
        book_multi = BookOutput(
            title="Multi Test",
            chapters=[
                Chapter(number=1, title="Part 1", content_markdown="# Chapter 1: Part 1\n\nContent."),
                Chapter(number=2, title="Part 2", content_markdown="# Chapter 2: Part 2\n\nContent."),
            ],
            front_matter_markdown="# Multi Test\n\nFront matter content here.",
            full_book_markdown="# Multi Test\n\n# Chapter 1\n\nContent.\n\n# Chapter 2\n\nMore content.",
            report=CompilationReport(total_chapters=2, total_words=1000),
            output_path=f"{tmp_path}/final_book.md",
            summary="Compiled 2 chapters.",
        )
        mock_compile.return_value = book_multi

        result, pdf_result = run_multi_url_pipeline(
            urls=urls,
            title="Multi Test",
            output_dir=str(tmp_path),
        )

        assert result.title == "Multi Test"
        assert pdf_result is None
        assert mock_transcribe.call_count == 2
        assert mock_enrich.call_count == 2

    def test_multi_url_empty_list(self, tmp_path):
        with pytest.raises(PipelineError, match="No URLs"):
            run_multi_url_pipeline(urls=[], output_dir=str(tmp_path))

    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_multi_url_all_downloads_fail(self, mock_download, tmp_path):
        urls = ["https://youtube.com/watch?v=A"]
        manifest = _mock_manifest(urls)
        manifest.results[0].success = False
        manifest.results[0].error = "Network error"
        manifest.results[0].audio_path = None
        mock_download.return_value = manifest

        with pytest.raises(PipelineError, match="All downloads failed"):
            run_multi_url_pipeline(urls=urls, output_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# From-agent resume tests
# ---------------------------------------------------------------------------


def _setup_checkpoints(tmp_path, through_agent: int = 4):
    """Save checkpoint files for agents 1 through through_agent."""
    url = "https://youtube.com/watch?v=TEST"
    manifest = _mock_manifest([url], output_dir=str(tmp_path / "audio"))
    save_manifest_checkpoint(manifest, str(tmp_path))
    if through_agent >= 2:
        save_transcript_checkpoint(_mock_transcript(), str(tmp_path), order=1)
    if through_agent >= 3:
        save_enriched_checkpoint(_mock_enriched(), str(tmp_path), order=1)
    if through_agent >= 4:
        save_book_checkpoint(_mock_book(str(tmp_path)), str(tmp_path))


@pytest.mark.pipeline
class TestFromAgentSingleUrl:

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_from_agent_1_saves_checkpoints(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        """A full run (from_agent=1) saves all checkpoint files in per-URL folder."""
        mock_download.return_value = _mock_manifest(
            ["https://youtube.com/watch?v=TEST"],
            output_dir=str(tmp_path / "audio"),
        )
        mock_transcribe.return_value = _mock_transcript()
        mock_enrich.return_value = _mock_enriched()
        mock_compile.return_value = _mock_book(str(tmp_path))

        run_single_url_pipeline(
            url="https://youtube.com/watch?v=TEST",
            output_dir=str(tmp_path),
        )

        # from_agent=1 creates a per-URL subfolder; find it via .latest_run
        latest_file = tmp_path / ".latest_run"
        assert latest_file.exists(), ".latest_run marker should be created"
        run_dir = tmp_path / latest_file.read_text().strip()
        ckpt = run_dir / "checkpoints"
        assert (ckpt / "manifest.json").exists()
        assert (ckpt / "url_001_transcript.json").exists()
        assert (ckpt / "url_001_enriched.json").exists()
        assert (ckpt / "book_output.json").exists()

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_from_agent_3_skips_download_and_transcribe(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        """--from-agent 3 loads checkpoints, skips agents 1 and 2."""
        _setup_checkpoints(tmp_path, through_agent=2)
        mock_enrich.return_value = _mock_enriched()
        mock_compile.return_value = _mock_book(str(tmp_path))

        result, pdf = run_single_url_pipeline(
            url="https://youtube.com/watch?v=TEST",
            output_dir=str(tmp_path),
            from_agent=3,
        )

        assert result.title == "Test Book"
        mock_download.assert_not_called()
        mock_transcribe.assert_not_called()
        mock_enrich.assert_called_once()
        mock_compile.assert_called_once()

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_from_agent_4_skips_through_enrichment(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        """--from-agent 4 loads checkpoints, only compiles."""
        _setup_checkpoints(tmp_path, through_agent=3)
        mock_compile.return_value = _mock_book(str(tmp_path))

        result, pdf = run_single_url_pipeline(
            url="https://youtube.com/watch?v=TEST",
            output_dir=str(tmp_path),
            from_agent=4,
        )

        assert result.title == "Test Book"
        mock_download.assert_not_called()
        mock_transcribe.assert_not_called()
        mock_enrich.assert_not_called()
        mock_compile.assert_called_once()

    def test_from_agent_invalid_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="between 1 and 5"):
            run_single_url_pipeline(
                url="https://youtube.com/watch?v=TEST",
                output_dir=str(tmp_path),
                from_agent=0,
            )

    def test_from_agent_missing_checkpoints_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="missing checkpoint"):
            run_single_url_pipeline(
                url="https://youtube.com/watch?v=TEST",
                output_dir=str(tmp_path),
                from_agent=3,
            )


@pytest.mark.pipeline
class TestFromAgentMultiUrl:

    @patch("lecture_agents.orchestrator.run_compiler_pipeline")
    @patch("lecture_agents.orchestrator.run_enrichment_pipeline")
    @patch("lecture_agents.orchestrator.run_transcription_pipeline")
    @patch("lecture_agents.orchestrator.run_download_pipeline")
    def test_from_agent_3_multi_url(
        self, mock_download, mock_transcribe, mock_enrich, mock_compile, tmp_path,
    ):
        """Multi-URL --from-agent 3 loads per-URL checkpoints."""
        urls = ["https://youtube.com/watch?v=A", "https://youtube.com/watch?v=B"]
        manifest = _mock_manifest(urls, output_dir=str(tmp_path / "audio"))
        save_manifest_checkpoint(manifest, str(tmp_path))
        save_transcript_checkpoint(_mock_transcript(), str(tmp_path), order=1)
        save_transcript_checkpoint(_mock_transcript(), str(tmp_path), order=2)

        mock_enrich.return_value = _mock_enriched()
        mock_compile.return_value = _mock_book(str(tmp_path))

        result, pdf = run_multi_url_pipeline(
            urls=urls,
            output_dir=str(tmp_path),
            from_agent=3,
        )

        assert result.title == "Test Book"
        mock_download.assert_not_called()
        mock_transcribe.assert_not_called()
        assert mock_enrich.call_count == 2

    def test_from_agent_invalid_multi_raises(self, tmp_path):
        with pytest.raises(PipelineError, match="between 1 and 5"):
            run_multi_url_pipeline(
                urls=["url1"], output_dir=str(tmp_path), from_agent=6,
            )
