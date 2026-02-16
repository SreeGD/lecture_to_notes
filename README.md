# Lecture-to-Notes Pipeline

A multi-agent system that transforms audio lectures — primarily Gaudiya Vaishnava discourses — into enriched, structured, publishable notes in Markdown format.

The pipeline downloads audio, transcribes locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper), enriches with [vedabase.io](https://vedabase.io)-verified scripture references, compiles into book format, and optionally generates a styled PDF.

## Pipeline Architecture

```
URL(s) → Agent 1 → Agent 2 → Agent 3 → Agent 4 → Agent 5
         Download   Transcribe  Enrich   Compile    PDF
```

| Agent | Role | Key Technology |
|-------|------|----------------|
| **1. Downloader** | Downloads audio from YouTube, HTTP, or local paths; normalizes to 16kHz mono WAV | yt-dlp, httpx, ffmpeg |
| **2. Transcriber** | Local speech-to-text with domain vocabulary, optional speaker diarization and LLM post-processing | faster-whisper (large-v3), pyannote.audio |
| **3. Enrichment** | Identifies scripture references, verifies against vedabase.io, builds glossary and thematic index | beautifulsoup4, httpx |
| **4. Compiler** | Assembles enriched notes into a structured Markdown book with chapters, verse annotations, glossary, and indices | Pydantic |
| **5. PDF** *(optional)* | Generates a styled PDF from the compiled book | fpdf2 |

All agents produce validated [Pydantic](https://docs.pydantic.dev/) schemas. Each agent has two execution paths:
- **Deterministic pipeline** (`run_*_pipeline()`) — no LLM, fully testable
- **Agentic pipeline** (`build_*_agent()`) — CrewAI agent with LLM reasoning

## Quick Start

### Prerequisites

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on macOS)

### Installation

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[diarize]"   # Speaker diarization (pyannote.audio)
pip install -e ".[crewai]"    # CrewAI agentic mode
pip install -e ".[llm]"       # LLM post-processing (Anthropic)
pip install -e ".[pdf]"       # PDF generation (fpdf2)
```

### Usage

```bash
# Single URL
python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE"

# Multiple URLs compiled into one book
python run_pipeline.py "url1" "url2" "url3" --title "Collected Lectures"

# With speaker diarization and LLM post-processing
python run_pipeline.py "url" --speaker "Srila Prabhupada" --diarize --llm -v

# Generate PDF output
python run_pipeline.py "url" --pdf

# Resume from a specific agent (uses saved checkpoints)
python run_pipeline.py "url" --from-agent 3 --llm -v
```

### CLI Options

| Flag | Description | Default |
|------|-------------|---------|
| `urls` | One or more audio URLs (YouTube, HTTP, or local file paths) | *(required)* |
| `--title`, `-t` | Book title | `Lecture Notes` |
| `--output`, `-o` | Output directory | `output` |
| `--speaker`, `-s` | Speaker name | *(none)* |
| `--whisper-model`, `-m` | Whisper model size | `large-v3` |
| `--no-vad` | Disable Voice Activity Detection filter | *(VAD on)* |
| `--diarize` | Enable speaker diarization (requires `[diarize]` extra) | *(off)* |
| `--llm` | Enable LLM post-processing for transcript cleanup | *(off)* |
| `--pdf` | Generate a styled PDF from the compiled book | *(off)* |
| `--cache` | Path to vedabase.io cache file | `cache/vedabase_cache.json` |
| `--from-agent N` | Start from agent N, loading earlier outputs from checkpoints (1-5) | `1` |
| `--verbose`, `-v` | Enable verbose logging | *(off)* |

### Python API

```python
from lecture_agents.orchestrator import run_single_url_pipeline, run_multi_url_pipeline

# Single URL
book, pdf = run_single_url_pipeline(
    url="https://youtube.com/watch?v=EXAMPLE",
    title="Bhagavad-gita Lecture",
)

# Multiple URLs
book, pdf = run_multi_url_pipeline(
    urls=["url1", "url2"],
    title="Lecture Series",
    generate_pdf=True,
)
```

## Checkpoints and Resumption

The pipeline saves JSON checkpoints after each agent completes, enabling resumption from any point with `--from-agent N`:

```
output/checkpoints/
├── manifest.json              # Agent 1 output (download manifest)
├── url_001_transcript.json    # Agent 2 output (per-URL transcript)
├── url_002_transcript.json
├── url_001_enriched.json      # Agent 3 output (per-URL enriched notes)
├── url_002_enriched.json
└── book_output.json           # Agent 4 output (compiled book)
```

This is useful when:
- A long transcription succeeds but enrichment fails — skip re-transcription with `--from-agent 3`
- You want to re-enrich with `--llm` after a fast initial run — `--from-agent 3 --llm`
- PDF styling needs tweaking without re-running the full pipeline — `--from-agent 5 --pdf`

## Vedabase Verification

All scripture references are verified against [vedabase.io](https://vedabase.io). The system **never** speculates or generates philosophical content from LLM training data alone. Unverifiable references are flagged as `[UNVERIFIED]`.

Supported scriptures:

| Abbreviation | Scripture | URL Pattern |
|-------------|-----------|-------------|
| BG | Bhagavad-gita As It Is | `vedabase.io/en/library/bg/{chapter}/{verse}/` |
| SB | Srimad-Bhagavatam | `vedabase.io/en/library/sb/{canto}/{chapter}/{verse}/` |
| CC | Caitanya-caritamrita | `vedabase.io/en/library/cc/{division}/{chapter}/{verse}/` |
| NOI | Nectar of Instruction | `vedabase.io/en/library/noi/{verse}/` |
| ISO | Sri Isopanisad | `vedabase.io/en/library/iso/{verse}/` |

Fetched verses are cached locally (default: `cache/vedabase_cache.json`) to minimize network requests.

## Project Structure

```
src/lecture_agents/
├── agents/                    # Pipeline agents (1 per stage)
│   ├── downloader_agent.py
│   ├── transcriber_agent.py
│   ├── enrichment_agent.py
│   ├── compiler_agent.py
│   └── pdf_agent.py
├── schemas/                   # Pydantic models for all I/O
│   ├── download_output.py
│   ├── transcript_output.py
│   ├── enrichment_output.py
│   ├── compiler_output.py
│   ├── pdf_output.py
│   └── pipeline_state.py
├── tools/                     # Reusable tool functions
│   ├── whisper_transcriber.py
│   ├── vedabase_fetcher.py
│   ├── verse_identifier.py
│   ├── ffmpeg_normalizer.py
│   ├── http_downloader.py
│   ├── yt_dlp_downloader.py
│   ├── pdf_generator.py
│   └── ...
├── config/
│   └── constants.py           # All configuration constants
├── orchestrator.py            # Pipeline orchestration
├── checkpoint.py              # Checkpoint save/load/validate
└── exceptions.py              # Custom exception types
```

## Testing

```bash
# All tests
pytest

# By marker
pytest -m schema      # Schema validation (no LLM, no I/O)
pytest -m tool        # Tool function tests (mocked I/O)
pytest -m pipeline    # Pipeline orchestration tests
pytest -m llm         # Tests that call a real LLM
pytest -m integration # Cross-agent integration tests
pytest -m slow        # Tests requiring audio download/transcription

# Single file
pytest tests/unit/test_checkpoint.py -v
```

## License

Private — all rights reserved.
