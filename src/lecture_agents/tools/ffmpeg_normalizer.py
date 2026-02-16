"""
Downloader Tool: Audio normalization via ffmpeg subprocess.

Converts any audio format to 16kHz mono WAV for optimal Whisper performance.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import json
import logging
import subprocess
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.constants import AUDIO_CHANNELS, AUDIO_SAMPLE_RATE

logger = logging.getLogger(__name__)


def get_audio_duration(file_path: str) -> Optional[float]:
    """Get audio duration in seconds using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "json",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
    except Exception as e:
        logger.warning("ffprobe failed for %s: %s", file_path, e)
    return None


def get_audio_info(file_path: str) -> dict:
    """Get audio format info using ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration,size,bit_rate:stream=codec_name,sample_rate,channels",
                "-of", "json",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            return json.loads(result.stdout)
    except Exception as e:
        logger.warning("ffprobe info failed for %s: %s", file_path, e)
    return {}


def normalize_to_wav(
    input_path: str,
    output_path: Optional[str] = None,
    sample_rate: int = AUDIO_SAMPLE_RATE,
    channels: int = AUDIO_CHANNELS,
) -> dict:
    """
    Normalize audio to WAV format suitable for Whisper.

    Runs: ffmpeg -i input -ar 16000 -ac 1 -f wav output

    Args:
        input_path: Path to input audio file (any format ffmpeg supports).
        output_path: Path to output WAV file. If None, derives from input.
        sample_rate: Target sample rate (default 16000 for Whisper).
        channels: Target number of channels (default 1 = mono).

    Returns:
        dict with keys:
            success: bool
            output_path: str or None
            duration_seconds: float or None
            error: str or None
    """
    input_file = Path(input_path)
    if not input_file.exists():
        return {
            "success": False,
            "output_path": None,
            "duration_seconds": None,
            "error": f"Input file not found: {input_path}",
        }

    if output_path is None:
        output_path = str(input_file.with_suffix(".wav"))

    # Skip if already a normalized WAV
    if input_path == output_path and input_file.suffix == ".wav":
        info = get_audio_info(input_path)
        streams = info.get("streams", [{}])
        fmt = info.get("format", {})
        if streams and str(streams[0].get("sample_rate")) == str(sample_rate):
            duration = float(fmt.get("duration", 0))
            return {
                "success": True,
                "output_path": output_path,
                "duration_seconds": duration,
                "error": None,
            }

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",       # overwrite output
                "-i", input_path,
                "-ar", str(sample_rate),
                "-ac", str(channels),
                "-f", "wav",
                output_path,
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minutes max for large files
        )

        if result.returncode != 0:
            return {
                "success": False,
                "output_path": None,
                "duration_seconds": None,
                "error": f"ffmpeg failed: {result.stderr[:500]}",
            }

        duration = get_audio_duration(output_path)

        logger.info("Normalized: %s -> %s (%.1fs)", input_path, output_path,
                     duration or 0)
        return {
            "success": True,
            "output_path": output_path,
            "duration_seconds": duration,
            "error": None,
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output_path": None,
            "duration_seconds": None,
            "error": "ffmpeg timed out after 600 seconds",
        }
    except FileNotFoundError:
        return {
            "success": False,
            "output_path": None,
            "duration_seconds": None,
            "error": "ffmpeg not found. Install with: brew install ffmpeg",
        }
    except Exception as e:
        logger.error("Normalization failed for %s: %s", input_path, e)
        return {
            "success": False,
            "output_path": None,
            "duration_seconds": None,
            "error": str(e),
        }


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class FfmpegNormalizeInput(BaseModel):
    input_path: str = Field(..., description="Path to input audio file")
    output_path: str = Field(default="", description="Path to output WAV file (optional)")


class FfmpegNormalizeTool(BaseTool):
    name: str = "normalize_to_wav"
    description: str = (
        "Normalize audio to 16kHz mono WAV format for Whisper transcription. "
        "Uses ffmpeg for conversion."
    )
    args_schema: type[BaseModel] = FfmpegNormalizeInput

    def _run(self, input_path: str, output_path: str = "") -> str:
        result = normalize_to_wav(input_path, output_path or None)
        return json.dumps(result)
