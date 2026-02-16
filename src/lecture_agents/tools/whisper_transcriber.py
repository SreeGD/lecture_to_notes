"""
Transcriber Tool: Local speech-to-text via faster-whisper.

Uses CTranslate2-based Whisper for fast CPU/GPU inference.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.constants import (
    WHISPER_BEAM_SIZE,
    WHISPER_COMPUTE_TYPE,
    WHISPER_LANGUAGE,
    WHISPER_MODEL_SIZE,
    WHISPER_VAD_FILTER,
)

logger = logging.getLogger(__name__)


def transcribe_audio(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
    language: str = WHISPER_LANGUAGE,
    beam_size: int = WHISPER_BEAM_SIZE,
    vad_filter: bool = WHISPER_VAD_FILTER,
    compute_type: str = WHISPER_COMPUTE_TYPE,
    initial_prompt: Optional[str] = None,
) -> dict:
    """
    Transcribe audio using local faster-whisper.

    The initial_prompt parameter biases Whisper toward domain vocabulary
    (Sanskrit terms, speaker names, scripture references).

    Args:
        audio_path: Path to WAV file (16kHz mono recommended).
        model_size: Whisper model size (tiny/base/small/medium/large-v3).
        language: ISO 639-1 language code.
        beam_size: Beam search width.
        vad_filter: Enable Voice Activity Detection filter.
        compute_type: CTranslate2 compute type (int8/float16/float32).
        initial_prompt: Domain-specific prompt to improve recognition.

    Returns:
        dict with keys:
            segments: list of dicts with start, end, text, confidence
            language: detected language code
            language_probability: float
            model: model name used
            duration: total audio duration in seconds
    """
    from faster_whisper import WhisperModel

    logger.info("Loading Whisper model: %s (compute: %s)", model_size, compute_type)
    model = WhisperModel(model_size, compute_type=compute_type)

    logger.info("Transcribing: %s", audio_path)
    segments_gen, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        initial_prompt=initial_prompt,
    )

    segments = []
    for seg in segments_gen:
        segments.append({
            "start": seg.start,
            "end": seg.end,
            "text": seg.text.strip(),
            "confidence": seg.avg_logprob,
            # Convert log probability to a 0-1 confidence score
            # avg_log_prob is negative; closer to 0 = more confident
        })

    duration = info.duration if hasattr(info, "duration") else (
        segments[-1]["end"] if segments else 0
    )

    logger.info(
        "Transcription complete: %d segments, %.1fs, language=%s (%.2f)",
        len(segments), duration, info.language, info.language_probability,
    )

    return {
        "segments": segments,
        "language": info.language,
        "language_probability": info.language_probability,
        "model": model_size,
        "duration": duration,
    }


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class WhisperTranscribeInput(BaseModel):
    audio_path: str = Field(..., description="Path to audio file (WAV recommended)")
    model_size: str = Field(default=WHISPER_MODEL_SIZE, description="Whisper model size")
    language: str = Field(default=WHISPER_LANGUAGE, description="Language code")


class WhisperTranscribeTool(BaseTool):
    name: str = "transcribe_audio"
    description: str = (
        "Transcribe audio to text using local faster-whisper. "
        "Returns timestamped segments with confidence scores."
    )
    args_schema: type[BaseModel] = WhisperTranscribeInput

    def _run(self, audio_path: str, model_size: str = WHISPER_MODEL_SIZE,
             language: str = WHISPER_LANGUAGE) -> str:
        import json
        result = transcribe_audio(audio_path, model_size=model_size, language=language)
        return json.dumps(result, default=str)
