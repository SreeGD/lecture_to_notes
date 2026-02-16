"""
Centralized configuration constants for the Lecture-to-Notes Pipeline.

All magic numbers, vocabulary lists, and configuration defaults live here.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Audio Normalization (Agent 1: Downloader)
# ---------------------------------------------------------------------------

AUDIO_SAMPLE_RATE: int = 16000         # 16kHz for optimal Whisper performance
AUDIO_CHANNELS: int = 1                 # Mono
AUDIO_FORMAT: str = "wav"               # WAV for Whisper input
MAX_AUDIO_SIZE_MB: int = 2048           # 2GB hard abort limit
WARN_AUDIO_SIZE_MB: int = 500           # 500MB warning threshold
MAX_AUDIO_DURATION_HOURS: int = 4       # Reject audio > 4 hours
MIN_AUDIO_DURATION_SECONDS: int = 30    # Reject audio < 30 seconds

# Download behavior
MAX_CONCURRENT_DOWNLOADS: int = 3
DOWNLOAD_RETRIES: int = 3
DOWNLOAD_BACKOFF_BASE: float = 2.0      # Exponential backoff: 2s, 8s, 32s
RATE_LIMIT_DELAY: float = 2.0           # Minimum seconds between requests to same domain

# ---------------------------------------------------------------------------
# Whisper Configuration (Agent 2: Transcriber)
# ---------------------------------------------------------------------------

WHISPER_MODEL_SIZE: str = "large-v3"
WHISPER_LANGUAGE: str = "en"
WHISPER_BEAM_SIZE: int = 5
WHISPER_VAD_FILTER: bool = True
WHISPER_COMPUTE_TYPE: str = "int8"      # For CPU; use "float16" for GPU

# Speaker diarization
MIN_SPEAKERS: int = 1
MAX_SPEAKERS: int = 10
SPEAKER_LABEL_PRIMARY: str = "Speaker"
SPEAKER_LABEL_QUESTIONER: str = "Questioner"

# Paragraph-level timestamp threshold (seconds of silence)
PARAGRAPH_PAUSE_THRESHOLD: float = 2.0

# ---------------------------------------------------------------------------
# Vedabase Configuration (Agent 3: Enrichment)
# ---------------------------------------------------------------------------

VEDABASE_BASE_URL: str = "https://vedabase.io/en/library"
VEDABASE_CACHE_FILE: str = "cache/vedabase_cache.json"
VEDABASE_REQUEST_DELAY: float = 1.0     # Polite delay between requests
VEDABASE_TIMEOUT: int = 30              # HTTP timeout in seconds

# Scripture abbreviation -> vedabase.io path prefix
SCRIPTURE_ABBREVIATIONS: dict[str, str] = {
    "BG": "bg",            # Bhagavad-gita As It Is
    "SB": "sb",            # Srimad-Bhagavatam
    "CC": "cc",            # Caitanya-caritamrita
    "NOI": "noi",          # Nectar of Instruction
    "NOD": "nod",          # Nectar of Devotion
    "ISO": "iso",          # Sri Isopanisad
    "BS": "bs",            # Brahma-samhita
    "TLC": "tlc",          # Teachings of Lord Caitanya
    "KB": "kb",            # Krsna Book
}

# CC division mappings (Adi/Madhya/Antya -> URL path)
CC_DIVISIONS: dict[str, str] = {
    "ADI": "adi",
    "MADHYA": "madhya",
    "ANTYA": "antya",
}

# ---------------------------------------------------------------------------
# Domain Vocabulary (Agent 2 + 3)
# ---------------------------------------------------------------------------

DEITY_NAMES: list[str] = [
    "Krsna", "Krishna", "Kṛṣṇa",
    "Radha", "Rādhā", "Radharani", "Rādhārāṇī",
    "Caitanya", "Mahaprabhu", "Mahāprabhu",
    "Nityananda", "Nityānanda",
    "Visnu", "Viṣṇu", "Narayana", "Nārāyaṇa",
    "Govinda", "Gopinatha", "Gopīnātha",
    "Madana-mohana", "Damodara", "Dāmodara",
    "Jagannatha", "Jagannātha",
    "Balarama", "Baladeva", "Balabhadra",
    "Siva", "Śiva", "Brahma", "Brahmā",
    "Rama", "Rāma", "Laksmana", "Lakṣmaṇa",
    "Hanuman", "Hanumān",
    "Nrsimha", "Nṛsiṁha", "Narasimha",
    "Varaha", "Varāha", "Vamana", "Vāmana",
]

SCRIPTURE_NAMES: list[str] = [
    "Bhagavad-gita", "Bhagavad-gītā", "Gita", "Gītā",
    "Srimad-Bhagavatam", "Śrīmad-Bhāgavatam", "Bhagavatam", "Bhāgavatam",
    "Caitanya-caritamrita", "Caitanya-caritāmṛta",
    "Bhakti-rasamrita-sindhu", "Bhakti-rasāmṛta-sindhu",
    "Ujjvala-nilamani", "Ujjvala-nīlamaṇi",
    "Hari-bhakti-vilasa", "Hari-bhakti-vilāsa",
    "Siksastaka", "Śikṣāṣṭaka",
    "Prema-vivarta",
    "Jaiva-dharma",
    "Nectar of Devotion",
    "Nectar of Instruction",
    "Teachings of Lord Caitanya",
    "Sri Isopanisad", "Śrī Īśopaniṣad",
    "Krsna Book", "Kṛṣṇa Book",
    "Brahma-samhita", "Brahma-saṁhitā",
]

ACARYA_NAMES: list[str] = [
    "Prabhupada", "Prabhupāda", "Śrīla Prabhupāda",
    "Bhaktisiddhanta", "Bhaktisiddhānta", "Bhaktisiddhānta Sarasvatī",
    "Bhaktivinoda", "Bhaktivinoda Ṭhākura",
    "Rupa Gosvami", "Rūpa Gosvāmī",
    "Sanatana Gosvami", "Sanātana Gosvāmī",
    "Jiva Gosvami", "Jīva Gosvāmī",
    "Raghunatha dasa Gosvami", "Raghunātha dāsa Gosvāmī",
    "Visvanatha Cakravarti", "Viśvanātha Cakravartī",
    "Baladeva Vidyabhusana", "Baladeva Vidyābhūṣaṇa",
    "Narottama dasa Thakura", "Narottama dāsa Ṭhākura",
    "Gaurakisora dasa Babaji", "Gaurakiśora dāsa Bābājī",
    "Madhvacarya", "Madhvācārya",
    "Ramanujacarya", "Rāmānujācārya",
]

PHILOSOPHICAL_TERMS: list[str] = [
    "prema", "prema-bhakti",
    "bhakti", "sadhana-bhakti", "sādhana-bhakti",
    "raganuga", "rāgānuga", "vaidhi", "vaidhī",
    "rasa", "sthāyi-bhāva", "vibhāva", "anubhāva",
    "sattvika", "sāttvika", "vyabhicārī",
    "santa", "śānta", "dasya", "dāsya",
    "sakhya", "vatsalya", "vātsalya", "madhurya", "mādhurya",
    "sambandha", "abhidheya", "prayojana",
    "tattva", "jiva", "jīva", "atma", "ātmā",
    "paramatma", "paramātmā", "brahman",
    "maya", "māyā", "lila", "līlā",
    "svarupa", "svarūpa", "vastu",
    "dharma", "karma", "jnana", "jñāna", "yoga",
    "sankhya", "sāṅkhya",
    "diksa", "dīkṣā", "siksa", "śikṣā",
    "seva", "sevā", "kirtana", "kīrtana",
    "smarana", "smaraṇa", "arcana", "arcanā",
    "vandana", "dasyam", "sakhyam", "atma-nivedanam", "ātma-nivedanam",
    "sampradaya", "sampradāya", "parampara", "paramparā",
    "acarya", "ācārya", "guru",
    "sadhu", "sādhu", "sastra", "śāstra",
    "vaisnava", "vaiṣṇava",
    "prasadam", "prasādam", "murti", "mūrti",
    "mantra", "japa", "kirtan", "sankirtana", "saṅkīrtana",
    "sloka", "śloka", "sutra", "sūtra",
]

PLACE_NAMES: list[str] = [
    "Vrndavana", "Vṛndāvana", "Vrindavan",
    "Mayapur", "Māyāpur",
    "Jagannatha Puri", "Jagannātha Purī", "Puri", "Purī",
    "Navadvipa", "Navadvīpa",
    "Govardhana", "Govardhana Hill",
    "Radha-kunda", "Rādhā-kuṇḍa",
    "Syama-kunda", "Śyāma-kuṇḍa",
    "Mathura", "Mathurā",
    "Dvaraka", "Dvārakā",
    "Ayodhya", "Ayodhyā",
    "Gaya",
]

# Combined vocabulary for Whisper initial prompt
DOMAIN_VOCABULARY: list[str] = (
    DEITY_NAMES + SCRIPTURE_NAMES + ACARYA_NAMES
    + PHILOSOPHICAL_TERMS + PLACE_NAMES
)

# ---------------------------------------------------------------------------
# Compiler Configuration (Agent 4)
# ---------------------------------------------------------------------------

BOOK_TITLE_DEFAULT: str = "Lecture Notes"
CHAPTER_MIN_SEGMENTS: int = 3
CHAPTER_MAX_SEGMENTS: int = 200
GLOSSARY_MIN_ENTRIES: int = 5
WORD_COUNT_TARGET_MIN: int = 5000       # Per 60-min lecture
WORD_COUNT_TARGET_MAX: int = 30000      # Per 90-min lecture

# ---------------------------------------------------------------------------
# PDF Generation (Agent 5)
# ---------------------------------------------------------------------------

PDF_PAGE_SIZE: str = "A4"
PDF_MARGIN_MM: int = 18
PDF_DEFAULT_FONT: str = "DejaVu"

# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

PIPELINE_OUTPUT_DIR: str = "output"
PIPELINE_CACHE_DIR: str = "cache"
CHECKPOINT_DIR_NAME: str = "checkpoints"
