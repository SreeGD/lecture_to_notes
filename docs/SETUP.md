# Setup Guide

Step-by-step installation and configuration for the Lecture-to-Notes Pipeline.

---

## 1. System Requirements

| Requirement | Details |
|---|---|
| **Python** | 3.12 or higher |
| **ffmpeg** | `brew install ffmpeg` on macOS, `apt install ffmpeg` on Debian/Ubuntu |
| **Node.js** | 18+ (for the frontend only) |
| **RAM** | 8 GB minimum recommended. Whisper `large-v3` loads ~3 GB into memory; diarization adds another ~1--2 GB. |
| **OS** | macOS (Intel or Apple Silicon) or Linux. Windows is untested. |

---

## 2. Quick Install

```bash
git clone <repo-url>
cd lecture_to_notes

python -m venv .venv
source .venv/bin/activate   # On Linux/macOS
# .venv\Scripts\activate    # On Windows (unsupported but may work)

pip install -e .
```

This installs the core pipeline with its base dependencies: `pydantic`, `httpx`, `yt-dlp`, `faster-whisper`, `beautifulsoup4`, `mutagen`, and `pytest`.

---

## 3. Install Extras

The project defines several optional dependency groups in `pyproject.toml`. Install only what you need, or combine them.

| Extra | Command | What it adds |
|---|---|---|
| **llm** | `pip install -e ".[llm]"` | LLM enrichment via the Anthropic SDK (`anthropic>=0.39`) |
| **diarize** | `pip install -e ".[diarize]"` | Speaker diarization (`pyannote.audio>=3.1`, `torch>=2.0`) |
| **pdf** | `pip install -e ".[pdf]"` | PDF generation (`fpdf2>=2.8`) |
| **api** | `pip install -e ".[api]"` | REST API server (`fastapi>=0.115`, `uvicorn[standard]>=0.34`) |
| **mcp** | `pip install -e ".[mcp]"` | MCP verse tools (`mcp[cli]>=1.2.0`) |
| **crewai** | `pip install -e ".[crewai]"` | CrewAI agentic mode (`crewai[tools]>=0.102.0`) |

Install several at once by comma-separating them:

```bash
pip install -e ".[llm,diarize,pdf,api]"
```

---

## 4. Environment Variables

Create a `.env` file in the project root. The pipeline reads it automatically on startup.

```env
# Required for LLM enrichment (Agent 03 and LLM post-processing)
ANTHROPIC_API_KEY=sk-ant-...

# Optional -- needed only for pyannote.audio speaker diarization models
HF_TOKEN=hf_...
```

The CLI (`run_pipeline.py`) and API server (`run_server.py`) both load `.env` at startup. If `python-dotenv` is not installed, the CLI falls back to a simple `KEY=VALUE` parser.

> **Note:** Never commit your `.env` file. It is already listed in `.gitignore`.

---

## 5. Whisper Backends

The pipeline supports two local Whisper backends. You only need one.

### faster-whisper (default)

Installed automatically with the base `pip install -e .` command. Uses the CTranslate2 runtime and works on CPU and CUDA GPUs.

```bash
pip install faster-whisper   # already included in base deps
```

### whisper.cpp

An alternative backend using the GGML runtime. Provides Apple Silicon Metal acceleration out of the box.

```bash
pip install pywhispercpp
```

Optionally install the CLI tools for standalone use:

```bash
brew install whisper-cpp
```

---

## 6. Running the Backend

Install the `api` extra first, then start the server:

```bash
pip install -e ".[api]"

# Localhost only (default)
python run_server.py

# Network-accessible
python run_server.py --host 0.0.0.0

# Development mode with auto-reload
python run_server.py --reload

# Custom port and multiple workers
python run_server.py --port 8080 --workers 4
```

Once running, interactive API docs are available at:

- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 7. Running the Frontend

The frontend is a React + Vite + TypeScript application in the `frontend/` directory.

```bash
cd frontend
npm install
npm run dev
```

This starts the dev server at [http://localhost:5173](http://localhost:5173). The backend API must be running on port 8000 for the frontend to function.

To build for production:

```bash
npm run build
npm run preview   # Preview the production build locally
```

---

## 8. Running the CLI

The CLI is the simplest way to process lectures without starting the server.

```bash
# Single URL
python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE" --title "My Notes" -v

# Multiple URLs compiled into one book
python run_pipeline.py URL1 URL2 --title "Series" --speaker "Speaker Name"

# With speaker diarization and PDF output
python run_pipeline.py "URL" --diarize --pdf -v

# Disable LLM post-processing (faster, offline)
python run_pipeline.py "URL" --no-llm

# Resume from a specific agent (e.g., re-enrich from saved transcript)
python run_pipeline.py "URL" --from-agent 3

# Specify Whisper model size
python run_pipeline.py "URL" --whisper-model medium
```

Full option list:

```
python run_pipeline.py --help
```

---

## 9. Verify Installation

Run the quick schema tests to confirm the core library is installed correctly. These require no network access and no LLM key.

```bash
pytest -m schema -v
```

If you installed the API extra, verify the server starts and responds:

```bash
# In one terminal:
python run_server.py

# In another terminal:
curl http://localhost:8000/api/v1/health
```

Run the full non-LLM test suite:

```bash
pytest -m "not llm and not slow" -v
```

---

## 10. GPU / Metal Acceleration

### Apple Silicon (M1/M2/M3/M4)

- **faster-whisper** uses CoreML automatically when running on Apple Silicon. No extra configuration needed.
- **whisper.cpp** (via `pywhispercpp`) uses Metal for GPU-accelerated inference on Apple Silicon.

### NVIDIA CUDA

faster-whisper supports CUDA acceleration. Ensure you have the NVIDIA CUDA toolkit installed, then use `float16` compute type for best performance:

```python
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cuda", compute_type="float16")
```

The CLI uses `large-v3` by default. On CUDA-capable machines, faster-whisper will detect and use the GPU automatically.

### CPU-only

Both backends work on CPU without any special setup. Expect slower transcription times -- roughly 1x real-time for `large-v3` on a modern CPU, compared to 5--10x real-time on GPU.
