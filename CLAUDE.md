# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-Agent Lecture-to-Notes Pipeline v1.0 — a 5-agent system that transforms audio lectures (primarily Gaudiya Vaishnava discourses) into enriched, structured, publishable notes in Markdown format. The system downloads audio, transcribes locally with faster-whisper, enriches with vedabase.io-verified scripture references, and compiles into notes format.

**Critical Rule:** All scripture references must be verified against vedabase.io. No speculation. Only parampara-authorized content.

## Commands

### Install dependencies
```bash
pip install -e .
# With speaker diarization:
pip install -e ".[diarize]"
# With CrewAI agentic mode:
pip install -e ".[crewai]"
# With LLM enrichment:
pip install -e ".[llm]"
# System dependency:
brew install ffmpeg
```

### Run tests
```bash
# All tests
pytest

# By marker
pytest -m schema      # Schema validation tests (no LLM, no I/O)
pytest -m tool        # Tool function tests (may use mocks)
pytest -m pipeline    # Deterministic pipeline tests
pytest -m llm         # Tests that call real LLM
pytest -m integration # Cross-agent integration tests
pytest -m slow        # Tests requiring audio download/transcription

# Single test file
pytest tests/unit/test_download_schema.py -v
```

### Run the pipeline
```bash
# Single URL
python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE"

# Multiple URLs
python run_pipeline.py "url1" "url2" "url3"

# With options
python run_pipeline.py "url" --title "My Book" --output results/ --no-diarize --verbose
```

### Run from Python
```python
from lecture_agents.orchestrator import run_single_url_pipeline, run_multi_url_pipeline

# Single URL
book = run_single_url_pipeline("https://youtube.com/watch?v=EXAMPLE")

# Multiple URLs
book = run_multi_url_pipeline(["url1", "url2", "url3"], title="Series Title")
```

## Architecture

### Agent Pipeline

```
URL(s) → Downloader → Transcriber → Enrichment → Compiler → book.md
            Agent 1      Agent 2       Agent 3      Agent 4
```

1. **Agent 01: Downloader** — downloads audio from URLs (yt-dlp, httpx), normalizes to 16kHz mono WAV (ffmpeg)
2. **Agent 02: Transcriber** — local faster-whisper transcription, optional speaker diarization (pyannote.audio), Sanskrit/Bengali domain vocabulary, optional LLM post-processing
3. **Agent 03: Enrichment** — identifies scripture references, verifies against vedabase.io, builds glossary and thematic index. Never speculates.
4. **Agent 04: Compiler** — assembles enriched notes into structured Markdown book with chapters, verse annotations, glossary, and indices

Each agent has two execution paths:
1. **Deterministic pipeline** (`run_*_pipeline()`) — no LLM, used by tests
2. **Agentic pipeline** (`build_*_agent()` + `build_*_task()`) — CrewAI agent with LLM reasoning

All paths produce validated Pydantic schemas.

### Key modules

- `src/lecture_agents/schemas/pipeline_state.py` — PipelineState, PerURLState shared across all agents
- `src/lecture_agents/schemas/download_output.py` — DownloadManifest, DownloadResult, MediaMetadata
- `src/lecture_agents/schemas/transcript_output.py` — TranscriptOutput, Segment, VocabularyLog
- `src/lecture_agents/schemas/enrichment_output.py` — EnrichedNotes, Reference, VerificationResult, GlossaryEntry
- `src/lecture_agents/schemas/compiler_output.py` — BookOutput, Chapter, CompilationReport
- `src/lecture_agents/agents/downloader_agent.py` — run_download_pipeline()
- `src/lecture_agents/agents/transcriber_agent.py` — run_transcription_pipeline()
- `src/lecture_agents/agents/enrichment_agent.py` — run_enrichment_pipeline()
- `src/lecture_agents/agents/compiler_agent.py` — run_compiler_pipeline()
- `src/lecture_agents/orchestrator.py` — run_single_url_pipeline(), run_multi_url_pipeline()
- `src/lecture_agents/tools/vedabase_fetcher.py` — fetch_verse() with JSON caching
- `src/lecture_agents/config/constants.py` — all configuration constants and domain vocabulary

### Tool pattern

Each tool file exports a pure function and a BaseTool wrapper:
```python
def download_with_ytdlp(url: str, output_dir: str) -> dict: ...
class YtDlpDownloadTool(BaseTool): ...
```

### Vedabase.io URL patterns

- BG: `https://vedabase.io/en/library/bg/{chapter}/{verse}/`
- SB: `https://vedabase.io/en/library/sb/{canto}/{chapter}/{verse}/`
- CC: `https://vedabase.io/en/library/cc/{division}/{chapter}/{verse}/`
- NOI: `https://vedabase.io/en/library/noi/{verse}/`
- ISO: `https://vedabase.io/en/library/iso/{verse}/`

## Siddhanta Fidelity Principle

Every verse, translation, purport, and philosophical explanation must be verified against vedabase.io. The system must NEVER speculate, infer, or generate philosophical content from LLM training data alone. If a verse cannot be verified against vedabase.io, it must be flagged as [UNVERIFIED] and excluded from the final output.
