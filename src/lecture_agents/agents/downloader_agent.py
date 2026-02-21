"""
Agent 01: Downloader Agent
Lecture-to-Notes Pipeline v1.0

Downloads audio from URLs (YouTube, direct HTTP, local files),
normalizes to 16kHz mono WAV, extracts metadata, and validates integrity.
"""

from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

try:
    from crewai import Agent, Task
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    Agent = None  # type: ignore[assignment,misc]
    Task = None   # type: ignore[assignment,misc]

from lecture_agents.config.constants import (
    MAX_AUDIO_DURATION_HOURS,
    MAX_AUDIO_SIZE_MB,
    MIN_AUDIO_DURATION_SECONDS,
    PIPELINE_OUTPUT_DIR,
    RATE_LIMIT_DELAY,
    WARN_AUDIO_SIZE_MB,
)
from lecture_agents.exceptions import AudioNormalizationError, DownloadError
from lecture_agents.schemas.download_output import (
    BatchSummary,
    DownloadManifest,
    DownloadResult,
    MediaMetadata,
)
from lecture_agents.tools.ffmpeg_normalizer import get_audio_duration, normalize_to_wav
from lecture_agents.tools.http_downloader import (
    HttpDownloadTool,
    download_with_httpx,
    is_direct_audio_url,
)
from lecture_agents.tools.metadata_extractor import (
    MetadataExtractTool,
    compute_sha256,
    extract_metadata,
)
from lecture_agents.tools.yt_dlp_downloader import (
    YtDlpDownloadTool,
    download_with_ytdlp,
    is_ytdlp_url,
)

logger = logging.getLogger(__name__)


def _detect_source_type(url: str) -> str:
    """Determine the best download strategy for a URL."""
    if url.startswith("/") or url.startswith("file://"):
        return "local_file"
    if is_ytdlp_url(url):
        return "youtube"
    if is_direct_audio_url(url):
        return "direct_http"
    # Default: try yt-dlp first (it supports many sites)
    return "youtube"


def _download_single(
    url: str,
    order: int,
    output_dir: str,
    metadata_hints: Optional[dict] = None,
) -> DownloadResult:
    """Download and normalize a single URL. Returns a validated DownloadResult."""
    source_type = _detect_source_type(url)
    download_dir = str(Path(output_dir) / "downloads")

    start_time = time.time()

    # Step 1: Download
    if source_type == "local_file":
        local_path = url.replace("file://", "")
        if not Path(local_path).exists():
            return DownloadResult(
                url=url, order=order, success=False,
                error=f"Local file not found: {local_path}",
            )
        dl_result = {"success": True, "file_path": local_path, "metadata": None}
    elif source_type == "direct_http":
        dl_result = download_with_httpx(url, download_dir)
    else:
        dl_result = download_with_ytdlp(url, download_dir)

    if not dl_result["success"]:
        return DownloadResult(
            url=url, order=order, success=False,
            error=dl_result.get("error", "Download failed"),
        )

    downloaded_path = dl_result["file_path"]

    # Step 2: Normalize to WAV
    wav_dir = str(Path(output_dir) / "audio")
    Path(wav_dir).mkdir(parents=True, exist_ok=True)
    wav_filename = f"lecture_{order:03d}.wav"
    wav_path = str(Path(wav_dir) / wav_filename)

    norm_result = normalize_to_wav(downloaded_path, wav_path)
    if not norm_result["success"]:
        return DownloadResult(
            url=url, order=order, success=False,
            error=f"Normalization failed: {norm_result.get('error')}",
        )

    # Step 3: Validate
    duration = norm_result.get("duration_seconds") or get_audio_duration(wav_path) or 0
    if duration < MIN_AUDIO_DURATION_SECONDS:
        return DownloadResult(
            url=url, order=order, success=False,
            error=f"Audio too short: {duration:.1f}s (minimum {MIN_AUDIO_DURATION_SECONDS}s)",
        )
    if duration > MAX_AUDIO_DURATION_HOURS * 3600:
        return DownloadResult(
            url=url, order=order, success=False,
            error=f"Audio too long: {duration/3600:.1f}h (maximum {MAX_AUDIO_DURATION_HOURS}h)",
        )

    file_size = Path(wav_path).stat().st_size
    if file_size == 0:
        return DownloadResult(
            url=url, order=order, success=False,
            error="Normalized audio file is empty (0 bytes) — possible corruption",
        )
    if file_size > MAX_AUDIO_SIZE_MB * 1024 * 1024:
        return DownloadResult(
            url=url, order=order, success=False,
            error=f"Audio file exceeds hard limit: {file_size / (1024 * 1024):.0f} MB > {MAX_AUDIO_SIZE_MB} MB",
        )
    if file_size > WARN_AUDIO_SIZE_MB * 1024 * 1024:
        logger.warning("Large audio file: %s (%.0f MB)", wav_path,
                       file_size / (1024 * 1024))

    # Step 4: Extract metadata
    meta_dict = extract_metadata(
        wav_path,
        url=url,
        metadata_hints=metadata_hints,
        ytdlp_metadata=dl_result.get("metadata"),
    )
    meta_dict["source_type"] = source_type
    meta_dict["duration_seconds"] = duration
    meta_dict["file_size_bytes"] = file_size

    sha256 = compute_sha256(wav_path)

    download_duration = time.time() - start_time

    metadata = MediaMetadata(
        url=url,
        title=meta_dict.get("title", "Unknown"),
        duration_seconds=duration,
        source_type=source_type,
        original_format=meta_dict.get("original_format"),
        file_size_bytes=file_size,
        upload_date=meta_dict.get("upload_date"),
        channel=meta_dict.get("channel"),
        description=meta_dict.get("description"),
        speaker=meta_dict.get("speaker"),
        series=meta_dict.get("series"),
    )

    return DownloadResult(
        url=url,
        order=order,
        success=True,
        audio_path=wav_path,
        original_path=downloaded_path,
        sha256=sha256,
        metadata=metadata,
        download_duration_seconds=round(download_duration, 2),
    )


def run_download_pipeline(
    urls: list[str],
    output_dir: str = PIPELINE_OUTPUT_DIR,
    metadata_hints_list: Optional[list[dict]] = None,
) -> DownloadManifest:
    """
    Run the deterministic download pipeline without LLM.

    For each URL:
    1. Detect source type (youtube/http/local)
    2. Download via appropriate tool
    3. Normalize to WAV (16kHz mono)
    4. Validate duration and size
    5. Extract and merge metadata

    Args:
        urls: List of URLs to download.
        output_dir: Base output directory.
        metadata_hints_list: Optional per-URL metadata hints (parallel to urls).

    Returns:
        Validated DownloadManifest.
    """
    if not urls:
        raise DownloadError("No URLs provided")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    hints_list = metadata_hints_list or [None] * len(urls)  # type: ignore[list-item]
    if len(hints_list) < len(urls):
        hints_list.extend([None] * (len(urls) - len(hints_list)))  # type: ignore[arg-type]

    results: list[DownloadResult] = []
    seen_urls: dict[str, int] = {}

    for i, url in enumerate(urls):
        order = i + 1

        # Deduplication
        if url in seen_urls:
            logger.info("Skipping duplicate URL: %s (same as #%d)", url, seen_urls[url])
            # Reference the earlier result
            earlier = results[seen_urls[url] - 1]
            results.append(DownloadResult(
                url=url, order=order, success=earlier.success,
                audio_path=earlier.audio_path, sha256=earlier.sha256,
                metadata=earlier.metadata,
                error="Duplicate of URL #%d" % seen_urls[url] if not earlier.success else None,
            ))
            continue

        seen_urls[url] = order
        logger.info("Downloading [%d/%d]: %s", order, len(urls), url)

        result = _download_single(url, order, output_dir, hints_list[i])
        results.append(result)

        # Rate limiting between downloads
        if i < len(urls) - 1:
            time.sleep(RATE_LIMIT_DELAY)

    # Build summary
    successful = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    total_duration = sum(
        r.metadata.duration_seconds for r in results
        if r.success and r.metadata
    )
    total_size = sum(
        r.metadata.file_size_bytes for r in results
        if r.success and r.metadata and r.metadata.file_size_bytes
    )

    batch_summary = BatchSummary(
        total_urls=len(results),
        successful=successful,
        failed=failed,
        total_duration_seconds=round(total_duration, 2),
        total_size_bytes=total_size,
    )

    summary_text = (
        f"Downloaded {successful}/{len(urls)} URLs. "
        f"Total audio: {total_duration/60:.1f} minutes. "
        f"Total size: {total_size/(1024*1024):.1f} MB."
    )
    if failed > 0:
        failed_urls = [r.url for r in results if not r.success]
        summary_text += f" Failed: {', '.join(failed_urls[:3])}"

    return DownloadManifest(
        results=results,
        batch_summary=batch_summary,
        output_dir=output_dir,
        summary=summary_text,
    )


# ---------------------------------------------------------------------------
# CrewAI Agentic Mode
# ---------------------------------------------------------------------------


def build_downloader_agent() -> Agent:
    """Create the Downloader Agent with all tools. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode. pip install crewai[tools]")
    return Agent(
        role="Audio Acquisition Specialist",
        goal=(
            "Download audio files from provided URLs, normalize them to "
            "16kHz mono WAV format, extract metadata, and validate integrity. "
            "Handle YouTube, direct HTTP links, and local files."
        ),
        backstory=(
            "You are an expert at acquiring audio content from diverse "
            "online sources. You handle YouTube, SoundCloud, podcast feeds, "
            "and direct file downloads with equal ease. You always normalize "
            "audio to the format required by the transcription engine and "
            "validate file integrity before passing downstream."
        ),
        tools=[
            YtDlpDownloadTool(),
            HttpDownloadTool(),
            MetadataExtractTool(),
        ],
        verbose=True,
    )


def build_download_task(
    agent: Agent,
    urls: list[str],
    output_dir: str = PIPELINE_OUTPUT_DIR,
) -> Task:
    """Create the Download task. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode.")
    return Task(
        description=(
            f"Download audio from these URLs and normalize to 16kHz mono WAV:\n"
            + "\n".join(f"  {i+1}. {url}" for i, url in enumerate(urls))
            + f"\n\nSave to: {output_dir}"
        ),
        expected_output=(
            "A DownloadManifest JSON with results for each URL, "
            "batch summary, and file paths to normalized WAV files."
        ),
        agent=agent,
    )
