"""
Level 1: Schema validation tests for Agent 01 (Downloader).

Tests Pydantic model constraints without any I/O or LLM calls.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lecture_agents.schemas.download_output import (
    BatchSummary,
    DownloadManifest,
    DownloadResult,
    MediaMetadata,
)


# ---------------------------------------------------------------------------
# Factory helpers (minimal valid objects)
# ---------------------------------------------------------------------------


def _make_metadata(**overrides) -> MediaMetadata:
    defaults = {
        "url": "https://example.com/lecture.mp3",
        "title": "Test Lecture",
        "duration_seconds": 3600.0,
        "source_type": "youtube",
    }
    return MediaMetadata(**(defaults | overrides))


def _make_result(**overrides) -> DownloadResult:
    defaults = {
        "url": "https://example.com/lecture.mp3",
        "order": 1,
        "success": True,
        "audio_path": "/output/audio/lecture_001.wav",
        "sha256": "abc123",
        "metadata": _make_metadata(),
    }
    return DownloadResult(**(defaults | overrides))


def _make_summary(**overrides) -> BatchSummary:
    defaults = {
        "total_urls": 1,
        "successful": 1,
        "failed": 0,
    }
    return BatchSummary(**(defaults | overrides))


def _make_manifest(**overrides) -> DownloadManifest:
    defaults = {
        "results": [_make_result()],
        "batch_summary": _make_summary(),
        "output_dir": "/output",
        "summary": "Downloaded 1/1 URLs. Total audio: 60.0 minutes.",
    }
    return DownloadManifest(**(defaults | overrides))


# ---------------------------------------------------------------------------
# MediaMetadata tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestMediaMetadata:

    def test_valid_metadata_parses(self):
        m = _make_metadata()
        assert m.title == "Test Lecture"
        assert m.duration_seconds == 3600.0

    def test_source_type_enum(self):
        for st in ["youtube", "direct_http", "local_file"]:
            m = _make_metadata(source_type=st)
            assert m.source_type == st

    def test_invalid_source_type(self):
        with pytest.raises(ValidationError):
            _make_metadata(source_type="ftp")

    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            _make_metadata(duration_seconds=-1.0)

    def test_empty_url_rejected(self):
        with pytest.raises(ValidationError):
            _make_metadata(url="")


# ---------------------------------------------------------------------------
# DownloadResult tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestDownloadResult:

    def test_valid_result_parses(self):
        r = _make_result()
        assert r.success is True
        assert r.audio_path is not None

    def test_successful_requires_audio_path(self):
        with pytest.raises(ValidationError, match="audio_path"):
            _make_result(success=True, audio_path=None)

    def test_failed_requires_error(self):
        with pytest.raises(ValidationError, match="error"):
            _make_result(success=False, audio_path=None, error=None)

    def test_failed_result_with_error(self):
        r = _make_result(success=False, audio_path=None, error="404 Not Found")
        assert r.success is False
        assert r.error == "404 Not Found"

    def test_order_must_be_positive(self):
        with pytest.raises(ValidationError):
            _make_result(order=0)

    def test_url_not_empty(self):
        with pytest.raises(ValidationError):
            _make_result(url="")


# ---------------------------------------------------------------------------
# BatchSummary tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestBatchSummary:

    def test_valid_summary_parses(self):
        s = _make_summary()
        assert s.total_urls == 1

    def test_counts_must_match(self):
        with pytest.raises(ValidationError, match="must equal"):
            _make_summary(total_urls=3, successful=1, failed=1)

    def test_counts_with_duplicates(self):
        s = _make_summary(total_urls=5, successful=3, failed=1, skipped_duplicate=1)
        assert s.total_urls == 5

    def test_negative_count_rejected(self):
        with pytest.raises(ValidationError):
            _make_summary(total_urls=1, successful=-1, failed=2)


# ---------------------------------------------------------------------------
# DownloadManifest tests
# ---------------------------------------------------------------------------


@pytest.mark.schema
class TestDownloadManifest:

    def test_valid_manifest_parses(self):
        m = _make_manifest()
        assert len(m.results) == 1

    def test_result_count_must_match_summary(self):
        with pytest.raises(ValidationError, match="results length"):
            _make_manifest(
                results=[_make_result(), _make_result(order=2)],
                batch_summary=_make_summary(total_urls=1, successful=1, failed=0),
            )

    def test_empty_results_rejected(self):
        with pytest.raises(ValidationError):
            _make_manifest(results=[])

    def test_summary_min_length(self):
        with pytest.raises(ValidationError):
            _make_manifest(summary="short")

    def test_multi_url_manifest(self):
        r1 = _make_result(url="url1", order=1)
        r2 = _make_result(url="url2", order=2)
        s = _make_summary(total_urls=2, successful=2, failed=0)
        m = _make_manifest(results=[r1, r2], batch_summary=s)
        assert len(m.results) == 2
