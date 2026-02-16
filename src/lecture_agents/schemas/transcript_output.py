"""
Agent 02: Transcriber Agent — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the Transcriber Agent. Defines TranscriptOutput,
Segment, VocabularyCorrection, and VocabularyLog.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    """A single transcription segment with timing, text, and speaker."""

    start: float = Field(..., ge=0.0, description="Start time in seconds")
    end: float = Field(..., description="End time in seconds")
    text: str = Field(..., min_length=1, description="Transcribed text")
    speaker: Optional[str] = Field(None, description="Speaker label e.g. SPEAKER_00")
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    language: Optional[str] = Field(None, description="ISO 639-1 language code")

    @model_validator(mode="after")
    def validate_timing(self) -> Segment:
        if self.end <= self.start:
            raise ValueError(f"end ({self.end}) must be > start ({self.start})")
        return self


class VocabularyCorrection(BaseModel):
    """Record of a domain vocabulary correction applied to the transcript."""

    original: str = Field(..., min_length=1, description="Text before correction")
    corrected: str = Field(..., min_length=1, description="Text after correction")
    category: Literal["sanskrit", "bengali", "name", "scripture"] = Field(
        ..., description="Type of domain term corrected"
    )
    segment_index: Optional[int] = Field(None, ge=0)


class VocabularyLog(BaseModel):
    """Log of all vocabulary corrections applied during transcription."""

    corrections: list[VocabularyCorrection] = Field(default_factory=list)
    total_corrections: int = Field(default=0, ge=0)
    unique_terms_corrected: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_counts(self) -> VocabularyLog:
        if self.corrections:
            if self.total_corrections < len(self.corrections):
                self.total_corrections = len(self.corrections)
            unique = len({c.corrected for c in self.corrections})
            if self.unique_terms_corrected < unique:
                self.unique_terms_corrected = unique
        return self


class DetectedSloka(BaseModel):
    """A Sanskrit verse (sloka) detected in the transcript."""

    segment_index: int = Field(..., ge=0)
    text: str = Field(..., min_length=5, description="Sanskrit text as transcribed")
    probable_reference: Optional[str] = Field(
        None, description="Best-guess reference e.g. 'BG 2.47'"
    )
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class TranscriptOutput(BaseModel):
    """Top-level output contract for the Transcriber Agent."""

    source_audio: str = Field(..., min_length=1, description="Path to source WAV file")
    segments: list[Segment] = Field(..., min_length=1)
    full_text: str = Field(..., min_length=20, description="Concatenated cleaned transcript")
    duration_seconds: float = Field(..., ge=0.0)
    language: str = Field(default="en", description="Primary detected language")
    whisper_model: str = Field(..., min_length=1, description="Model used e.g. large-v3")
    speakers_detected: int = Field(default=0, ge=0)
    vocabulary_log: VocabularyLog = Field(default_factory=VocabularyLog)
    detected_slokas: list[DetectedSloka] = Field(default_factory=list)
    post_processing_source: Literal["llm", "regex", "none"] = Field(default="none")
    summary: str = Field(..., min_length=10, description="Brief summary of transcription")

    @model_validator(mode="after")
    def validate_segments_within_duration(self) -> TranscriptOutput:
        if self.segments and self.duration_seconds > 0:
            max_end = max(s.end for s in self.segments)
            # Allow 10% tolerance for timing drift
            if max_end > self.duration_seconds * 1.1:
                raise ValueError(
                    f"Segment end time {max_end:.1f}s exceeds "
                    f"audio duration {self.duration_seconds:.1f}s by more than 10%"
                )
        return self
