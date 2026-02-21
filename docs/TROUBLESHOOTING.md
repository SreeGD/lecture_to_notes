# Troubleshooting Guide

Common issues encountered when running the Lecture-to-Notes pipeline and how to fix them.

---

## Installation Issues

- **ffmpeg not found**: The pipeline requires ffmpeg for audio normalization.
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `apt install ffmpeg`
  - Verify with: `ffmpeg -version`

- **pip install fails**: Ensure you are running Python 3.12 or later.
  - Check version: `python --version`
  - Upgrade pip first: `pip install --upgrade pip`
  - Then retry: `pip install -e .`

- **torch installation issues**: Speaker diarization depends on pyannote.audio, which requires PyTorch. On some platforms, the default torch wheel may not work.
  - Install the diarization extras: `pip install -e ".[diarize]"`
  - If that fails, install a platform-specific torch build first (see https://pytorch.org/get-started/locally/) and then retry.

---

## Whisper Backend Errors

- **"faster-whisper is not installed"**: The default transcription backend requires faster-whisper.
  - Fix: `pip install faster-whisper`

- **"pywhispercpp is not installed"**: If you selected the whisper.cpp backend, it requires pywhispercpp.
  - Fix: `pip install pywhispercpp`

- These checks happen at pipeline startup (Step 0) before any processing begins, so you will see the error immediately.

---

## Validation Failures

The pipeline validates transcription and enrichment quality. Failures are classified as either **CRITICAL** (blocking — the pipeline stops) or **WARNING** (non-blocking — the pipeline continues but flags the issue).

### CRITICAL Failures (pipeline stops)

- **content_density**: "Low content density: X words/min (Y words in Zmin). Expected >= 10 words/min."
  - Cause: Whisper produced very little text relative to the audio duration.
  - Fix: Try disabling VAD (`--no-vad`), use a different whisper model (`--whisper-model medium`), or try the whisper.cpp backend.
  - Threshold: 10 words/min (constant: `VALIDATION_MIN_WORDS_PER_MINUTE`).

- **sliding_window_repetition**: Whisper hallucination loop detected.
  - Cause: Whisper gets stuck repeating the same phrase in a loop, a known failure mode.
  - Fix: Try a smaller model, add initial prompt context, or try the whisper.cpp backend.
  - Threshold: 60% repetition ratio in a 50-segment sliding window.

### WARNING Failures (pipeline continues)

- **enriched_markdown_repetition**: "Markdown repetition: one paragraph repeated Nx (threshold 5x)"
  - Cause: The LLM or source material has repeated paragraphs. This is often legitimate when the speaker cites the same verse multiple times.
  - Threshold: 5 repetitions (constant: `VALIDATION_MARKDOWN_REPEAT_THRESHOLD`).

- **unverified_refs_in_markdown**: "N verse reference(s) in markdown not in verified set"
  - Cause: The LLM added verse references that were not verified against vedabase.io.
  - These are flagged per the Siddhanta Fidelity Principle — no unverified references are allowed in the final output.

- **verification_rate**: Low percentage of identified references were successfully verified.
  - Threshold: 50% (constant: `VALIDATION_MIN_VERIFICATION_RATE`).

- **metadata_duration_consistency**: "Duration mismatch: last segment ends at Xs but reported duration is Ys"
  - Cause: Transcription did not cover the full audio. Often related to the content_density issue.
  - Threshold: 10% mismatch.

- **enriched_markdown_sections**: "Enriched markdown has only N section(s) (minimum 5)"
  - Cause: The LLM produced too few section headings for the enriched notes.
  - Threshold: 5 sections (constant: `VALIDATION_MARKDOWN_MIN_SECTIONS`).

- **llm_speculative_content**: Speculative phrases detected in LLM output.
  - Phrases such as "it is likely that", "this probably means", "perhaps this refers to", etc.
  - Threshold: 3 occurrences (constant: `VALIDATION_MAX_SPECULATIVE_PHRASES`).

---

## LLM Issues

- **ANTHROPIC_API_KEY not set**: The enrichment agent requires an Anthropic API key. Add it to your `.env` file in the project root:
  ```
  ANTHROPIC_API_KEY=sk-ant-...
  ```

- **Rate limits**: The pipeline processes URLs sequentially, so it rarely hits rate limits. If you encounter rate limit errors, wait a few minutes and retry.

- **LLM truncation**: For transcripts longer than 15,000 characters, the LLM only processes a portion. The full transcript is preserved in the pipeline state; individual segments are cleaned by the LLM up to the character limit.

---

## Vedabase.io Issues

- **Connection timeout**: The pipeline retries failed vedabase.io requests 3 times with exponential backoff (2s, 4s, 8s delays).

- **Cache location**: Fetched verses are cached at `cache/vedabase_cache.json`. Delete this file to force a fresh re-fetch from vedabase.io.

- **Verse not found**: Some verses may not exist on vedabase.io. These are flagged as `[UNVERIFIED]` and excluded from the final output per the Siddhanta Fidelity Principle.

---

## Memory Issues

- **Large Whisper models**: The `large-v3` model requires approximately 3GB of RAM. If you are running low on memory, try `medium` or `small` models instead:
  ```bash
  python run_pipeline.py "url" --whisper-model medium
  ```

- **Long audio files**: Files longer than 2 hours may need chunked processing. The enrichment agent handles chunking automatically.

- **Max audio limits**: The pipeline enforces a hard limit of 500MB file size and 5 hours duration. Files exceeding these limits are rejected at download time.

---

## Output Issues

- **Empty output**: Check the pipeline logs for validation failures. Ensure the LLM is enabled for enrichment (`--llm` flag). Without it, the enrichment agent runs in deterministic mode, which produces minimal output.

- **Missing PDF**: PDF generation requires the PDF extras and an explicit flag:
  ```bash
  pip install -e ".[pdf]"
  python run_pipeline.py "url" --pdf
  ```

- **Checkpoint corruption**: If the pipeline fails mid-run and subsequent retries produce errors about corrupt state, delete the `checkpoints/` subdirectory inside the run folder and re-run from scratch.

---

## Retrying Failed Jobs

You can resume a failed pipeline run from a specific agent instead of starting over:

- **Via CLI**:
  ```bash
  python run_pipeline.py URL --from-agent 2
  ```
  Agent numbers: 1=Download, 2=Transcribe, 3=Enrich, 4=Compile, 5=PDF

- **Via API**:
  ```
  POST /api/v1/jobs/{job_id}/retry
  ```

This is useful when, for example, transcription succeeded but enrichment failed due to a network issue — you can resume from agent 3 without re-downloading and re-transcribing.
