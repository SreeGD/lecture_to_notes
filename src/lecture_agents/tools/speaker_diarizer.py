"""
Transcriber Tool: Speaker diarization via pyannote.audio.

Identifies and labels different speakers in the audio.
Optional dependency — gracefully degrades if pyannote.audio is not installed.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.constants import (
    MAX_SPEAKERS,
    MIN_SPEAKERS,
    SPEAKER_LABEL_PRIMARY,
    SPEAKER_LABEL_QUESTIONER,
)

logger = logging.getLogger(__name__)

# Check if pyannote.audio is available
try:
    from pyannote.audio import Pipeline as PyannotePipeline
    HAS_PYANNOTE = True
except ImportError:
    HAS_PYANNOTE = False


def diarize_audio(
    audio_path: str,
    num_speakers: Optional[int] = None,
    min_speakers: int = MIN_SPEAKERS,
    max_speakers: int = MAX_SPEAKERS,
    hf_token: Optional[str] = None,
) -> dict:
    """
    Perform speaker diarization using pyannote.audio.

    Args:
        audio_path: Path to WAV file.
        num_speakers: Expected number of speakers (None for auto-detect).
        min_speakers: Minimum number of speakers for auto-detect.
        max_speakers: Maximum number of speakers for auto-detect.
        hf_token: Hugging Face token for pyannote model access.

    Returns:
        dict with keys:
            success: bool
            segments: list of dicts with start, end, speaker
            num_speakers: int — number of unique speakers detected
            error: str or None
    """
    if not HAS_PYANNOTE:
        return {
            "success": False,
            "segments": [],
            "num_speakers": 0,
            "error": (
                "pyannote.audio not installed. "
                "Install with: pip install -e '.[diarize]'"
            ),
        }

    try:
        import os
        token = hf_token or os.environ.get("HF_TOKEN")
        if not token:
            return {
                "success": False,
                "segments": [],
                "num_speakers": 0,
                "error": "HF_TOKEN not set. Required for pyannote.audio model access.",
            }

        pipeline = PyannotePipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )

        kwargs = {}
        if num_speakers is not None:
            kwargs["num_speakers"] = num_speakers
        else:
            kwargs["min_speakers"] = min_speakers
            kwargs["max_speakers"] = max_speakers

        diarization = pipeline(audio_path, **kwargs)

        segments = []
        speakers = set()
        for turn, _, speaker in diarization.itertracks(yield_label=True):
            segments.append({
                "start": turn.start,
                "end": turn.end,
                "speaker": speaker,
            })
            speakers.add(speaker)

        logger.info(
            "Diarization complete: %d segments, %d speakers",
            len(segments), len(speakers),
        )
        return {
            "success": True,
            "segments": segments,
            "num_speakers": len(speakers),
            "error": None,
        }

    except Exception as e:
        logger.error("Diarization failed: %s", e)
        return {
            "success": False,
            "segments": [],
            "num_speakers": 0,
            "error": str(e),
        }


def merge_transcript_with_diarization(
    transcript_segments: list[dict],
    diarization_segments: list[dict],
    primary_speaker_label: str = SPEAKER_LABEL_PRIMARY,
    questioner_label: str = SPEAKER_LABEL_QUESTIONER,
) -> list[dict]:
    """
    Assign speaker labels to transcript segments based on diarization overlap.

    For each transcript segment, finds the diarization segment with the most
    temporal overlap and assigns that speaker label. The most frequent speaker
    is labeled as the primary speaker; others get questioner labels.

    Args:
        transcript_segments: Segments from Whisper with start, end, text.
        diarization_segments: Segments from pyannote with start, end, speaker.
        primary_speaker_label: Label for the main speaker.
        questioner_label: Base label for other speakers.

    Returns:
        Updated transcript_segments with speaker labels assigned.
    """
    if not diarization_segments:
        return transcript_segments

    # Find the most common speaker (primary/lecturer)
    speaker_durations: dict[str, float] = {}
    for seg in diarization_segments:
        speaker = seg["speaker"]
        duration = seg["end"] - seg["start"]
        speaker_durations[speaker] = speaker_durations.get(speaker, 0) + duration

    primary_raw = max(speaker_durations, key=speaker_durations.get)  # type: ignore[arg-type]

    # Build speaker label mapping
    other_speakers = sorted(
        [s for s in speaker_durations if s != primary_raw],
        key=lambda s: speaker_durations[s],
        reverse=True,
    )
    label_map = {primary_raw: primary_speaker_label}
    for i, speaker in enumerate(other_speakers, 1):
        label_map[speaker] = f"{questioner_label} {i}"

    # Assign labels to transcript segments based on overlap
    for t_seg in transcript_segments:
        best_overlap = 0.0
        best_speaker = primary_raw

        for d_seg in diarization_segments:
            overlap_start = max(t_seg["start"], d_seg["start"])
            overlap_end = min(t_seg["end"], d_seg["end"])
            overlap = max(0, overlap_end - overlap_start)

            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = d_seg["speaker"]

        t_seg["speaker"] = label_map.get(best_speaker, primary_speaker_label)

    return transcript_segments


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class SpeakerDiarizeInput(BaseModel):
    audio_path: str = Field(..., description="Path to audio file")
    num_speakers: Optional[int] = Field(None, description="Expected number of speakers")


class SpeakerDiarizeTool(BaseTool):
    name: str = "diarize_audio"
    description: str = (
        "Identify and label different speakers in an audio file "
        "using pyannote.audio speaker diarization."
    )
    args_schema: type[BaseModel] = SpeakerDiarizeInput

    def _run(self, audio_path: str, num_speakers: Optional[int] = None) -> str:
        import json
        result = diarize_audio(audio_path, num_speakers=num_speakers)
        return json.dumps(result)
