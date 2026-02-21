"""
Job store with background thread execution and JSON persistence.

Jobs are stored in-memory for active use and persisted to
{output_dir}/job_meta.json so they survive server restarts.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from lecture_agents.api.models import JobCreateRequest, JobRetryRequest, JobStatus, PipelineStep
from lecture_agents.config.constants import (
    CHECKPOINT_DIR_NAME,
    JOB_METADATA_FILENAME,
    PIPELINE_OUTPUT_DIR,
)
from lecture_agents.schemas.compiler_output import BookOutput
from lecture_agents.schemas.pdf_output import PDFOutput

logger = logging.getLogger(__name__)

MAX_CONCURRENT_JOBS = 2


@dataclass
class ProgressEntry:
    """A single timestamped progress log entry."""

    timestamp: datetime
    step: str
    message: str


class JobCancelled(Exception):
    """Raised when a job is cancelled by the user."""


@dataclass
class JobRecord:
    """Record for a single pipeline job."""

    job_id: str
    urls: list[str]
    title: str
    config: dict
    status: JobStatus = JobStatus.QUEUED
    current_step: PipelineStep = PipelineStep.PENDING
    step_detail: str = ""
    url_progress: list[dict] = field(default_factory=list)
    progress_log: list[ProgressEntry] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    output_dir: Optional[str] = None
    output_files: list[str] = field(default_factory=list)
    book_output: Optional[BookOutput] = None
    pdf_output: Optional[PDFOutput] = None
    _cancel_event: threading.Event = field(default_factory=threading.Event)


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def _serialize_job(record: JobRecord) -> dict:
    """Convert a JobRecord to a JSON-serializable dict (excluding large outputs)."""

    def _dt(dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None

    return {
        "job_id": record.job_id,
        "urls": record.urls,
        "title": record.title,
        "config": record.config,
        "status": record.status.value,
        "current_step": record.current_step.value,
        "step_detail": record.step_detail,
        "url_progress": record.url_progress,
        "progress_log": [
            {"timestamp": _dt(e.timestamp), "step": e.step, "message": e.message}
            for e in record.progress_log
        ],
        "created_at": _dt(record.created_at),
        "started_at": _dt(record.started_at),
        "completed_at": _dt(record.completed_at),
        "error": record.error,
        "output_dir": record.output_dir,
        "output_files": record.output_files,
    }


def _deserialize_job(data: dict) -> JobRecord:
    """Reconstruct a JobRecord from a persisted dict."""

    def _dt(val: Optional[str]) -> Optional[datetime]:
        return datetime.fromisoformat(val) if val else None

    return JobRecord(
        job_id=data["job_id"],
        urls=data["urls"],
        title=data["title"],
        config=data.get("config", {}),
        status=JobStatus(data["status"]),
        current_step=PipelineStep(data["current_step"]),
        step_detail=data.get("step_detail", ""),
        url_progress=data.get("url_progress", []),
        progress_log=[
            ProgressEntry(
                timestamp=_dt(e["timestamp"]) or datetime.now(),
                step=e["step"],
                message=e["message"],
            )
            for e in data.get("progress_log", [])
        ],
        created_at=_dt(data.get("created_at")) or datetime.now(),
        started_at=_dt(data.get("started_at")),
        completed_at=_dt(data.get("completed_at")),
        error=data.get("error"),
        output_dir=data.get("output_dir"),
        output_files=data.get("output_files", []),
    )


class JobManager:
    """Job store with ThreadPoolExecutor for background pipeline runs.

    Persists job metadata to ``{output_dir}/job_meta.json`` and reloads
    completed/failed jobs on startup so they survive server restarts.
    """

    def __init__(self, max_workers: int = MAX_CONCURRENT_JOBS):
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="pipeline-worker",
        )
        self._load_jobs()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_job(self, record: JobRecord) -> None:
        """Persist job metadata to disk (best-effort, non-blocking)."""
        if not record.output_dir:
            return
        try:
            path = Path(record.output_dir) / JOB_METADATA_FILENAME
            path.write_text(json.dumps(_serialize_job(record), indent=2))
            logger.debug("Saved job metadata: %s", path)
        except Exception as e:
            logger.warning("Failed to save job metadata for %s: %s", record.job_id, e)

    def _load_jobs(self) -> None:
        """Scan output directories for persisted job metadata on startup."""
        output_root = Path(PIPELINE_OUTPUT_DIR)
        if not output_root.is_dir():
            return

        loaded = 0
        discovered_dirs: set[str] = set()

        # Phase 1: Load jobs from existing job_meta.json files
        for meta_path in output_root.glob(f"*/{JOB_METADATA_FILENAME}"):
            try:
                data = json.loads(meta_path.read_text())
                record = _deserialize_job(data)
                discovered_dirs.add(str(meta_path.parent))

                # Mark non-terminal jobs as failed (interrupted by restart)
                if record.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                    record.status = JobStatus.FAILED
                    record.current_step = PipelineStep.FAILED
                    record.step_detail = "Interrupted by server restart"
                    record.error = "Interrupted by server restart"
                    record.completed_at = datetime.now()
                    self._save_job(record)

                self._jobs[record.job_id] = record
                loaded += 1
            except Exception as e:
                logger.warning("Failed to load job from %s: %s", meta_path, e)

        # Phase 2: Discover completed runs that predate job persistence
        for book_path in output_root.glob(
            f"*/{CHECKPOINT_DIR_NAME}/book_output.json"
        ):
            run_dir = str(book_path.parent.parent)
            if run_dir in discovered_dirs:
                continue
            try:
                book = BookOutput.model_validate_json(book_path.read_text())
                dir_name = book_path.parent.parent.name
                # Use last 12 chars of directory name as synthetic job_id
                job_id = dir_name[-12:] if len(dir_name) >= 12 else dir_name

                # Discover output files
                out_dir = book_path.parent.parent
                output_files = sorted(
                    f.name for f in out_dir.iterdir()
                    if f.is_file() and f.suffix in (".md", ".pdf")
                )

                # Get manifest for URL info if available
                manifest_path = book_path.parent / "manifest.json"
                urls: list[str] = []
                if manifest_path.exists():
                    try:
                        manifest_data = json.loads(manifest_path.read_text())
                        urls = [
                            r.get("url", "") for r in manifest_data.get("results", [])
                        ]
                    except Exception:
                        pass

                record = JobRecord(
                    job_id=job_id,
                    urls=urls,
                    title=book.title,
                    config={},
                    status=JobStatus.COMPLETED,
                    current_step=PipelineStep.COMPLETED,
                    step_detail="Pipeline completed successfully",
                    output_dir=run_dir,
                    output_files=output_files,
                    book_output=book,
                )
                self._jobs[record.job_id] = record
                self._save_job(record)
                loaded += 1
            except Exception as e:
                logger.warning(
                    "Failed to discover job from %s: %s", book_path, e
                )

        if loaded:
            logger.info("Loaded %d persisted job(s) from disk", loaded)

    def _ensure_book_output(self, record: JobRecord) -> None:
        """Lazily load book_output from checkpoint if not in memory."""
        if record.book_output is not None:
            return
        if record.status != JobStatus.COMPLETED or not record.output_dir:
            return
        ckpt = Path(record.output_dir) / CHECKPOINT_DIR_NAME / "book_output.json"
        if ckpt.exists():
            try:
                record.book_output = BookOutput.model_validate_json(ckpt.read_text())
                logger.debug("Loaded book_output from checkpoint for job %s", record.job_id)
            except Exception as e:
                logger.warning("Failed to load book checkpoint for %s: %s", record.job_id, e)

    def _ensure_pdf_output(self, record: JobRecord) -> None:
        """Lazily reconstruct pdf_output from output files if not in memory."""
        if record.pdf_output is not None:
            return
        if record.status != JobStatus.COMPLETED or not record.output_dir:
            return
        out_dir = Path(record.output_dir)
        pdf_files = list(out_dir.glob("*.pdf"))
        if pdf_files:
            pdf_path = pdf_files[0]
            try:
                record.pdf_output = PDFOutput(
                    pdf_path=str(pdf_path),
                    title=record.title,
                    total_pages=0,
                    file_size_kb=pdf_path.stat().st_size / 1024,
                    summary=f"PDF: {pdf_path.name}",
                )
                logger.debug("Reconstructed pdf_output for job %s", record.job_id)
            except Exception as e:
                logger.warning("Failed to reconstruct pdf_output for %s: %s", record.job_id, e)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def submit_job(self, request: JobCreateRequest) -> JobRecord:
        """Create a new job and submit it to the thread pool."""
        job_id = uuid.uuid4().hex[:12]
        record = JobRecord(
            job_id=job_id,
            urls=list(request.urls),
            title=request.title,
            config={
                "speaker": request.speaker,
                "whisper_model": request.whisper_model,
                "enable_diarization": request.enable_diarization,
                "enable_llm": request.enable_llm,
                "generate_pdf": request.generate_pdf,
                "vad_filter": request.vad_filter,
                "whisper_backend": request.whisper_backend,
                "prompt": request.prompt,
                "enrichment_mode": request.enrichment_mode,
                "output_dir": request.output_dir,
            },
            url_progress=[
                {"url": url, "order": i + 1, "status": "pending", "error": None}
                for i, url in enumerate(request.urls)
            ],
        )
        with self._lock:
            self._jobs[job_id] = record
        self._executor.submit(self._run_pipeline, record)
        return record

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        with self._lock:
            record = self._jobs.get(job_id)
        if record:
            self._ensure_book_output(record)
            self._ensure_pdf_output(record)
        return record

    def list_jobs(self) -> list[JobRecord]:
        with self._lock:
            return list(self._jobs.values())

    def _run_pipeline(self, record: JobRecord, from_agent: int = 1) -> None:
        """Execute the pipeline in a background thread."""
        from lecture_agents.orchestrator import (
            run_multi_url_pipeline,
            run_single_url_pipeline,
        )

        record.status = JobStatus.RUNNING
        record.started_at = datetime.now()

        agent_to_step = {
            1: PipelineStep.DOWNLOADING,
            2: PipelineStep.TRANSCRIBING,
            3: PipelineStep.ENRICHING,
            4: PipelineStep.COMPILING,
            5: PipelineStep.PDF_GENERATING,
        }
        record.current_step = agent_to_step.get(from_agent, PipelineStep.DOWNLOADING)

        step_descriptions = {
            "downloading": "Downloading audio from source URL",
            "transcribing": "Transcribing audio with Whisper",
            "enriching": "Enriching transcript with scripture references",
            "validating": "Validating transcription and enrichment quality",
            "compiling": "Compiling enriched notes into structured book",
            "pdf_generating": "Generating styled PDF from Markdown",
        }

        def _on_progress(step: str, detail: str = "") -> None:
            if record._cancel_event.is_set():
                raise JobCancelled("Job cancelled by user")
            record.current_step = PipelineStep(step)
            record.step_detail = detail or step_descriptions.get(step, "")
            record.progress_log.append(ProgressEntry(
                timestamp=datetime.now(),
                step=step,
                message=detail or step_descriptions.get(step, step),
            ))
            # Keep url_progress in sync
            for up in record.url_progress:
                if up["status"] not in ("completed", "failed"):
                    up["status"] = step

        initial_step = agent_to_step.get(from_agent, PipelineStep.DOWNLOADING).value
        _on_progress(initial_step)

        try:
            kwargs = {
                "title": record.title,
                "output_dir": record.config["output_dir"],
                "speaker": record.config["speaker"],
                "whisper_model": record.config["whisper_model"],
                "enable_diarization": record.config["enable_diarization"],
                "enable_llm": record.config["enable_llm"],
                "generate_pdf": record.config["generate_pdf"],
                "vad_filter": record.config["vad_filter"],
                "whisper_backend": record.config["whisper_backend"],
                "prompt": record.config["prompt"],
                "enrichment_mode": record.config.get("enrichment_mode", "auto"),
                "progress_callback": _on_progress,
                "from_agent": from_agent,
            }

            if len(record.urls) == 1:
                book, pdf = run_single_url_pipeline(url=record.urls[0], **kwargs)
            else:
                book, pdf = run_multi_url_pipeline(urls=record.urls, **kwargs)

            record.book_output = book
            record.pdf_output = pdf
            record.output_dir = str(Path(book.output_path).parent)
            record.status = JobStatus.COMPLETED
            record.current_step = PipelineStep.COMPLETED
            record.step_detail = "Pipeline completed successfully"
            record.completed_at = datetime.now()
            for up in record.url_progress:
                up["status"] = "completed"
            record.progress_log.append(ProgressEntry(
                timestamp=record.completed_at,
                step="completed",
                message=f"Pipeline completed: {book.report.total_chapters} chapters, "
                        f"{book.report.total_words} words",
            ))

            # Discover output files
            out_dir = Path(book.output_path).parent
            record.output_files = sorted(
                f.name
                for f in out_dir.iterdir()
                if f.is_file() and f.suffix in (".md", ".pdf")
            )
            logger.info("Job %s completed: %s", record.job_id, book.output_path)

        except JobCancelled:
            logger.info("Job %s cancelled by user", record.job_id)
            record.status = JobStatus.FAILED
            record.current_step = PipelineStep.FAILED
            record.step_detail = "Cancelled by user"
            record.error = "Cancelled by user"
            record.completed_at = datetime.now()
            for up in record.url_progress:
                if up["status"] not in ("completed",):
                    up["status"] = "cancelled"
                    up["error"] = "Cancelled by user"
            record.progress_log.append(ProgressEntry(
                timestamp=record.completed_at,
                step="failed",
                message="Job cancelled by user",
            ))

        except Exception as e:
            logger.exception("Pipeline job %s failed", record.job_id)
            record.status = JobStatus.FAILED
            record.current_step = PipelineStep.FAILED
            record.step_detail = str(e)
            record.error = str(e)
            record.completed_at = datetime.now()
            for up in record.url_progress:
                if up["status"] not in ("completed",):
                    up["status"] = "failed"
                    up["error"] = str(e)
            record.progress_log.append(ProgressEntry(
                timestamp=record.completed_at,
                step="failed",
                message=str(e),
            ))

        # Persist job metadata to disk (both success and failure)
        self._save_job(record)

    def cancel_job(self, job_id: str, force: bool = False) -> Optional[JobRecord]:
        """Signal a running job to cancel at the next step boundary.

        If *force* is True (or the cancel event was already set from a prior
        attempt), immediately mark the job as failed so it doesn't remain
        stuck in 'running' state when the worker thread has died.
        """
        with self._lock:
            record = self._jobs.get(job_id)
        if not record or record.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
            return record

        already_requested = record._cancel_event.is_set()
        record._cancel_event.set()

        # Force-fail orphaned jobs (second cancel attempt, or explicit force)
        if force or already_requested:
            logger.info("Force-cancelling orphaned job %s", job_id)
            record.status = JobStatus.FAILED
            record.current_step = PipelineStep.FAILED
            record.step_detail = "Cancelled by user (force)"
            record.error = "Cancelled by user"
            record.completed_at = datetime.now()
            for up in record.url_progress:
                if up.get("status") not in ("completed", "failed"):
                    up["status"] = "cancelled"
                    up["error"] = "Cancelled by user"
            record.progress_log.append(ProgressEntry(
                timestamp=record.completed_at,
                step="failed",
                message="Force-cancelled by user",
            ))
            self._save_job(record)

        return record

    def _detect_resume_agent(self, record: JobRecord) -> int:
        """Determine the best from_agent for retrying a failed job.

        Inspects which checkpoints exist and the failed step to pick the
        earliest agent that needs re-running.
        """
        if not record.output_dir:
            return 1

        ckpt = Path(record.output_dir) / CHECKPOINT_DIR_NAME

        # Map failed step → which agent to re-run
        step_to_agent = {
            PipelineStep.DOWNLOADING: 1,
            PipelineStep.TRANSCRIBING: 2,
            PipelineStep.ENRICHING: 3,
            # Validation failures usually indicate transcript/enrichment issues
            PipelineStep.VALIDATING: 2,
            PipelineStep.COMPILING: 4,
            PipelineStep.PDF_GENERATING: 5,
        }

        # Default from the failed step
        default = step_to_agent.get(record.current_step, 1)

        # But only if earlier checkpoints exist to support it
        if default >= 2 and not (ckpt / "manifest.json").exists():
            return 1
        if default >= 3 and not (ckpt / "url_001_transcript.json").exists():
            return 2

        return default

    def retry_job(self, job_id: str, request: Optional[JobRetryRequest] = None) -> JobRecord:
        """Retry a failed job, resuming from checkpoints.

        Creates a new JobRecord that reuses the original job's config, URLs,
        and output_dir, then passes from_agent to skip completed stages.
        """
        with self._lock:
            original = self._jobs.get(job_id)
        if not original:
            raise ValueError(f"Job {job_id} not found")
        if original.status != JobStatus.FAILED:
            raise ValueError(f"Job {job_id} is {original.status.value}, not failed")

        from_agent = (request.from_agent if request and request.from_agent else None) \
            or self._detect_resume_agent(original)

        # Create new job record reusing original config
        new_job_id = uuid.uuid4().hex[:12]
        new_record = JobRecord(
            job_id=new_job_id,
            urls=original.urls,
            title=original.title,
            config={**original.config, "from_agent": from_agent},
            output_dir=original.output_dir,
            url_progress=[
                {"url": url, "order": i + 1, "status": "pending", "error": None}
                for i, url in enumerate(original.urls)
            ],
        )
        new_record.progress_log.append(ProgressEntry(
            timestamp=datetime.now(),
            step="retry",
            message=f"Retrying from agent {from_agent} (original job: {job_id})",
        ))

        with self._lock:
            self._jobs[new_job_id] = new_record
        self._executor.submit(self._run_pipeline, new_record, from_agent)

        logger.info(
            "Job %s retrying as %s (from_agent=%d)",
            job_id, new_job_id, from_agent,
        )
        return new_record

    def shutdown(self) -> None:
        """Graceful shutdown: wait for running jobs to finish."""
        self._executor.shutdown(wait=True)
