"""
Downloader Tool: Audio metadata extraction via ffprobe and mutagen.

Extracts metadata from audio files and merges with URL-provided hints.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


def compute_sha256(file_path: str) -> str:
    """Compute SHA-256 hash of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def extract_id3_metadata(file_path: str) -> dict:
    """Extract metadata from audio file using mutagen (ID3, Vorbis, etc.)."""
    try:
        from mutagen import File as MutagenFile

        audio = MutagenFile(file_path)
        if audio is None:
            return {}

        meta = {}
        # Try common tag formats
        if hasattr(audio, "tags") and audio.tags:
            tags = audio.tags
            # ID3 tags (MP3)
            for key, field in [("TIT2", "title"), ("TPE1", "artist"),
                               ("TALB", "album"), ("TDRC", "date")]:
                if key in tags:
                    meta[field] = str(tags[key])
            # Vorbis/FLAC tags
            for key, field in [("title", "title"), ("artist", "artist"),
                               ("album", "album"), ("date", "date")]:
                if key in tags:
                    val = tags[key]
                    meta[field] = val[0] if isinstance(val, list) else str(val)

        # Duration from mutagen
        if hasattr(audio, "info") and hasattr(audio.info, "length"):
            meta["duration_seconds"] = audio.info.length

        return meta
    except Exception as e:
        logger.debug("mutagen extraction failed for %s: %s", file_path, e)
        return {}


def extract_metadata(
    file_path: str,
    url: Optional[str] = None,
    metadata_hints: Optional[dict] = None,
    ytdlp_metadata: Optional[dict] = None,
) -> dict:
    """
    Extract and merge metadata from multiple sources.

    Priority (highest to lowest):
    1. metadata_hints (user-provided per-URL hints)
    2. ytdlp_metadata (from yt-dlp download info)
    3. id3_metadata (from audio file tags)
    4. Derived values (file size, hash, format from extension)

    Args:
        file_path: Path to the audio file.
        url: Original source URL.
        metadata_hints: User-provided metadata hints.
        ytdlp_metadata: Metadata from yt-dlp extraction.

    Returns:
        dict with normalized metadata fields.
    """
    path = Path(file_path)
    result: dict = {
        "url": url or "",
        "title": "Unknown",
        "duration_seconds": 0.0,
        "source_type": "local_file",
        "original_format": path.suffix.lstrip(".") if path.exists() else None,
        "file_size_bytes": path.stat().st_size if path.exists() else None,
    }

    # Layer 1: ID3/file metadata
    if path.exists():
        id3 = extract_id3_metadata(file_path)
        if id3.get("title"):
            result["title"] = id3["title"]
        if id3.get("artist"):
            result["speaker"] = id3["artist"]
        if id3.get("duration_seconds"):
            result["duration_seconds"] = id3["duration_seconds"]

    # Layer 2: yt-dlp metadata
    if ytdlp_metadata:
        result["source_type"] = "youtube"
        if ytdlp_metadata.get("title"):
            result["title"] = ytdlp_metadata["title"]
        if ytdlp_metadata.get("duration_seconds"):
            result["duration_seconds"] = ytdlp_metadata["duration_seconds"]
        if ytdlp_metadata.get("uploader"):
            result["channel"] = ytdlp_metadata["uploader"]
        if ytdlp_metadata.get("upload_date"):
            date = ytdlp_metadata["upload_date"]
            # yt-dlp returns YYYYMMDD; normalize to YYYY-MM-DD
            if len(date) == 8 and date.isdigit():
                result["upload_date"] = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
            else:
                result["upload_date"] = date
        if ytdlp_metadata.get("description"):
            result["description"] = ytdlp_metadata["description"][:500]

    # Layer 3: User-provided hints (highest priority)
    if metadata_hints:
        for key in ["title", "speaker", "date", "venue", "series_title",
                     "series_position", "description"]:
            if metadata_hints.get(key):
                if key == "series_title":
                    result["series"] = metadata_hints[key]
                elif key == "date":
                    result["upload_date"] = metadata_hints[key]
                else:
                    result[key] = metadata_hints[key]

    # Compute hash
    if path.exists():
        result["sha256"] = compute_sha256(file_path)

    return result


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class MetadataExtractInput(BaseModel):
    file_path: str = Field(..., description="Path to audio file")
    url: str = Field(default="", description="Original source URL")


class MetadataExtractTool(BaseTool):
    name: str = "extract_metadata"
    description: str = (
        "Extract metadata from audio files. Combines file tags, "
        "download metadata, and user-provided hints."
    )
    args_schema: type[BaseModel] = MetadataExtractInput

    def _run(self, file_path: str, url: str = "") -> str:
        result = extract_metadata(file_path, url=url or None)
        return json.dumps(result)
