"""
Request and response Pydantic models for the REST API.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from lecture_agents.config.constants import PIPELINE_OUTPUT_DIR


class JobStatus(str, Enum):
    """Overall job lifecycle status."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class PipelineStep(str, Enum):
    """Current pipeline step."""

    PENDING = "pending"
    DOWNLOADING = "downloading"
    TRANSCRIBING = "transcribing"
    ENRICHING = "enriching"
    VALIDATING = "validating"
    COMPILING = "compiling"
    PDF_GENERATING = "pdf_generating"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------- Request ----------


class JobCreateRequest(BaseModel):
    """POST /api/v1/jobs request body."""

    urls: list[str] = Field(..., min_length=1, description="One or more audio source URLs")
    title: str = Field(default="Lecture Notes", description="Book title")
    speaker: Optional[str] = Field(default=None, description="Speaker name")
    whisper_model: str = Field(default="large-v3", description="Whisper model size")
    enable_diarization: bool = Field(default=False, description="Enable speaker diarization")
    enable_llm: bool = Field(default=True, description="Enable LLM post-processing")
    generate_pdf: bool = Field(default=False, description="Generate PDF output")
    vad_filter: bool = Field(default=True, description="Enable voice activity detection")
    whisper_backend: str = Field(default="faster-whisper", description="Whisper backend: faster-whisper or whisper.cpp")
    prompt: Optional[str] = Field(default=None, description="Custom instructions for LLM enrichment")
    enrichment_mode: str = Field(
        default="auto",
        description="Enrichment mode: 'auto' (select based on verse count), 'verse-centric' (v6.0), or 'lecture-centric' (v7.0)",
    )
    output_dir: str = Field(default=PIPELINE_OUTPUT_DIR, description="Output directory")


# ---------- Response ----------


class ProgressLogEntry(BaseModel):
    """A timestamped progress log entry."""

    timestamp: datetime
    step: str
    message: str


class URLProgress(BaseModel):
    """Progress for a single URL within a job."""

    url: str
    order: int
    status: str
    error: Optional[str] = None


class JobSummary(BaseModel):
    """Compact job representation for list endpoint."""

    job_id: str
    status: JobStatus
    current_step: PipelineStep
    step_detail: str = ""
    title: str
    url_count: int
    created_at: datetime
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None


class JobDetail(BaseModel):
    """Full job detail for GET /api/v1/jobs/{job_id}."""

    job_id: str
    status: JobStatus
    current_step: PipelineStep
    step_detail: str = ""
    title: str
    urls: list[str]
    url_progress: list[URLProgress]
    progress_log: list[ProgressLogEntry] = Field(default_factory=list)
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    elapsed_seconds: Optional[float] = None
    error: Optional[str] = None
    output_dir: Optional[str] = None
    output_files: list[str] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


class JobRetryRequest(BaseModel):
    """POST /api/v1/jobs/{job_id}/retry request body."""

    from_agent: Optional[int] = Field(
        default=None,
        ge=1,
        le=5,
        description=(
            "Agent to resume from (1=download, 2=transcribe, 3=enrich, 4=compile, 5=pdf). "
            "If omitted, auto-detected from the failed step."
        ),
    )


class JobCreateResponse(BaseModel):
    """POST /api/v1/jobs response."""

    job_id: str
    status: JobStatus
    message: str


class JobOutputResponse(BaseModel):
    """GET /api/v1/jobs/{job_id}/output response."""

    job_id: str
    book: dict
    pdf: Optional[dict] = None


class HealthResponse(BaseModel):
    """GET /api/v1/health response."""

    status: str = "ok"
    version: str = "0.1.0"
    active_jobs: int = 0


# ---------- Browse ----------


class BrowseEntry(BaseModel):
    """A single entry in a directory listing."""

    name: str
    href: str
    is_dir: bool
    size: str | None = None
    modified: str | None = None


class BrowseResponse(BaseModel):
    """GET /api/v1/browse response."""

    path: str
    parent: str | None = None
    entries: list[BrowseEntry]


class SearchEntry(BaseModel):
    """A single search result with breadcrumb context."""

    name: str
    href: str
    is_dir: bool
    size: str | None = None
    breadcrumb: str = ""  # e.g. "ISKCON Swamis / Bhakti Charu Swami / English"


class SearchGroup(BaseModel):
    """A group of search results sharing a common title/path prefix."""

    group_title: str
    entries: list[SearchEntry]


class SearchResponse(BaseModel):
    """GET /api/v1/browse/search response."""

    query: str
    total: int = 0
    groups: list[SearchGroup]


class TopicEntry(BaseModel):
    """A single topic in the taxonomy."""

    slug: str
    label: str
    search_terms: list[str]
    category: str  # "scripture", "festival", "theme", "practice"


class TopicCategory(BaseModel):
    """A category of topics."""

    category: str
    label: str
    topics: list[TopicEntry]


class TopicTaxonomyResponse(BaseModel):
    """GET /api/v1/browse/topics response."""

    categories: list[TopicCategory]
