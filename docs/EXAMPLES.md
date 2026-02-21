# Lecture-to-Notes Pipeline -- Working Examples

## Quick Start

```bash
python run_pipeline.py "https://audio.iskcondesiretree.com/02_-_ISKCON_Swamis/ISKCON_Swamis_-_A_to_C/His_Holiness_Bhakti_Rasamrita_Swami/English_Lectures/Nectar_of_Instruction/BRasamritaSw_NOI_-_Verse_02.mp3" \
  --title "Nectar of Instruction Verse 2" \
  --speaker "Bhakti Rasamrita Swami" \
  -v
```

## CLI Options

### Basic usage

```bash
python run_pipeline.py "URL" --title "My Notes" -v
```

### With speaker and diarization

```bash
python run_pipeline.py "URL" \
  --title "SB Class" \
  --speaker "Radhanath Swami" \
  --diarize \
  -v
```

### Different Whisper model (faster, less accurate)

```bash
python run_pipeline.py "URL" --whisper-model medium -v
```

### Disable VAD (for noisy recordings)

```bash
python run_pipeline.py "URL" --no-vad -v
```

### Generate PDF output

```bash
python run_pipeline.py "URL" --title "Study Notes" --pdf -v
```

### Without LLM enrichment (faster, less rich)

```bash
python run_pipeline.py "URL" --no-llm -v
```

## Multi-URL Batch

```bash
python run_pipeline.py \
  "URL1" "URL2" "URL3" \
  --title "BG Chapter 1 Series" \
  --speaker "Speaker Name" \
  -v
```

## Resume from Checkpoint

```bash
# Original run failed at enrichment -- resume from there:
python run_pipeline.py "URL" --from-agent 3 --output output/

# Re-run just compilation (agent 4) using existing enriched data:
python run_pipeline.py "URL" --from-agent 4 --output output/
```

Agent numbers: 1=Download, 2=Transcribe, 3=Enrich, 4=Compile, 5=PDF

## Python API

```python
from lecture_agents.orchestrator import run_single_url_pipeline, run_multi_url_pipeline

# Single URL
book, pdf = run_single_url_pipeline(
    url="https://audio.iskcondesiretree.com/.../lecture.mp3",
    title="Lecture Notes",
    speaker="Speaker Name",
    enable_llm=True,
)
print(f"Output: {book.output_path}")
print(f"Words: {book.report.total_words}")

# Multiple URLs
book, pdf = run_multi_url_pipeline(
    urls=["url1", "url2"],
    title="Collected Lectures",
    speaker="Speaker Name",
)
```

## REST API Workflow

### Submit a job

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://audio.iskcondesiretree.com/.../lecture.mp3"],
    "title": "Lecture Notes",
    "speaker": "Speaker Name"
  }'
```

### Poll for progress

```bash
curl http://localhost:8000/api/v1/jobs/{job_id}
```

### Download the output

```bash
# Get Markdown
curl -O http://localhost:8000/api/v1/jobs/{job_id}/files/Lecture_Notes.md

# Get PDF (if generated)
curl -O http://localhost:8000/api/v1/jobs/{job_id}/files/Lecture_Notes.pdf
```

### Retry a failed job

```bash
curl -X POST http://localhost:8000/api/v1/jobs/{job_id}/retry
```

## Output Directory Structure

```
output/
└── Lecture_Title_abc12345/
    ├── Lecture_Title.md              # Final Markdown book
    ├── Lecture_Title.pdf             # PDF (if --pdf)
    ├── job_meta.json                 # Job metadata
    ├── audio/
    │   └── downloads/                # Original downloaded audio
    │       └── lecture_001.wav       # Normalized 16kHz mono WAV
    └── checkpoints/
        ├── manifest.json             # Download manifest
        ├── url_001_transcript.json   # Transcription output
        ├── url_001_enriched.json     # Enrichment output
        └── book_output.json          # Compiled book
```

## Browse ISKCON Desire Tree

```bash
# Browse root
curl http://localhost:8000/api/v1/browse

# Browse a speaker's lectures
curl "http://localhost:8000/api/v1/browse?path=/02_-_ISKCON_Swamis/..."

# Search for a topic
curl "http://localhost:8000/api/v1/browse/search?q=Bhagavad%20Gita"
```
