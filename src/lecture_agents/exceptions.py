"""
Exception hierarchy for Lecture-to-Notes Pipeline.

All pipeline-specific exceptions inherit from LectureBookException.
Each agent domain has its own exception class for targeted error handling.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class ErrorSeverity(Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ProcessingError:
    """Structured error record for pipeline logging and diagnostics."""

    source: str
    error_type: str
    message: str
    severity: ErrorSeverity
    traceback_str: Optional[str] = None
    context: dict = field(default_factory=dict)

    @classmethod
    def from_exception(
        cls,
        source: str,
        error_type: str,
        exception: Exception,
        severity: ErrorSeverity,
        context: Optional[dict] = None,
    ) -> ProcessingError:
        tb = (
            traceback.format_exc()
            if severity in (ErrorSeverity.CRITICAL, ErrorSeverity.WARNING)
            else None
        )
        return cls(
            source=source,
            error_type=error_type,
            message=str(exception),
            severity=severity,
            traceback_str=tb,
            context=context or {},
        )


class LectureBookException(Exception):
    """Base exception for the Lecture-to-Notes pipeline."""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or self.__class__.__name__


class DownloadError(LectureBookException):
    """Raised when audio download fails."""


class AudioNormalizationError(LectureBookException):
    """Raised when ffmpeg audio normalization fails."""


class TranscriptionError(LectureBookException):
    """Raised when Whisper transcription fails."""


class DiarizationError(LectureBookException):
    """Raised when speaker diarization fails."""


class VedabaseFetchError(LectureBookException):
    """Raised when vedabase.io fetch or parsing fails."""


class EnrichmentError(LectureBookException):
    """Raised when scripture enrichment fails."""


class CompilationError(LectureBookException):
    """Raised when book compilation fails."""


class PDFGenerationError(LectureBookException):
    """Raised when PDF generation fails."""


class PipelineError(LectureBookException):
    """Raised for orchestration-level pipeline failures."""


class ConfigurationError(LectureBookException):
    """Raised for missing or invalid configuration."""
