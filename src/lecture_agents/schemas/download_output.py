"""
Agent 01: Downloader Agent — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the Downloader Agent. Defines DownloadManifest,
DownloadResult, MediaMetadata, and BatchSummary.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class MediaMetadata(BaseModel):
    """Metadata extracted from the downloaded media file or URL."""

    url: str = Field(..., min_length=1)
    title: str = Field(default="Unknown", min_length=1)
    duration_seconds: float = Field(default=0.0, ge=0)
    source_type: Literal["youtube", "direct_http", "local_file"] = Field(...)
    original_format: Optional[str] = Field(None, description="e.g. mp3, m4a, webm")
    file_size_bytes: Optional[int] = Field(None, ge=0)
    upload_date: Optional[str] = Field(None, description="YYYY-MM-DD if available")
    channel: Optional[str] = Field(None, description="YouTube channel or uploader name")
    description: Optional[str] = Field(None)
    speaker: Optional[str] = Field(None, description="From metadata_hints or ID3 tags")
    series: Optional[str] = Field(None, description="Series name from metadata_hints")


class DownloadResult(BaseModel):
    """Result of downloading and normalizing a single URL."""

    url: str = Field(..., min_length=1)
    order: int = Field(default=1, ge=1, description="Sequence position for multi-URL")
    success: bool = Field(...)
    audio_path: Optional[str] = Field(None, description="Path to normalized WAV file")
    original_path: Optional[str] = Field(None, description="Path to original download")
    sha256: Optional[str] = Field(None, description="SHA-256 hash of normalized file")
    metadata: Optional[MediaMetadata] = Field(None)
    error: Optional[str] = Field(None)
    download_duration_seconds: Optional[float] = Field(None, ge=0)

    @model_validator(mode="after")
    def validate_success_has_path(self) -> DownloadResult:
        if self.success and not self.audio_path:
            raise ValueError("Successful download must have audio_path")
        if not self.success and not self.error:
            raise ValueError("Failed download must have error message")
        return self


class BatchSummary(BaseModel):
    """Summary statistics for a batch download operation."""

    total_urls: int = Field(..., ge=1)
    successful: int = Field(..., ge=0)
    failed: int = Field(..., ge=0)
    skipped_duplicate: int = Field(default=0, ge=0)
    total_duration_seconds: float = Field(default=0.0, ge=0)
    total_size_bytes: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> BatchSummary:
        if self.successful + self.failed + self.skipped_duplicate != self.total_urls:
            raise ValueError(
                f"successful ({self.successful}) + failed ({self.failed}) "
                f"+ skipped ({self.skipped_duplicate}) must equal total_urls ({self.total_urls})"
            )
        return self


class DownloadManifest(BaseModel):
    """Top-level output contract for the Downloader Agent."""

    results: list[DownloadResult] = Field(..., min_length=1)
    batch_summary: BatchSummary = Field(...)
    output_dir: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=10, description="Human-readable summary")

    @model_validator(mode="after")
    def validate_result_count(self) -> DownloadManifest:
        if len(self.results) != self.batch_summary.total_urls:
            raise ValueError(
                f"results length ({len(self.results)}) must match "
                f"batch_summary.total_urls ({self.batch_summary.total_urls})"
            )
        return self
