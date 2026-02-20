"""
Checkpoint manager for the Lecture-to-Notes pipeline.

Saves and loads intermediate Pydantic model outputs as JSON files
in the output_dir/checkpoints/ directory, enabling pipeline resumption
from any agent via --from-agent N.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from lecture_agents.config.constants import CHECKPOINT_DIR_NAME
from lecture_agents.exceptions import PipelineError
from lecture_agents.schemas.compiler_output import BookOutput
from lecture_agents.schemas.download_output import DownloadManifest
from lecture_agents.schemas.enrichment_output import EnrichedNotes
from lecture_agents.schemas.transcript_output import TranscriptOutput
from lecture_agents.schemas.validation_output import ValidationReport

logger = logging.getLogger(__name__)


def _checkpoint_dir(output_dir: str) -> Path:
    """Return the checkpoints directory, creating it if needed."""
    d = Path(output_dir) / CHECKPOINT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


# ---------------------------------------------------------------------------
# Save functions (called after each agent, always)
# ---------------------------------------------------------------------------


def save_manifest_checkpoint(manifest: DownloadManifest, output_dir: str) -> Path:
    """Save DownloadManifest to checkpoints/manifest.json."""
    path = _checkpoint_dir(output_dir) / "manifest.json"
    path.write_text(manifest.model_dump_json(indent=2))
    logger.info("Checkpoint saved: %s", path)
    return path


def save_transcript_checkpoint(
    transcript: TranscriptOutput, output_dir: str, order: int
) -> Path:
    """Save TranscriptOutput to checkpoints/url_NNN_transcript.json."""
    path = _checkpoint_dir(output_dir) / f"url_{order:03d}_transcript.json"
    path.write_text(transcript.model_dump_json(indent=2))
    logger.info("Checkpoint saved: %s", path)
    return path


def save_enriched_checkpoint(
    enriched: EnrichedNotes, output_dir: str, order: int
) -> Path:
    """Save EnrichedNotes to checkpoints/url_NNN_enriched.json."""
    path = _checkpoint_dir(output_dir) / f"url_{order:03d}_enriched.json"
    path.write_text(enriched.model_dump_json(indent=2))
    logger.info("Checkpoint saved: %s", path)
    return path


def save_validation_checkpoint(
    report: ValidationReport, output_dir: str, order: int
) -> Path:
    """Save ValidationReport to checkpoints/url_NNN_validation.json."""
    path = _checkpoint_dir(output_dir) / f"url_{order:03d}_validation.json"
    path.write_text(report.model_dump_json(indent=2))
    logger.info("Checkpoint saved: %s", path)
    return path


def save_book_checkpoint(book: BookOutput, output_dir: str) -> Path:
    """Save BookOutput to checkpoints/book_output.json."""
    path = _checkpoint_dir(output_dir) / "book_output.json"
    path.write_text(book.model_dump_json(indent=2))
    logger.info("Checkpoint saved: %s", path)
    return path


# ---------------------------------------------------------------------------
# Load functions (called when skipping agents)
# ---------------------------------------------------------------------------


def load_manifest_checkpoint(output_dir: str) -> DownloadManifest:
    """Load DownloadManifest from checkpoints/manifest.json."""
    path = Path(output_dir) / CHECKPOINT_DIR_NAME / "manifest.json"
    if not path.exists():
        raise PipelineError(
            f"Cannot load manifest checkpoint: file not found at {path}"
        )
    manifest = DownloadManifest.model_validate_json(path.read_text())
    logger.info("Checkpoint loaded: %s (%d results)", path, len(manifest.results))
    return manifest


def load_transcript_checkpoint(output_dir: str, order: int) -> TranscriptOutput:
    """Load TranscriptOutput from checkpoints/url_NNN_transcript.json."""
    path = Path(output_dir) / CHECKPOINT_DIR_NAME / f"url_{order:03d}_transcript.json"
    if not path.exists():
        raise PipelineError(
            f"Cannot load transcript checkpoint: file not found at {path}"
        )
    transcript = TranscriptOutput.model_validate_json(path.read_text())
    logger.info("Checkpoint loaded: %s (%d segments)", path, len(transcript.segments))
    return transcript


def load_enriched_checkpoint(output_dir: str, order: int) -> EnrichedNotes:
    """Load EnrichedNotes from checkpoints/url_NNN_enriched.json."""
    path = Path(output_dir) / CHECKPOINT_DIR_NAME / f"url_{order:03d}_enriched.json"
    if not path.exists():
        raise PipelineError(
            f"Cannot load enriched checkpoint: file not found at {path}"
        )
    enriched = EnrichedNotes.model_validate_json(path.read_text())
    logger.info("Checkpoint loaded: %s (%d refs)", path, len(enriched.references_found))
    return enriched


def load_validation_checkpoint(output_dir: str, order: int) -> ValidationReport:
    """Load ValidationReport from checkpoints/url_NNN_validation.json."""
    path = Path(output_dir) / CHECKPOINT_DIR_NAME / f"url_{order:03d}_validation.json"
    if not path.exists():
        raise PipelineError(
            f"Cannot load validation checkpoint: file not found at {path}"
        )
    report = ValidationReport.model_validate_json(path.read_text())
    logger.info(
        "Checkpoint loaded: %s (%d critical, %d warnings)",
        path, report.critical_failures, report.warnings,
    )
    return report


def load_book_checkpoint(output_dir: str) -> BookOutput:
    """Load BookOutput from checkpoints/book_output.json."""
    path = Path(output_dir) / CHECKPOINT_DIR_NAME / "book_output.json"
    if not path.exists():
        raise PipelineError(
            f"Cannot load book checkpoint: file not found at {path}"
        )
    book = BookOutput.model_validate_json(path.read_text())
    logger.info("Checkpoint loaded: %s (%d chapters)", path, len(book.chapters))
    return book


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_checkpoints_for_from_agent(
    from_agent: int,
    output_dir: str,
    url_count: Optional[int] = None,
) -> None:
    """
    Validate that all required checkpoint files exist for --from-agent N.

    Args:
        from_agent: Agent number to start from (2-5).
        output_dir: Output directory containing checkpoints/.
        url_count: Number of URLs (if known). If None, inferred from manifest.

    Raises:
        PipelineError: If any required checkpoint is missing.
    """
    if from_agent < 2:
        return

    ckpt = Path(output_dir) / CHECKPOINT_DIR_NAME
    missing: list[str] = []

    # Agent 2+ needs manifest
    manifest_path = ckpt / "manifest.json"
    if not manifest_path.exists():
        missing.append(str(manifest_path))
    elif url_count is None:
        manifest = DownloadManifest.model_validate_json(manifest_path.read_text())
        url_count = len([r for r in manifest.results if r.success])

    if url_count is None:
        raise PipelineError(
            f"Cannot start from agent {from_agent}: "
            f"manifest checkpoint missing at {manifest_path}"
        )

    # Agent 3+ needs transcripts
    if from_agent >= 3:
        for i in range(1, url_count + 1):
            t_path = ckpt / f"url_{i:03d}_transcript.json"
            if not t_path.exists():
                missing.append(str(t_path))

    # Agent 4+ needs enriched notes
    if from_agent >= 4:
        for i in range(1, url_count + 1):
            e_path = ckpt / f"url_{i:03d}_enriched.json"
            if not e_path.exists():
                missing.append(str(e_path))

    # Agent 5 needs book output
    if from_agent >= 5:
        b_path = ckpt / "book_output.json"
        if not b_path.exists():
            missing.append(str(b_path))

    if missing:
        files = "\n  ".join(missing)
        raise PipelineError(
            f"Cannot start from agent {from_agent}: "
            f"missing checkpoint file(s):\n  {files}\n"
            f"Run the full pipeline first to generate checkpoints."
        )
