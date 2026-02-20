"""
Transcriber Tool: Local speech-to-text via faster-whisper or whisper.cpp.

Supports two backends:
- "faster-whisper" (default): CTranslate2-based, good GPU support via CUDA
- "whisper.cpp": GGML-based, Apple Silicon Metal/CoreML acceleration

Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
import os
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

WHISPER_BACKEND_DEFAULT = "faster-whisper"


def transcribe_audio(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
    language: str = WHISPER_LANGUAGE,
    beam_size: int = WHISPER_BEAM_SIZE,
    vad_filter: bool = WHISPER_VAD_FILTER,
    compute_type: str = WHISPER_COMPUTE_TYPE,
    initial_prompt: Optional[str] = None,
    backend: str = WHISPER_BACKEND_DEFAULT,
) -> dict:
    """
    Transcribe audio using a local Whisper backend.

    Args:
        audio_path: Path to WAV file (16kHz mono recommended).
        model_size: Whisper model size (tiny/base/small/medium/large-v3).
        language: ISO 639-1 language code.
        beam_size: Beam search width.
        vad_filter: Enable Voice Activity Detection filter.
        compute_type: CTranslate2 compute type (faster-whisper only).
        initial_prompt: Domain-specific prompt to improve recognition.
        backend: "faster-whisper" or "whisper.cpp".

    Returns:
        dict with keys:
            segments: list of dicts with start, end, text, confidence
            language: detected language code
            language_probability: float
            model: model name used
            duration: total audio duration in seconds
    """
    if backend == "whisper.cpp":
        return _transcribe_whisper_cpp(
            audio_path,
            model_size=model_size,
            language=language,
            beam_size=beam_size,
            initial_prompt=initial_prompt,
        )
    return _transcribe_faster_whisper(
        audio_path,
        model_size=model_size,
        language=language,
        beam_size=beam_size,
        vad_filter=vad_filter,
        compute_type=compute_type,
        initial_prompt=initial_prompt,
    )


def _transcribe_faster_whisper(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
    language: str = WHISPER_LANGUAGE,
    beam_size: int = WHISPER_BEAM_SIZE,
    vad_filter: bool = WHISPER_VAD_FILTER,
    compute_type: str = WHISPER_COMPUTE_TYPE,
    initial_prompt: Optional[str] = None,
) -> dict:
    """Transcribe using faster-whisper (CTranslate2 backend)."""
    from faster_whisper import WhisperModel

    logger.info("Loading faster-whisper model: %s (compute: %s)", model_size, compute_type)
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


def _transcribe_whisper_cpp(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
    language: str = WHISPER_LANGUAGE,
    beam_size: int = WHISPER_BEAM_SIZE,
    initial_prompt: Optional[str] = None,
) -> dict:
    """Transcribe using whisper.cpp via pywhispercpp (Metal/CoreML on Apple Silicon)."""
    from pywhispercpp.model import Model

    model_name = model_size

    # Number of threads: use available CPU cores, capped at 8
    n_threads = min(os.cpu_count() or 4, 8)

    logger.info(
        "Loading whisper.cpp model: %s (threads: %d, beam_size: %d)",
        model_name, n_threads, beam_size,
    )
    model = Model(
        model_name,
        n_threads=n_threads,
        # Use beam search for more reliable long-form transcription
        params_sampling_strategy=1,  # BEAM_SEARCH
    )

    logger.info("Transcribing with whisper.cpp: %s", audio_path)
    segments_list = model.transcribe(
        audio_path,
        language=language,
        initial_prompt=initial_prompt or "",
        beam_search={"beam_size": beam_size, "patience": -1.0},
        single_segment=False,
    )

    # pywhispercpp t0/t1 are in centiseconds (10ms units), divide by 100 for seconds
    segments = []
    for seg in segments_list:
        start = seg.t0 / 100.0
        end = seg.t1 / 100.0
        text = seg.text.strip()
        # Skip zero-duration or empty segments (whisper.cpp occasionally produces these)
        if end <= start or not text:
            continue
        segments.append({
            "start": start,
            "end": end,
            "text": text,
            "confidence": None,
        })

    duration = segments[-1]["end"] if segments else 0

    logger.info(
        "whisper.cpp transcription complete: %d segments, %.1fs, language=%s",
        len(segments), duration, language,
    )

    return {
        "segments": segments,
        "language": language,
        "language_probability": 1.0,
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
        "Transcribe audio to text using local Whisper. "
        "Returns timestamped segments with confidence scores."
    )
    args_schema: type[BaseModel] = WhisperTranscribeInput

    def _run(self, audio_path: str, model_size: str = WHISPER_MODEL_SIZE,
             language: str = WHISPER_LANGUAGE) -> str:
        import json
        result = transcribe_audio(audio_path, model_size=model_size, language=language)
        return json.dumps(result, default=str)
