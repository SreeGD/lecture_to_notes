"""
Level 2: Pipeline tests for Agent 02 (Transcriber).

Tests run_transcription_pipeline() with mocked Whisper and diarization.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lecture_agents.agents.transcriber_agent import run_transcription_pipeline
from lecture_agents.exceptions import TranscriptionError
from lecture_agents.tools.domain_vocabulary import (
    apply_vocabulary_corrections,
    build_whisper_prompt,
)


# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------


MOCK_WHISPER_RESULT = {
    "segments": [
        {"start": 0.0, "end": 15.0, "text": "So krishna says to arjun in the bhagavad gita", "confidence": -0.3},
        {"start": 15.0, "end": 30.0, "text": "karmany evadhikaras te ma phaleshu kadachana", "confidence": -0.5},
        {"start": 30.0, "end": 50.0, "text": "You have a right to perform your prescribed duty", "confidence": -0.1},
        {"start": 50.0, "end": 65.0, "text": "Srila prabhupada explains in his purport", "confidence": -0.2},
    ],
    "language": "en",
    "language_probability": 0.95,
    "model": "large-v3",
    "duration": 65.0,
}

MOCK_DIARIZE_RESULT = {
    "success": True,
    "segments": [
        {"start": 0.0, "end": 65.0, "speaker": "SPEAKER_00"},
    ],
    "num_speakers": 1,
    "error": None,
}


# ---------------------------------------------------------------------------
# Domain vocabulary tests
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestDomainVocabulary:

    def test_build_whisper_prompt(self):
        prompt = build_whisper_prompt()
        assert "Krsna" in prompt
        assert "Prabhupada" in prompt

    def test_build_prompt_with_speaker(self):
        prompt = build_whisper_prompt(speaker_name="HH Sivarama Svami")
        assert "HH Sivarama Svami" in prompt

    def test_vocabulary_corrections_krishna(self):
        text = "So krishna says to arjun"
        corrected, corrections = apply_vocabulary_corrections(text)
        assert "Krsna" in corrected
        assert len(corrections) > 0

    def test_vocabulary_corrections_prabhupada(self):
        text = "probe upon said this is very important"
        corrected, corrections = apply_vocabulary_corrections(text)
        assert "Prabhupada" in corrected

    def test_no_false_corrections(self):
        text = "The weather is nice today"
        corrected, corrections = apply_vocabulary_corrections(text)
        assert corrected == text
        assert len(corrections) == 0


# ---------------------------------------------------------------------------
# Pipeline tests (mocked Whisper)
# ---------------------------------------------------------------------------


@pytest.mark.pipeline
class TestRunTranscriptionPipeline:

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio", return_value=MOCK_WHISPER_RESULT)
    @patch("lecture_agents.agents.transcriber_agent.diarize_audio", return_value=MOCK_DIARIZE_RESULT)
    @patch("lecture_agents.agents.transcriber_agent.post_process_transcript_llm")
    def test_pipeline_produces_valid_output(
        self, mock_llm, mock_diarize, mock_whisper, mock_audio_file
    ):
        mock_llm.return_value = ("cleaned text " * 10, MOCK_WHISPER_RESULT["segments"], [])
        result = run_transcription_pipeline(
            str(mock_audio_file),
            model_size="tiny",
            enable_diarization=True,
            enable_llm_postprocess=True,
        )
        assert len(result.segments) > 0
        assert result.duration_seconds == 65.0
        assert result.whisper_model == "tiny"

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio", return_value=MOCK_WHISPER_RESULT)
    @patch("lecture_agents.agents.transcriber_agent.diarize_audio")
    def test_pipeline_without_diarization(self, mock_diarize, mock_whisper, mock_audio_file):
        result = run_transcription_pipeline(
            str(mock_audio_file),
            model_size="tiny",
            enable_diarization=False,
            enable_llm_postprocess=False,
        )
        mock_diarize.assert_not_called()
        assert result.speakers_detected == 0

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio", return_value=MOCK_WHISPER_RESULT)
    @patch("lecture_agents.agents.transcriber_agent.diarize_audio", return_value=MOCK_DIARIZE_RESULT)
    def test_pipeline_applies_vocabulary_corrections(
        self, mock_diarize, mock_whisper, mock_audio_file
    ):
        result = run_transcription_pipeline(
            str(mock_audio_file),
            model_size="tiny",
            enable_diarization=False,
            enable_llm_postprocess=False,
        )
        # "krishna" should be corrected to "Krsna"
        assert "Krsna" in result.full_text
        assert result.vocabulary_log.total_corrections > 0

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio")
    def test_pipeline_handles_empty_segments(self, mock_whisper, mock_audio_file):
        mock_whisper.return_value = {
            "segments": [],
            "language": "en",
            "language_probability": 0.5,
            "model": "tiny",
            "duration": 10,
        }
        with pytest.raises(TranscriptionError, match="no segments"):
            run_transcription_pipeline(
                str(mock_audio_file),
                model_size="tiny",
                enable_diarization=False,
                enable_llm_postprocess=False,
            )

    def test_pipeline_rejects_missing_file(self):
        with pytest.raises(TranscriptionError, match="not found"):
            run_transcription_pipeline(
                "/nonexistent/audio.wav",
                model_size="tiny",
                enable_diarization=False,
                enable_llm_postprocess=False,
            )

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio", return_value=MOCK_WHISPER_RESULT)
    @patch("lecture_agents.agents.transcriber_agent.diarize_audio")
    def test_pipeline_diarization_failure_continues(
        self, mock_diarize, mock_whisper, mock_audio_file
    ):
        mock_diarize.return_value = {
            "success": False,
            "segments": [],
            "num_speakers": 0,
            "error": "pyannote not installed",
        }
        result = run_transcription_pipeline(
            str(mock_audio_file),
            model_size="tiny",
            enable_diarization=True,
            enable_llm_postprocess=False,
        )
        # Should succeed despite diarization failure
        assert len(result.segments) > 0
        assert result.speakers_detected == 0

    @patch("lecture_agents.agents.transcriber_agent.transcribe_audio", return_value=MOCK_WHISPER_RESULT)
    def test_pipeline_post_processing_source(self, mock_whisper, mock_audio_file):
        result = run_transcription_pipeline(
            str(mock_audio_file),
            model_size="tiny",
            enable_diarization=False,
            enable_llm_postprocess=False,
        )
        assert result.post_processing_source == "regex"
