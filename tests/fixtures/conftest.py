"""
Shared test fixtures for Lecture-to-Notes tests.

Provides factory functions, sample data, and reusable pytest fixtures
following the ibd_crew _make_*() pattern.
"""

from __future__ import annotations

import struct
from pathlib import Path

import pytest


FIXTURES_DIR = Path(__file__).parent

# ---------------------------------------------------------------------------
# Sample data for tests
# ---------------------------------------------------------------------------

SAMPLE_URLS = [
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=EXAMPLE_02",
]

SAMPLE_TRANSCRIPT_TEXT = (
    "So in the Bhagavad-gita chapter 2, verse 47, Krishna says to Arjuna, "
    "karmany evadhikaras te ma phaleshu kadachana. You have a right to perform "
    "your prescribed duty, but you are not entitled to the fruits of action. "
    "This is a very important verse. Srila Prabhupada explains in his purport "
    "that there are three considerations here. In the Srimad-Bhagavatam, "
    "canto 1, chapter 2, verse 6, it is said, sa vai pumsam paro dharmo. "
    "The supreme occupation for all humanity is that by which men can attain "
    "to loving devotional service unto the transcendent Lord. This is the "
    "essence of all Vedic literature."
)

SAMPLE_SEGMENTS = [
    {
        "start": 0.0,
        "end": 15.5,
        "text": "So in the Bhagavad-gita chapter 2, verse 47, Krishna says to Arjuna,",
        "speaker": "SPEAKER_00",
        "confidence": 0.95,
    },
    {
        "start": 15.5,
        "end": 30.2,
        "text": "karmany evadhikaras te ma phaleshu kadachana.",
        "speaker": "SPEAKER_00",
        "confidence": 0.72,
    },
    {
        "start": 30.2,
        "end": 55.0,
        "text": (
            "You have a right to perform your prescribed duty, "
            "but you are not entitled to the fruits of action."
        ),
        "speaker": "SPEAKER_00",
        "confidence": 0.97,
    },
    {
        "start": 55.0,
        "end": 70.0,
        "text": "This is a very important verse.",
        "speaker": "SPEAKER_00",
        "confidence": 0.99,
    },
    {
        "start": 70.0,
        "end": 95.0,
        "text": (
            "Srila Prabhupada explains in his purport "
            "that there are three considerations here."
        ),
        "speaker": "SPEAKER_00",
        "confidence": 0.93,
    },
    {
        "start": 95.0,
        "end": 120.0,
        "text": (
            "In the Srimad-Bhagavatam, canto 1, chapter 2, verse 6, "
            "it is said, sa vai pumsam paro dharmo."
        ),
        "speaker": "SPEAKER_00",
        "confidence": 0.88,
    },
    {
        "start": 120.0,
        "end": 150.0,
        "text": (
            "The supreme occupation for all humanity is that by which men "
            "can attain to loving devotional service unto the transcendent Lord."
        ),
        "speaker": "SPEAKER_00",
        "confidence": 0.96,
    },
    {
        "start": 150.0,
        "end": 165.0,
        "text": "This is the essence of all Vedic literature.",
        "speaker": "SPEAKER_00",
        "confidence": 0.98,
    },
]

SAMPLE_VEDABASE_BG_2_47 = {
    "url": "https://vedabase.io/en/library/bg/2/47/",
    "verified": True,
    "devanagari": "कर्मण्येवाधिकारस्ते मा फलेषु कदाचन ।\nमा कर्मफलहेतुर्भूर्मा ते सङ्गोऽस्त्वकर्मणि ॥ ४७ ॥",
    "verse_text": "karmaṇy evādhikāras te\nmā phaleṣu kadācana\nmā karma-phala-hetur bhūr\nmā te saṅgo 'stv akarmaṇi",
    "synonyms": (
        "karmaṇi — in prescribed duties; eva — certainly; adhikāraḥ — right; "
        "te — of you; mā — never; phaleṣu — in the fruits; kadācana — at any time; "
        "mā — never; karma-phala — in the result of the work; hetuḥ — cause; "
        "bhūḥ — become; mā — never; te — of you; saṅgaḥ — attachment; "
        "astu — there should be; akarmaṇi — in not doing prescribed duties."
    ),
    "translation": (
        "You have a right to perform your prescribed duty, but you are not "
        "entitled to the fruits of action. Never consider yourself the cause "
        "of the results of your activities, and never be attached to not "
        "doing your duty."
    ),
    "purport_excerpt": (
        "There are three considerations here: prescribed duties, capricious work, "
        "and inaction. Prescribed duties are activities enjoined in terms of one's "
        "acquired qualities in the modes of material nature."
    ),
}

SAMPLE_VEDABASE_SB_1_2_6 = {
    "url": "https://vedabase.io/en/library/sb/1/2/6/",
    "verified": True,
    "verse_text": "sa vai puṁsāṁ paro dharmo\nyato bhaktir adhokṣaje\nahaituky apratihatā\nyayātmā suprasīdati",
    "translation": (
        "The supreme occupation [dharma] for all humanity is that by which men "
        "can attain to loving devotional service unto the transcendent Lord. "
        "Such devotional service must be unmotivated and uninterrupted to "
        "completely satisfy the self."
    ),
    "purport_excerpt": (
        "In this statement, Śrī Sūta Gosvāmī answers the first question of "
        "the sages of Naimiṣāraṇya. The sages asked about the absolute good, "
        "which is the ultimate occupation."
    ),
}


# ---------------------------------------------------------------------------
# Pytest fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_output_dir(tmp_path: Path) -> Path:
    """Create a temporary output directory."""
    output = tmp_path / "output"
    output.mkdir()
    return output


@pytest.fixture
def mock_cache_dir(tmp_path: Path) -> Path:
    """Create a temporary cache directory."""
    cache = tmp_path / "cache"
    cache.mkdir()
    return cache


@pytest.fixture
def mock_audio_file(tmp_path: Path) -> Path:
    """Create a minimal valid WAV file (2 seconds of silence, 16kHz mono)."""
    wav_path = tmp_path / "test_lecture.wav"
    sample_rate = 16000
    num_samples = sample_rate * 2  # 2 seconds
    bits_per_sample = 16
    byte_rate = sample_rate * 1 * bits_per_sample // 8
    block_align = 1 * bits_per_sample // 8
    data_size = num_samples * block_align

    with open(wav_path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<IHHIIHH", 16, 1, 1, sample_rate, byte_rate, block_align, bits_per_sample))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(b"\x00" * data_size)

    return wav_path


@pytest.fixture
def sample_segments() -> list[dict]:
    """Return a copy of SAMPLE_SEGMENTS for modification in tests."""
    return [dict(s) for s in SAMPLE_SEGMENTS]


@pytest.fixture
def sample_vedabase_cache(tmp_path: Path) -> Path:
    """Create a temporary vedabase cache file with sample data."""
    import json

    cache_path = tmp_path / "vedabase_cache.json"
    cache_data = {
        "BG_2_47": SAMPLE_VEDABASE_BG_2_47,
        "SB_1.2_6": SAMPLE_VEDABASE_SB_1_2_6,
    }
    cache_path.write_text(json.dumps(cache_data, indent=2, ensure_ascii=False))
    return cache_path
