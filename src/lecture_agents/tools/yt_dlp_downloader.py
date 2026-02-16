"""
Downloader Tool: YouTube and media platform downloads via yt-dlp.

Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# URL patterns that indicate a yt-dlp-compatible source
YTDLP_PATTERNS = [
    r"(youtube\.com|youtu\.be)/",
    r"soundcloud\.com/",
    r"vimeo\.com/",
    r"dailymotion\.com/",
    r"archive\.org/",
    r"podcasts?\.(apple|google)\.com/",
]


def is_ytdlp_url(url: str) -> bool:
    """Check if URL is best handled by yt-dlp (YouTube, SoundCloud, etc.)."""
    return any(re.search(pattern, url) for pattern in YTDLP_PATTERNS)


def download_with_ytdlp(
    url: str,
    output_dir: str,
    audio_only: bool = True,
    preferred_format: str = "wav",
) -> dict:
    """
    Download audio from a URL using yt-dlp.

    Args:
        url: YouTube or yt-dlp-supported URL.
        output_dir: Directory to save the downloaded file.
        audio_only: Extract audio only (default True).
        preferred_format: Target audio format for post-processing.

    Returns:
        dict with keys:
            success: bool
            file_path: str or None — path to downloaded file
            metadata: dict or None — title, duration, uploader, upload_date, etc.
            error: str or None
    """
    import yt_dlp

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    outtmpl = str(output_path / "%(title)s.%(ext)s")

    ydl_opts: dict = {
        "outtmpl": outtmpl,
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
    }

    if audio_only:
        ydl_opts["format"] = "bestaudio/best"
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": preferred_format,
                "preferredquality": "0",  # best quality
            }
        ]

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            if info is None:
                return {"success": False, "file_path": None, "metadata": None,
                        "error": "yt-dlp returned no info"}

            # Determine actual output file path
            if audio_only and preferred_format:
                # yt-dlp may change extension after post-processing
                base = Path(ydl.prepare_filename(info))
                file_path = base.with_suffix(f".{preferred_format}")
                if not file_path.exists():
                    # Try finding the file with any audio extension
                    candidates = list(output_path.glob(f"{base.stem}.*"))
                    audio_exts = {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".webm"}
                    file_path = next(
                        (c for c in candidates if c.suffix in audio_exts),
                        base,
                    )
            else:
                file_path = Path(ydl.prepare_filename(info))

            metadata = {
                "title": info.get("title", "Unknown"),
                "duration_seconds": info.get("duration", 0) or 0,
                "uploader": info.get("uploader"),
                "upload_date": info.get("upload_date"),
                "description": info.get("description"),
                "original_format": info.get("ext"),
                "url": url,
            }

            logger.info("Downloaded: %s -> %s", url, file_path)
            return {
                "success": True,
                "file_path": str(file_path),
                "metadata": metadata,
                "error": None,
            }

    except Exception as e:
        logger.error("yt-dlp download failed for %s: %s", url, e)
        return {
            "success": False,
            "file_path": None,
            "metadata": None,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class YtDlpDownloadInput(BaseModel):
    url: str = Field(..., description="URL to download audio from")
    output_dir: str = Field(..., description="Directory to save the downloaded file")


class YtDlpDownloadTool(BaseTool):
    name: str = "download_with_ytdlp"
    description: str = (
        "Download audio from YouTube, SoundCloud, or other yt-dlp-supported "
        "platforms. Returns file path and metadata."
    )
    args_schema: type[BaseModel] = YtDlpDownloadInput

    def _run(self, url: str, output_dir: str) -> str:
        import json
        result = download_with_ytdlp(url, output_dir)
        return json.dumps(result)
