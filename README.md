# Lecture-to-Notes Pipeline

A multi-agent system that transforms audio lectures — primarily Gaudiya Vaishnava discourses — into enriched, structured, publishable notes in Markdown format.

The pipeline downloads audio, transcribes locally with [faster-whisper](https://github.com/SYSTRAN/faster-whisper) or [whisper.cpp](https://github.com/ggerganov/whisper.cpp), enriches with [vedabase.io](https://vedabase.io)-verified scripture references, generates LLM-enhanced thematic study notes, compiles into book format, and optionally generates a styled PDF.

## Pipeline Architecture

```
URL(s) → Agent 1 → Agent 2 → Agent 3 → Validation → Agent 4 → Agent 5
         Download   Transcribe  Enrich               Compile    PDF
```

| Agent | Role | Key Technology |
|-------|------|----------------|
| **1. Downloader** | Downloads audio from YouTube, HTTP, or local paths; normalizes to 16kHz mono WAV | yt-dlp, httpx, ffmpeg |
| **2. Transcriber** | Local speech-to-text with domain vocabulary, optional speaker diarization and LLM post-processing | faster-whisper, whisper.cpp |
| **3. Enrichment** | Identifies scripture references (regex + LLM + MCP fuzzy matching), verifies against vedabase.io, generates LLM-enhanced notes | Anthropic Claude, MCP |
| **Validation** | Checks content density, hallucination detection, segment gaps | Built-in |
| **4. Compiler** | Assembles enriched notes into a structured Markdown book with chapters, verse annotations, glossary, and indices | Pydantic |
| **5. PDF** *(optional)* | Generates a styled PDF from the compiled book | fpdf2 |

All agents produce validated [Pydantic](https://docs.pydantic.dev/) schemas. Each agent has two execution paths:
- **Deterministic pipeline** (`run_*_pipeline()`) — no LLM, fully testable
- **Agentic pipeline** (`build_*_agent()`) — CrewAI agent with LLM reasoning

## Web UI

A React frontend provides a browser-based interface for submitting jobs, monitoring progress, and viewing results.

```bash
# Start the API server
cd ~/Projects/lecture_to_notes
source .venv/bin/activate
uvicorn lecture_agents.api.app:app --reload --host 0.0.0.0 --port 8000

# Start the frontend (separate terminal)
cd frontend
npm install && npm run dev
```

The web UI includes:
- **Job submission form** with configurable Whisper model/backend, enrichment mode, and advanced options
- **Real-time job progress** tracking with step-by-step status updates
- **ISKCON Desire Tree audio browser** for browsing and selecting lecture audio files
- **Topic-based browsing** across 40+ categorized lecture topics
- **Search** with speaker-level grouping across the audio library
- **Output viewer** with rendered Markdown and downloadable files

## Enrichment Modes

The pipeline supports two LLM enrichment modes:

| Mode | Prompt | Best For |
|------|--------|----------|
| **Lecture-centric** (v7.0) | Organizes content thematically — stories, analogies, key teachings, practical instructions | Lectures with few or no identifiable verse references |
| **Verse-centric** (v6.0) | Generates 15 sections per verified verse — word-by-word analysis, SARANAGATHI classification | Lectures with many clearly quoted verses |
| **Auto** *(default)* | Selects lecture-centric if ≤2 verified verses, verse-centric otherwise | General use |

### Lecture-Centric Output (v7.0)

Produces 8 thematic sections:
1. **Header** — Title, speaker, key verse, summary
2. **Key Teachings** — 3-7 main principles with supporting evidence
3. **Stories & Illustrations** — Narrative accounts with setup, key moment, and teaching
4. **Analogies & Metaphors** — Vivid comparisons with their spiritual significance
5. **Verse References & Analysis** — All verses discussed, with verified data where available
6. **Practical Instructions** — Actionable do/avoid/how checklists
7. **Q&A Summary** — Question-and-answer pairs (if present)
8. **Summary & Cross-References** — Key points, verse table, glossary, further study

## Quick Start

### Prerequisites

- Python 3.12+
- [ffmpeg](https://ffmpeg.org/) (`brew install ffmpeg` on macOS)
- An [Anthropic API key](https://console.anthropic.com/) for LLM enrichment

### Installation

```bash
pip install -e .
```

Optional extras:

```bash
pip install -e ".[diarize]"   # Speaker diarization (pyannote.audio)
pip install -e ".[crewai]"    # CrewAI agentic mode
pip install -e ".[llm]"       # LLM enrichment (Anthropic Claude)
pip install -e ".[pdf]"       # PDF generation (fpdf2)
pip install "mcp[cli]>=1.2.0" # MCP verse tools (fuzzy Sanskrit matching)
```

### Environment

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=sk-ant-...
```

The API server loads this automatically via `python-dotenv`.

### Usage

```bash
# Single URL
python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE"

# Multiple URLs compiled into one book
python run_pipeline.py "url1" "url2" "url3" --title "Collected Lectures"

# With speaker diarization (LLM enrichment is on by default)
python run_pipeline.py "url" --speaker "Srila Prabhupada" --diarize -v

# Generate PDF output
python run_pipeline.py "url" --pdf

# Use whisper.cpp backend (Metal/CoreML acceleration on macOS)
python run_pipeline.py "url" --whisper-backend whisper.cpp --whisper-model small

# Force lecture-centric enrichment mode
python run_pipeline.py "url" --enrichment-mode lecture-centric

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
| `--whisper-model`, `-m` | Whisper model size (`tiny`, `base`, `small`, `medium`, `large-v3`) | `large-v3` |
| `--whisper-backend` | Transcription backend (`faster-whisper` or `whisper.cpp`) | `faster-whisper` |
| `--enrichment-mode` | Enrichment prompt (`auto`, `lecture-centric`, `verse-centric`) | `auto` |
| `--no-vad` | Disable Voice Activity Detection filter | *(VAD on)* |
| `--diarize` | Enable speaker diarization (requires `[diarize]` extra) | *(off)* |
| `--no-llm` | Disable LLM enrichment (on by default) | *(LLM on)* |
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
    enrichment_mode="auto",
)

# Multiple URLs
book, pdf = run_multi_url_pipeline(
    urls=["url1", "url2"],
    title="Lecture Series",
    generate_pdf=True,
    enrichment_mode="lecture-centric",
)
```

## REST API

The pipeline runs as a FastAPI server with a REST API.

```bash
uvicorn lecture_agents.api.app:app --reload --host 0.0.0.0 --port 8000
```

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/jobs` | Submit a new pipeline job |
| `GET` | `/api/v1/jobs` | List all jobs |
| `GET` | `/api/v1/jobs/{id}` | Get job details and progress |
| `POST` | `/api/v1/jobs/{id}/cancel` | Cancel a running job |
| `GET` | `/api/v1/jobs/{id}/output` | Get job output (book JSON) |
| `GET` | `/api/v1/jobs/{id}/files/{name}` | Download output files (Markdown, PDF) |
| `GET` | `/api/v1/browse` | Browse ISKCON Desire Tree audio library |
| `GET` | `/api/v1/browse/search` | Search audio library |
| `GET` | `/api/v1/browse/topics` | Get topic taxonomy |
| `GET` | `/api/v1/health` | Health check |

### Job Submission Example

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://audio.iskcondesiretree.com/.../lecture.mp3"],
    "title": "Lecture Notes",
    "speaker": "HH Radhanath Swami",
    "whisper_model": "small",
    "whisper_backend": "whisper.cpp",
    "enable_llm": true,
    "enrichment_mode": "auto",
    "generate_pdf": true
  }'
```

## Whisper Backends

| Backend | Pros | Cons |
|---------|------|------|
| **faster-whisper** | Reliable, good accuracy, CPU-optimized | Slower on macOS (no Metal) |
| **whisper.cpp** | Metal/CoreML acceleration on macOS, fast | `large-v3` can produce low-density output; `small` model recommended |

## Checkpoints and Resumption

The pipeline saves JSON checkpoints after each agent completes, enabling resumption from any point with `--from-agent N`:

```
output/checkpoints/
├── manifest.json              # Agent 1 output (download manifest)
├── url_001_transcript.json    # Agent 2 output (per-URL transcript)
├── url_002_transcript.json
├── url_001_enriched.json      # Agent 3 output (per-URL enriched notes)
├── url_002_enriched.json
├── url_001_validation.json    # Validation report
└── book_output.json           # Agent 4 output (compiled book)
```

This is useful when:
- A long transcription succeeds but enrichment fails — skip re-transcription with `--from-agent 3`
- You want to re-enrich after a fast `--no-llm` run — `--from-agent 3`
- PDF styling needs tweaking without re-running the full pipeline — `--from-agent 5 --pdf`

## Scripture Verification

All scripture references are verified against [vedabase.io](https://vedabase.io). The system **never** speculates or generates philosophical content from LLM training data alone. Unverifiable references are flagged as `[UNVERIFIED]`.

### Reference Identification

References are identified through three methods:
1. **Regex** — Pattern matching for explicit references (BG 2.47, SB 3.25.21, etc.)
2. **LLM** — Claude identifies implicit/paraphrased references missed by regex
3. **MCP Fuzzy Matching** — Garbled Sanskrit from Whisper ASR is matched against all 700 BG verses via the [Vedabase MCP Server](https://github.com/your-repo/vedabase-mcp-server)

### Supported Scriptures

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
│   ├── validation_agent.py
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
│   ├── whispercpp_transcriber.py
│   ├── vedabase_fetcher.py
│   ├── verse_identifier.py
│   ├── llm_enrichment_generator.py
│   ├── mcp_verse_tools.py
│   ├── ffmpeg_normalizer.py
│   ├── http_downloader.py
│   ├── yt_dlp_downloader.py
│   ├── pdf_generator.py
│   └── ...
├── config/
│   ├── constants.py           # All configuration constants
│   ├── enrichment_prompt.py   # Verse-centric prompt (v6.0)
│   └── lecture_prompt.py      # Lecture-centric prompt (v7.0)
├── api/                       # FastAPI REST API
│   ├── app.py                 # Application factory
│   ├── routes.py              # API endpoints
│   ├── models.py              # Request/response models
│   └── job_manager.py         # Background job execution
├── orchestrator.py            # Pipeline orchestration
├── checkpoint.py              # Checkpoint save/load/validate
└── exceptions.py              # Custom exception types

frontend/                      # React web UI
├── src/
│   ├── components/
│   │   ├── JobSubmitForm.tsx   # Job submission with advanced options
│   │   ├── AudioBrowser.tsx   # ISKCON Desire Tree audio browser
│   │   ├── TopicBrowser.tsx   # Topic-based browsing
│   │   └── ...
│   ├── api/
│   │   ├── jobs.ts            # Job API client
│   │   └── types.ts           # TypeScript interfaces
│   └── App.tsx
└── package.json
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
