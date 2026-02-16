"""
Level 2: Pipeline tests for Agent 01 (Downloader).

Tests the run_download_pipeline() deterministic path with mocked downloads.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lecture_agents.agents.downloader_agent import (
    _detect_source_type,
    run_download_pipeline,
)
from lecture_agents.exceptions import DownloadError


# ---------------------------------------------------------------------------
# Source type detection tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestDetectSourceType:

    def test_youtube_url(self):
        assert _detect_source_type("https://www.youtube.com/watch?v=abc123") == "youtube"

    def test_youtu_be_short_url(self):
        assert _detect_source_type("https://youtu.be/abc123") == "youtube"

    def test_direct_mp3_url(self):
        assert _detect_source_type("https://example.com/lecture.mp3") == "direct_http"

    def test_direct_wav_url(self):
        assert _detect_source_type("https://example.com/audio.wav") == "direct_http"

    def test_local_file(self):
        assert _detect_source_type("/path/to/file.wav") == "local_file"

    def test_file_uri(self):
        assert _detect_source_type("file:///path/to/file.wav") == "local_file"

    def test_unknown_url_defaults_to_youtube(self):
        # yt-dlp supports many sites, so unknown URLs default to it
        assert _detect_source_type("https://example.com/page") == "youtube"

    def test_soundcloud_url(self):
        assert _detect_source_type("https://soundcloud.com/artist/track") == "youtube"


# ---------------------------------------------------------------------------
# Pipeline tests (mocked downloads)
# ---------------------------------------------------------------------------


def _mock_ytdlp_success(url, output_dir, **kwargs):
    """Mock yt-dlp download that creates a fake file."""
    fake_path = Path(output_dir) / "fake_audio.webm"
    fake_path.parent.mkdir(parents=True, exist_ok=True)
    fake_path.write_bytes(b"\x00" * 1000)
    return {
        "success": True,
        "file_path": str(fake_path),
        "metadata": {
            "title": "Test Lecture on Bhagavad-gita",
            "duration_seconds": 3600.0,
            "uploader": "ISKCON Channel",
            "upload_date": "20240115",
        },
        "error": None,
    }


def _mock_normalize_success(input_path, output_path=None, **kwargs):
    """Mock ffmpeg normalization that creates a fake WAV."""
    out = output_path or input_path.replace(".webm", ".wav")
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_bytes(b"\x00" * 2000)
    return {
        "success": True,
        "output_path": out,
        "duration_seconds": 3600.0,
        "error": None,
    }


@pytest.mark.pipeline
class TestRunDownloadPipeline:

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp", side_effect=_mock_ytdlp_success)
    @patch("lecture_agents.agents.downloader_agent.normalize_to_wav", side_effect=_mock_normalize_success)
    @patch("lecture_agents.agents.downloader_agent.compute_sha256", return_value="abc123hash")
    @patch("lecture_agents.agents.downloader_agent.get_audio_duration", return_value=3600.0)
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_produces_valid_manifest(
        self, mock_sleep, mock_duration, mock_hash, mock_normalize, mock_ytdlp, tmp_path
    ):
        manifest = run_download_pipeline(
            ["https://youtube.com/watch?v=test1"],
            output_dir=str(tmp_path / "output"),
        )
        assert manifest.batch_summary.total_urls == 1
        assert manifest.batch_summary.successful == 1
        assert manifest.results[0].success is True
        assert manifest.results[0].audio_path is not None

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp")
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_handles_download_failure(self, mock_sleep, mock_ytdlp, tmp_path):
        mock_ytdlp.return_value = {
            "success": False,
            "file_path": None,
            "metadata": None,
            "error": "Video not available",
        }
        manifest = run_download_pipeline(
            ["https://youtube.com/watch?v=bad_video"],
            output_dir=str(tmp_path / "output"),
        )
        assert manifest.batch_summary.failed == 1
        assert manifest.results[0].success is False
        assert "not available" in manifest.results[0].error

    def test_pipeline_rejects_empty_urls(self):
        with pytest.raises(DownloadError, match="No URLs"):
            run_download_pipeline([])

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp", side_effect=_mock_ytdlp_success)
    @patch("lecture_agents.agents.downloader_agent.normalize_to_wav", side_effect=_mock_normalize_success)
    @patch("lecture_agents.agents.downloader_agent.compute_sha256", return_value="abc123hash")
    @patch("lecture_agents.agents.downloader_agent.get_audio_duration", return_value=3600.0)
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_batch_mode(
        self, mock_sleep, mock_duration, mock_hash, mock_normalize, mock_ytdlp, tmp_path
    ):
        urls = [
            "https://youtube.com/watch?v=test1",
            "https://youtube.com/watch?v=test2",
            "https://youtube.com/watch?v=test3",
        ]
        manifest = run_download_pipeline(urls, output_dir=str(tmp_path / "output"))
        assert manifest.batch_summary.total_urls == 3
        assert manifest.batch_summary.successful == 3
        assert len(manifest.results) == 3

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp", side_effect=_mock_ytdlp_success)
    @patch("lecture_agents.agents.downloader_agent.normalize_to_wav", side_effect=_mock_normalize_success)
    @patch("lecture_agents.agents.downloader_agent.compute_sha256", return_value="abc123hash")
    @patch("lecture_agents.agents.downloader_agent.get_audio_duration", return_value=3600.0)
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_deduplication(
        self, mock_sleep, mock_duration, mock_hash, mock_normalize, mock_ytdlp, tmp_path
    ):
        urls = [
            "https://youtube.com/watch?v=same",
            "https://youtube.com/watch?v=same",
        ]
        manifest = run_download_pipeline(urls, output_dir=str(tmp_path / "output"))
        assert manifest.batch_summary.total_urls == 2
        # Second URL references the first without re-downloading
        assert mock_ytdlp.call_count == 1

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp", side_effect=_mock_ytdlp_success)
    @patch("lecture_agents.agents.downloader_agent.normalize_to_wav")
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_normalization_failure(
        self, mock_sleep, mock_normalize, mock_ytdlp, tmp_path
    ):
        mock_normalize.return_value = {
            "success": False,
            "output_path": None,
            "duration_seconds": None,
            "error": "ffmpeg not found",
        }
        manifest = run_download_pipeline(
            ["https://youtube.com/watch?v=test1"],
            output_dir=str(tmp_path / "output"),
        )
        assert manifest.batch_summary.failed == 1
        assert "Normalization" in manifest.results[0].error

    @patch("lecture_agents.agents.downloader_agent.download_with_ytdlp", side_effect=_mock_ytdlp_success)
    @patch("lecture_agents.agents.downloader_agent.compute_sha256", return_value="abc123hash")
    @patch("lecture_agents.agents.downloader_agent.get_audio_duration", return_value=15.0)
    @patch("lecture_agents.agents.downloader_agent.time.sleep")
    def test_pipeline_rejects_short_audio(
        self, mock_sleep, mock_duration, mock_hash, mock_ytdlp, tmp_path
    ):
        def _mock_normalize_short(input_path, output_path=None, **kwargs):
            out = output_path or input_path.replace(".webm", ".wav")
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(b"\x00" * 2000)
            return {
                "success": True,
                "output_path": out,
                "duration_seconds": 15.0,
                "error": None,
            }

        with patch(
            "lecture_agents.agents.downloader_agent.normalize_to_wav",
            side_effect=_mock_normalize_short,
        ):
            manifest = run_download_pipeline(
                ["https://youtube.com/watch?v=short"],
                output_dir=str(tmp_path / "output"),
            )
        assert manifest.batch_summary.failed == 1
        assert "too short" in manifest.results[0].error
