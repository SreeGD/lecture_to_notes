"""
Agent 02: Transcriber Agent
Lecture-to-Notes Pipeline v1.0

Produces high-accuracy transcriptions with speaker diarization, timestamps,
and Sanskrit/Bengali term preservation using local faster-whisper.
"""

from __future__ import annotations

import logging
from collections import Counter
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
    HALLUCINATION_PHRASE_THRESHOLD,
    HALLUCINATION_PHRASES,
    HALLUCINATION_REPETITION_THRESHOLD,
    LLM_POST_PROCESS_MAX_CHARS,
    WHISPER_MODEL_SIZE,
    WHISPER_VAD_FILTER,
)
from lecture_agents.exceptions import DiarizationError, TranscriptionError
from lecture_agents.schemas.transcript_output import (
    DetectedSloka,
    Segment,
    TranscriptOutput,
    VocabularyCorrection,
    VocabularyLog,
)
from lecture_agents.tools.domain_vocabulary import (
    VocabCorrectionTool,
    apply_vocabulary_corrections,
    build_whisper_prompt,
)
from lecture_agents.tools.llm_post_processor import (
    LlmPostProcessTool,
    post_process_transcript_llm,
)
from lecture_agents.tools.speaker_diarizer import (
    SpeakerDiarizeTool,
    diarize_audio,
    merge_transcript_with_diarization,
)
from lecture_agents.tools.whisper_transcriber import (
    WhisperTranscribeTool,
    transcribe_audio,
)

logger = logging.getLogger(__name__)


def _check_hallucination(segments: list[dict]) -> None:
    """Detect Whisper hallucination loops and raise if detected."""
    if len(segments) < 10:
        return

    texts = [s["text"].strip() for s in segments if s.get("text")]
    if not texts:
        return

    # Check 1: Repetition ratio — same text dominates output
    counts = Counter(texts)
    most_common_text, most_common_count = counts.most_common(1)[0]
    repetition_ratio = most_common_count / len(texts)
    if repetition_ratio > HALLUCINATION_REPETITION_THRESHOLD:
        raise TranscriptionError(
            f"Hallucination detected: '{most_common_text[:60]}' repeated in "
            f"{most_common_count}/{len(texts)} segments ({repetition_ratio:.0%}). "
            f"Try a different Whisper backend, smaller model, or add an initial prompt."
        )

    # Check 2: Known hallucination phrases
    hallucination_count = sum(
        1 for t in texts
        if any(phrase in t.lower() for phrase in HALLUCINATION_PHRASES)
    )
    phrase_ratio = hallucination_count / len(texts)
    if phrase_ratio > HALLUCINATION_PHRASE_THRESHOLD:
        raise TranscriptionError(
            f"Hallucination detected: {hallucination_count}/{len(texts)} segments "
            f"({phrase_ratio:.0%}) contain known Whisper hallucination phrases. "
            f"Try a different Whisper backend, smaller model, or add an initial prompt."
        )


def run_transcription_pipeline(
    audio_path: str,
    model_size: str = WHISPER_MODEL_SIZE,
    enable_diarization: bool = True,
    enable_llm_postprocess: bool = True,
    speaker_name: Optional[str] = None,
    vad_filter: bool = WHISPER_VAD_FILTER,
    whisper_backend: str = "faster-whisper",
) -> TranscriptOutput:
    """
    Run the deterministic transcription pipeline.

    Steps:
    1. Build domain vocabulary prompt for Whisper
    2. Transcribe audio with Whisper (using initial_prompt)
    3. Optionally run speaker diarization and merge labels
    4. Apply regex-based domain vocabulary corrections
    5. Optionally run LLM post-processing for deeper cleanup
    6. Build and validate TranscriptOutput

    Args:
        audio_path: Path to normalized WAV file (16kHz mono).
        model_size: Whisper model size.
        enable_diarization: Enable speaker diarization (requires pyannote.audio).
        enable_llm_postprocess: Enable LLM-based post-processing.
        speaker_name: Speaker's name for prompt and labels.
        whisper_backend: "faster-whisper" or "whisper.cpp".

    Returns:
        Validated TranscriptOutput.
    """
    if not Path(audio_path).exists():
        raise TranscriptionError(f"Audio file not found: {audio_path}")

    # Step 0: Verify whisper backend is available
    if whisper_backend == "faster-whisper":
        try:
            import faster_whisper  # noqa: F401
        except ImportError:
            raise TranscriptionError(
                "faster-whisper is not installed. Install with: pip install faster-whisper"
            )
    elif whisper_backend == "whisper.cpp":
        try:
            import pywhispercpp  # noqa: F401
        except ImportError:
            raise TranscriptionError(
                "pywhispercpp is not installed. "
                "Install with: pip install pywhispercpp"
            )

    # Step 1: Build domain vocabulary prompt
    logger.info("Step 1: Building domain vocabulary prompt")
    initial_prompt = build_whisper_prompt(speaker_name=speaker_name)

    # Step 2: Transcribe with Whisper
    logger.info("Step 2: Transcribing with %s (%s)", whisper_backend, model_size)
    whisper_result = transcribe_audio(
        audio_path,
        model_size=model_size,
        initial_prompt=initial_prompt,
        vad_filter=vad_filter,
        backend=whisper_backend,
    )

    raw_segments = whisper_result["segments"]
    if not raw_segments:
        raise TranscriptionError("Whisper produced no segments")

    duration = whisper_result.get("duration", 0)
    detected_language = whisper_result.get("language", "en")

    # Step 3: Speaker diarization (optional)
    speakers_detected = 0
    if enable_diarization:
        logger.info("Step 3: Running speaker diarization")
        diarize_result = diarize_audio(audio_path)
        if diarize_result["success"]:
            raw_segments = merge_transcript_with_diarization(
                raw_segments, diarize_result["segments"],
                primary_speaker_label=speaker_name or "Speaker",
            )
            speakers_detected = diarize_result["num_speakers"]
        else:
            logger.warning("Diarization failed: %s", diarize_result.get("error"))
    else:
        logger.info("Step 3: Skipping diarization (disabled)")

    # Step 4: Domain vocabulary corrections (regex-based)
    logger.info("Step 4: Applying domain vocabulary corrections")
    full_text = " ".join(s["text"] for s in raw_segments if s.get("text"))
    corrected_text, correction_records = apply_vocabulary_corrections(full_text)

    # Also correct individual segment texts
    for seg in raw_segments:
        if seg.get("text"):
            seg["text"], _ = apply_vocabulary_corrections(seg["text"])

    vocab_log = VocabularyLog(
        corrections=[
            VocabularyCorrection(
                original=c["original"],
                corrected=c["corrected"],
                category=c["category"],
            )
            for c in correction_records
        ],
        total_corrections=len(correction_records),
        unique_terms_corrected=len({c["corrected"] for c in correction_records}),
    )

    post_processing_source = "regex"

    # Step 5: LLM post-processing (optional, with token budget check)
    detected_slokas: list[DetectedSloka] = []
    if enable_llm_postprocess:
        if len(corrected_text) > LLM_POST_PROCESS_MAX_CHARS:
            logger.warning(
                "Step 5: Text exceeds LLM post-processing budget (%d > %d chars); "
                "truncating input to LLM while preserving full transcript",
                len(corrected_text), LLM_POST_PROCESS_MAX_CHARS,
            )
        logger.info("Step 5: Running LLM post-processing")
        llm_input = corrected_text[:LLM_POST_PROCESS_MAX_CHARS]
        was_truncated = len(corrected_text) > LLM_POST_PROCESS_MAX_CHARS
        llm_text, llm_segments, llm_slokas = post_process_transcript_llm(
            llm_input, raw_segments,
        )
        if llm_text != llm_input:
            if was_truncated:
                # LLM only processed partial text — keep full transcript,
                # but still use LLM-cleaned segments
                logger.info(
                    "Step 5: LLM applied to segments only (text was truncated)"
                )
                raw_segments = llm_segments
            else:
                corrected_text = llm_text
                raw_segments = llm_segments
            post_processing_source = "llm"

        detected_slokas = [
            DetectedSloka(
                segment_index=0,  # Approximate — LLM doesn't track segment index
                text=s.get("text", ""),
                probable_reference=s.get("probable_reference"),
                confidence=s.get("confidence", 0.5),
            )
            for s in llm_slokas
            if s.get("text")
        ]
    else:
        logger.info("Step 5: Skipping LLM post-processing (disabled)")

    # Step 6: Build output
    logger.info("Step 6: Building TranscriptOutput")
    segments = [
        Segment(
            start=s["start"],
            end=s["end"],
            text=s["text"],
            speaker=s.get("speaker"),
            confidence=min(1.0, max(0.0, 1.0 + s["confidence"])) if s.get("confidence") is not None and s["confidence"] < 0 else s.get("confidence"),
            language=detected_language,
        )
        for s in raw_segments
        if s.get("text", "").strip()
    ]

    if not segments:
        raise TranscriptionError("No valid segments after processing")

    _check_hallucination(raw_segments)

    word_count = len(corrected_text.split())
    summary = (
        f"Transcribed {duration:.0f}s of audio. "
        f"{len(segments)} segments, {word_count} words. "
        f"Language: {detected_language}. "
        f"Speakers: {speakers_detected}. "
        f"Vocabulary corrections: {len(correction_records)}."
    )

    return TranscriptOutput(
        source_audio=audio_path,
        segments=segments,
        full_text=corrected_text,
        duration_seconds=duration,
        language=detected_language,
        whisper_model=model_size,
        speakers_detected=speakers_detected,
        vocabulary_log=vocab_log,
        detected_slokas=detected_slokas,
        post_processing_source=post_processing_source,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# CrewAI Agentic Mode
# ---------------------------------------------------------------------------


def build_transcriber_agent() -> Agent:
    """Create the Transcriber Agent with all tools. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode. pip install crewai[tools]")
    return Agent(
        role="Sanskrit-Aware Transcription Specialist",
        goal=(
            "Produce high-accuracy transcriptions of Gaudiya Vaishnava lectures "
            "with speaker diarization, correct Sanskrit/Bengali transliterations, "
            "and identified verse quotations."
        ),
        backstory=(
            "You are an expert transcriptionist fluent in English, Sanskrit, "
            "and Bengali. You specialize in Gaudiya Vaishnava discourses and "
            "can accurately transcribe even rapid Sanskrit verse recitations. "
            "You use faster-whisper for initial transcription, then apply "
            "domain-specific corrections and speaker identification."
        ),
        tools=[
            WhisperTranscribeTool(),
            SpeakerDiarizeTool(),
            VocabCorrectionTool(),
            LlmPostProcessTool(),
        ],
        verbose=True,
    )


def build_transcription_task(agent: Agent, audio_path: str) -> Task:
    """Create the Transcription task. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode.")
    return Task(
        description=(
            f"Transcribe the audio file at {audio_path}. "
            "Apply domain vocabulary corrections for Sanskrit/Bengali terms. "
            "Identify speakers and detect Sanskrit verse quotations."
        ),
        expected_output=(
            "A TranscriptOutput JSON with timestamped segments, speaker labels, "
            "vocabulary corrections, and detected śloka references."
        ),
        agent=agent,
    )
