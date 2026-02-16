"""
Pipeline state: shared dataclasses flowing between agents.

PipelineState is the top-level orchestration state.
PerURLState tracks each URL through the Download -> Transcribe -> Enrich cycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class URLStatus(Enum):
    """Processing status for a single URL in the pipeline."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    TRANSCRIBING = "transcribing"
    TRANSCRIBED = "transcribed"
    ENRICHING = "enriching"
    ENRICHED = "enriched"
    COMPILING = "compiling"
    COMPILED = "compiled"
    PDF_GENERATING = "pdf_generating"
    PDF_GENERATED = "pdf_generated"
    FAILED = "failed"


_PAST_DOWNLOAD = {"downloaded", "transcribed", "enriched", "compiled", "pdf_generated"}
_PAST_TRANSCRIBE = {"transcribed", "enriched", "compiled", "pdf_generated"}
_PAST_ENRICH = {"enriched", "compiled", "pdf_generated"}


@dataclass
class PerURLState:
    """Tracks processing state for a single URL through the pipeline."""

    url: str
    order: int = 0
    status: URLStatus = URLStatus.PENDING

    # Agent 1 outputs
    audio_path: Optional[Path] = None
    download_manifest_entry: Optional[dict] = None

    # Agent 2 outputs
    transcript_path: Optional[Path] = None
    transcript_output: Optional[object] = None  # TranscriptOutput (avoid circular)

    # Agent 3 outputs
    enriched_path: Optional[Path] = None
    enriched_output: Optional[object] = None    # EnrichedNotes (avoid circular)

    # Agent 5 outputs
    pdf_path: Optional[Path] = None

    # Error tracking
    error: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class PipelineState:
    """Top-level state for the entire pipeline run."""

    run_id: str = ""
    mode: str = "single"                # "single" or "multi"
    output_dir: Path = field(default_factory=lambda: Path("output"))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Per-URL states (single URL = list of 1)
    url_states: list[PerURLState] = field(default_factory=list)

    # Global config
    book_title: str = "Lecture Notes"
    speaker: str = ""
    series: str = ""

    # Pipeline-level errors
    errors: list[dict] = field(default_factory=list)

    def add_url(self, url: str, order: int = 0) -> PerURLState:
        """Add a URL to the pipeline and return its state object."""
        state = PerURLState(url=url, order=order or len(self.url_states) + 1)
        self.url_states.append(state)
        return state

    @property
    def all_downloaded(self) -> bool:
        return all(u.status.value in _PAST_DOWNLOAD for u in self.url_states)

    @property
    def all_transcribed(self) -> bool:
        return all(u.status.value in _PAST_TRANSCRIBE for u in self.url_states)

    @property
    def all_enriched(self) -> bool:
        return all(u.status.value in _PAST_ENRICH for u in self.url_states)

    @property
    def failed_urls(self) -> list[PerURLState]:
        return [u for u in self.url_states if u.status == URLStatus.FAILED]

    @property
    def successful_urls(self) -> list[PerURLState]:
        return [u for u in self.url_states if u.status != URLStatus.FAILED]
