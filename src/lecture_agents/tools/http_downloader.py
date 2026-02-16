"""
Downloader Tool: Direct HTTP/HTTPS file downloads via httpx.

For direct audio file URLs (MP3, WAV, M4A, etc.) that don't need yt-dlp.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional
from urllib.parse import unquote, urlparse

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".flac", ".webm", ".aac"}


def is_direct_audio_url(url: str) -> bool:
    """Check if URL points directly to an audio file based on extension."""
    parsed = urlparse(url)
    path = unquote(parsed.path).lower()
    return any(path.endswith(ext) for ext in AUDIO_EXTENSIONS)


def download_with_httpx(
    url: str,
    output_dir: str,
    timeout: int = 120,
    max_size_mb: int = 2048,
) -> dict:
    """
    Download an audio file directly via HTTP/HTTPS using httpx.

    Args:
        url: Direct URL to an audio file.
        output_dir: Directory to save the downloaded file.
        timeout: HTTP timeout in seconds.
        max_size_mb: Maximum file size in MB (abort if exceeded).

    Returns:
        dict with keys:
            success: bool
            file_path: str or None
            file_size_bytes: int or None
            sha256: str or None
            error: str or None
    """
    import httpx

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Derive filename from URL
    parsed = urlparse(url)
    filename = Path(unquote(parsed.path)).name or "download.mp3"
    file_path = output_path / filename

    try:
        with httpx.stream("GET", url, timeout=timeout, follow_redirects=True) as response:
            response.raise_for_status()

            # Check content-length if available
            content_length = response.headers.get("content-length")
            if content_length and int(content_length) > max_size_mb * 1024 * 1024:
                return {
                    "success": False,
                    "file_path": None,
                    "file_size_bytes": None,
                    "sha256": None,
                    "error": f"File too large: {int(content_length)} bytes (max {max_size_mb}MB)",
                }

            sha256 = hashlib.sha256()
            total_bytes = 0

            with open(file_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    total_bytes += len(chunk)
                    if total_bytes > max_size_mb * 1024 * 1024:
                        f.close()
                        file_path.unlink(missing_ok=True)
                        return {
                            "success": False,
                            "file_path": None,
                            "file_size_bytes": None,
                            "sha256": None,
                            "error": f"Download exceeded {max_size_mb}MB limit",
                        }
                    sha256.update(chunk)
                    f.write(chunk)

            logger.info("Downloaded: %s -> %s (%d bytes)", url, file_path, total_bytes)
            return {
                "success": True,
                "file_path": str(file_path),
                "file_size_bytes": total_bytes,
                "sha256": sha256.hexdigest(),
                "error": None,
            }

    except Exception as e:
        logger.error("HTTP download failed for %s: %s", url, e)
        file_path.unlink(missing_ok=True)
        return {
            "success": False,
            "file_path": None,
            "file_size_bytes": None,
            "sha256": None,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class HttpDownloadInput(BaseModel):
    url: str = Field(..., description="Direct URL to audio file")
    output_dir: str = Field(..., description="Directory to save the downloaded file")


class HttpDownloadTool(BaseTool):
    name: str = "download_with_httpx"
    description: str = (
        "Download audio files directly via HTTP/HTTPS. "
        "Use for direct file URLs (MP3, WAV, M4A, etc.)."
    )
    args_schema: type[BaseModel] = HttpDownloadInput

    def _run(self, url: str, output_dir: str) -> str:
        import json
        result = download_with_httpx(url, output_dir)
        return json.dumps(result)
