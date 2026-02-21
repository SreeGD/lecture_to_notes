# Lecture-to-Notes Pipeline -- REST API Reference

**Base URL:** `http://localhost:8000/api/v1`

**Authentication:** None required.

**Interactive docs:**

| Format  | URL                            |
|---------|--------------------------------|
| Swagger | `http://localhost:8000/docs`   |
| ReDoc   | `http://localhost:8000/redoc`  |

---

## Table of Contents

- [Health Check](#health-check)
- [Jobs](#jobs)
  - [Create a Job](#create-a-job)
  - [List Jobs](#list-jobs)
  - [Get Job Details](#get-job-details)
  - [Cancel a Job](#cancel-a-job)
  - [Retry a Failed Job](#retry-a-failed-job)
  - [Get Job Output](#get-job-output)
  - [Download Output File](#download-output-file)
- [Browse ISKCON Desire Tree](#browse-iskcon-desire-tree)
  - [Browse Library](#browse-library)
  - [Search Library](#search-library)
  - [Topic Taxonomy](#topic-taxonomy)
- [Enumerations and Constants](#enumerations-and-constants)
- [Error Handling](#error-handling)
- [Polling Pattern](#polling-pattern)

---

## Health Check

Check whether the API server is running and how many jobs are currently active.

### `GET /health`

**Response:** `200 OK`

```json
{
  "status": "ok",
  "version": "0.1.0",
  "active_jobs": 2
}
```

**Response Schema -- `HealthResponse`**

| Field         | Type   | Description                                |
|---------------|--------|--------------------------------------------|
| `status`      | string | Always `"ok"` when the server is healthy.  |
| `version`     | string | API version string.                        |
| `active_jobs` | int    | Number of jobs in `queued` or `running` state. |

**Example:**

```bash
curl http://localhost:8000/api/v1/health
```

---

## Jobs

### Create a Job

Submit one or more URLs for processing through the lecture-to-notes pipeline.

### `POST /jobs`

**Request Body -- `JobCreateRequest`**

| Field                | Type           | Required | Default            | Description |
|----------------------|----------------|----------|--------------------|-------------|
| `urls`               | list[string]   | Yes      | --                 | One or more audio/video URLs to process. Minimum 1. |
| `title`              | string         | No       | `"Lecture Notes"`  | Title for the compiled book output. |
| `speaker`            | string or null | No       | `null`             | Speaker name, used in metadata and headers. |
| `whisper_model`      | string         | No       | `"large-v3"`       | Whisper model size. Common values: `"tiny"`, `"base"`, `"small"`, `"medium"`, `"large-v3"`. |
| `enable_diarization` | bool           | No       | `false`            | Enable speaker diarization via pyannote.audio. Requires the `[diarize]` extra. |
| `enable_llm`         | bool           | No       | `true`             | Enable LLM-based enrichment (verse identification, glossary generation). |
| `generate_pdf`       | bool           | No       | `false`            | Generate a PDF alongside the Markdown output. |
| `vad_filter`         | bool           | No       | `true`             | Enable Voice Activity Detection filtering during transcription. |
| `whisper_backend`    | string         | No       | `"faster-whisper"` | Transcription backend. One of `"faster-whisper"` or `"whisper.cpp"`. |
| `prompt`             | string or null | No       | `null`             | Custom instructions passed to the LLM during enrichment. |
| `enrichment_mode`    | string         | No       | `"auto"`           | Enrichment strategy. One of `"auto"`, `"verse-centric"`, `"lecture-centric"`. |
| `output_dir`         | string         | No       | `"output"`         | Directory where output files are written. |

**Response:** `202 Accepted`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "queued",
  "message": "Job created with 2 URL(s)"
}
```

**Response Schema -- `JobCreateResponse`**

| Field     | Type   | Description                          |
|-----------|--------|--------------------------------------|
| `job_id`  | string | Unique identifier for the new job.   |
| `status`  | string | Initial status, always `"queued"`.   |
| `message` | string | Human-readable confirmation message. |

**Example -- single URL:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://youtube.com/watch?v=EXAMPLE"],
    "title": "Bhagavad-gita Chapter 2 Lecture",
    "speaker": "HH Radhanath Swami"
  }'
```

**Example -- multiple URLs with full options:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "urls": [
      "https://youtube.com/watch?v=EXAMPLE1",
      "https://youtube.com/watch?v=EXAMPLE2",
      "https://youtube.com/watch?v=EXAMPLE3"
    ],
    "title": "SB Canto 1 Series",
    "speaker": "HG Chaitanya Charan Prabhu",
    "whisper_model": "large-v3",
    "enable_diarization": true,
    "enable_llm": true,
    "generate_pdf": true,
    "enrichment_mode": "verse-centric",
    "output_dir": "output/sb-series"
  }'
```

---

### List Jobs

Retrieve a summary of all jobs.

### `GET /jobs`

**Response:** `200 OK`

```json
[
  {
    "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "status": "completed",
    "current_step": "completed",
    "step_detail": "All 2 URLs processed successfully",
    "title": "Bhagavad-gita Chapter 2 Lecture",
    "url_count": 2,
    "created_at": "2026-02-21T10:30:00Z",
    "completed_at": "2026-02-21T10:45:12Z",
    "elapsed_seconds": 912,
    "error": null
  },
  {
    "job_id": "f9e8d7c6-b5a4-3210-fedc-ba0987654321",
    "status": "running",
    "current_step": "transcribing",
    "step_detail": "Transcribing URL 1/3",
    "title": "SB Canto 1 Series",
    "url_count": 3,
    "created_at": "2026-02-21T11:00:00Z",
    "completed_at": null,
    "elapsed_seconds": 120,
    "error": null
  }
]
```

**Response Schema -- `list[JobSummary]`**

| Field             | Type           | Description                                          |
|-------------------|----------------|------------------------------------------------------|
| `job_id`          | string         | Unique job identifier.                               |
| `status`          | string         | Current job status. See [Job Statuses](#job-statuses). |
| `current_step`    | string         | Current pipeline step. See [Pipeline Steps](#pipeline-steps). |
| `step_detail`     | string         | Human-readable description of current activity.      |
| `title`           | string         | Book title for this job.                             |
| `url_count`       | int            | Number of URLs in this job.                          |
| `created_at`      | string (ISO 8601) | Timestamp when the job was created.              |
| `completed_at`    | string or null | Timestamp when the job finished, or `null` if still active. |
| `elapsed_seconds` | number         | Wall-clock seconds since job creation.               |
| `error`           | string or null | Error message if the job failed, otherwise `null`.   |

**Example:**

```bash
curl http://localhost:8000/api/v1/jobs
```

---

### Get Job Details

Retrieve full details for a single job, including per-URL progress, configuration, and output file paths.

### `GET /jobs/{job_id}`

**Path Parameters:**

| Parameter | Type   | Description              |
|-----------|--------|--------------------------|
| `job_id`  | string | The unique job identifier. |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "running",
  "current_step": "enriching",
  "step_detail": "Verifying scripture references for URL 1/2",
  "title": "Bhagavad-gita Chapter 2 Lecture",
  "url_count": 2,
  "created_at": "2026-02-21T10:30:00Z",
  "started_at": "2026-02-21T10:30:01Z",
  "completed_at": null,
  "elapsed_seconds": 300,
  "error": null,
  "urls": [
    "https://youtube.com/watch?v=EXAMPLE1",
    "https://youtube.com/watch?v=EXAMPLE2"
  ],
  "url_progress": [
    {
      "url": "https://youtube.com/watch?v=EXAMPLE1",
      "step": "enriching",
      "detail": "Verifying verse references against vedabase.io"
    },
    {
      "url": "https://youtube.com/watch?v=EXAMPLE2",
      "step": "pending",
      "detail": "Waiting"
    }
  ],
  "progress_log": [
    "10:30:01 - Started downloading URL 1/2",
    "10:31:15 - Download complete for URL 1/2",
    "10:31:16 - Started transcription for URL 1/2",
    "10:34:45 - Transcription complete for URL 1/2",
    "10:34:46 - Started enrichment for URL 1/2"
  ],
  "output_dir": "output",
  "output_files": [],
  "config": {
    "whisper_model": "large-v3",
    "enable_diarization": false,
    "enable_llm": true,
    "generate_pdf": false,
    "vad_filter": true,
    "whisper_backend": "faster-whisper",
    "enrichment_mode": "auto"
  }
}
```

**Response Schema -- `JobDetail`**

Includes all fields from `JobSummary`, plus:

| Field           | Type              | Description                                          |
|-----------------|-------------------|------------------------------------------------------|
| `urls`          | list[string]      | All URLs submitted in this job.                      |
| `url_progress`  | list[object]      | Per-URL progress. Each entry has `url`, `step`, and `detail`. |
| `progress_log`  | list[string]      | Chronological log of pipeline events.                |
| `started_at`    | string or null    | Timestamp when processing began.                     |
| `output_dir`    | string            | Directory where output files are written.            |
| `output_files`  | list[string]      | Filenames of generated outputs (populated on completion). |
| `config`        | object            | The configuration used for this job.                 |

**Errors:**

| Status | Condition                                   |
|--------|---------------------------------------------|
| 404    | No job exists with the given `job_id`.      |

**Example:**

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

---

### Cancel a Job

Cancel a job that is currently queued or running.

### `POST /jobs/{job_id}/cancel`

**Path Parameters:**

| Parameter | Type   | Description              |
|-----------|--------|--------------------------|
| `job_id`  | string | The unique job identifier. |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "message": "Job cancelled"
}
```

**Errors:**

| Status | Condition                                                     |
|--------|---------------------------------------------------------------|
| 404    | No job exists with the given `job_id`.                        |
| 409    | Job is not in `queued` or `running` state (already completed, failed, or cancelled). |

**Example:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/cancel
```

---

### Retry a Failed Job

Retry a job that has failed. Creates a new job that reuses checkpoints from the failed run. You can optionally specify which agent to resume from; if omitted, the server auto-detects the appropriate resume point.

### `POST /jobs/{job_id}/retry`

**Path Parameters:**

| Parameter | Type   | Description              |
|-----------|--------|--------------------------|
| `job_id`  | string | The unique job identifier. |

**Request Body (optional) -- `JobRetryRequest`**

| Field        | Type        | Required | Default | Description                                     |
|--------------|-------------|----------|---------|-------------------------------------------------|
| `from_agent` | int or null | No       | `null`  | Agent number to resume from (1-5). `null` for auto-detection. |

Agent numbers:

| Number | Agent        |
|--------|-------------|
| 1      | Downloader   |
| 2      | Transcriber  |
| 3      | Enrichment   |
| 4      | Compiler     |
| 5      | PDF Generator|

**Response:** `202 Accepted`

```json
{
  "job_id": "new-job-id-created-for-retry",
  "status": "queued",
  "message": "Retry job created from agent 3"
}
```

**Errors:**

| Status | Condition                                             |
|--------|-------------------------------------------------------|
| 404    | No job exists with the given `job_id`.                |
| 409    | Job is not in `failed` state (cannot retry a running or completed job). |

**Example -- auto-detect resume point:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/retry
```

**Example -- resume from enrichment agent:**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/retry \
  -H "Content-Type: application/json" \
  -d '{"from_agent": 3}'
```

---

### Get Job Output

Retrieve the structured output of a completed job, including the full book content and optional PDF metadata.

### `GET /jobs/{job_id}/output`

**Path Parameters:**

| Parameter | Type   | Description              |
|-----------|--------|--------------------------|
| `job_id`  | string | The unique job identifier. |

**Response:** `200 OK`

```json
{
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "book": {
    "title": "Bhagavad-gita Chapter 2 Lecture",
    "chapters": [
      {
        "title": "Chapter 2 -- Contents of the Gita Summarized",
        "sections": ["..."]
      }
    ],
    "glossary": [
      {
        "term": "dharma",
        "definition": "Religious duty; righteousness; the inherent nature of a thing."
      }
    ],
    "references": [
      {
        "ref": "BG 2.13",
        "url": "https://vedabase.io/en/library/bg/2/13/",
        "verified": true
      }
    ]
  },
  "pdf": {
    "filename": "Bhagavad-gita_Chapter_2_Lecture.pdf",
    "size_bytes": 245760
  }
}
```

**Response Schema -- `JobOutputResponse`**

| Field  | Type        | Description                                                 |
|--------|-------------|-------------------------------------------------------------|
| `job_id` | string    | The job identifier.                                         |
| `book` | object      | Full structured book output (chapters, glossary, references, indices). |
| `pdf`  | object or null | PDF file metadata if `generate_pdf` was enabled, otherwise `null`. |

**Errors:**

| Status | Condition                                        |
|--------|--------------------------------------------------|
| 404    | No job exists with the given `job_id`.           |
| 409    | Job is not in `completed` state.                 |

**Example:**

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/output
```

---

### Download Output File

Download a generated output file (Markdown or PDF) directly.

### `GET /jobs/{job_id}/files/{filename}`

**Path Parameters:**

| Parameter  | Type   | Description                               |
|------------|--------|-------------------------------------------|
| `job_id`   | string | The unique job identifier.                |
| `filename` | string | Name of the file to download (e.g., `notes.md`, `notes.pdf`). |

**Response:** `200 OK` with the file content as a binary download.

The `Content-Type` header is set according to the file extension (e.g., `text/markdown` for `.md`, `application/pdf` for `.pdf`). The `Content-Disposition` header is set to trigger a file download.

**Security:** Path traversal is blocked. The filename must refer to a file within the job's output directory. Attempts to use `..` or absolute paths will be rejected.

**Errors:**

| Status | Condition                                        |
|--------|--------------------------------------------------|
| 404    | Job not found, or file does not exist.           |
| 409    | Job is not in `completed` state.                 |

**Example:**

```bash
# Download Markdown
curl -O http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/files/Bhagavad-gita_Chapter_2_Lecture.md

# Download PDF
curl -O http://localhost:8000/api/v1/jobs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/files/Bhagavad-gita_Chapter_2_Lecture.pdf
```

---

## Browse ISKCON Desire Tree

These endpoints provide access to the ISKCON Desire Tree (iskcondesiretree.com) audio library. Responses are cached for 5 minutes.

### Browse Library

Browse the ISKCON Desire Tree audio library directory structure.

### `GET /browse`

**Query Parameters:**

| Parameter | Type   | Required | Default | Description                          |
|-----------|--------|----------|---------|--------------------------------------|
| `path`    | string | No       | `"/"`   | Path within the library to browse.   |

**Response:** `200 OK`

```json
{
  "path": "/",
  "parent": null,
  "entries": [
    {
      "name": "HH Radhanath Swami",
      "href": "/HH%20Radhanath%20Swami/",
      "is_dir": true,
      "size": null,
      "modified": null
    },
    {
      "name": "HG Chaitanya Charan Prabhu",
      "href": "/HG%20Chaitanya%20Charan%20Prabhu/",
      "is_dir": true,
      "size": null,
      "modified": null
    }
  ]
}
```

**Response Schema -- `BrowseResponse`**

| Field     | Type           | Description                                       |
|-----------|----------------|---------------------------------------------------|
| `path`    | string         | The current browsed path.                         |
| `parent`  | string or null | Parent path for navigation, or `null` at root.    |
| `entries` | list[BrowseEntry] | Directory and file entries at this path.       |

**`BrowseEntry` Schema:**

| Field      | Type           | Description                                    |
|------------|----------------|------------------------------------------------|
| `name`     | string         | Display name of the entry.                     |
| `href`     | string         | Relative path/URL for this entry.              |
| `is_dir`   | bool           | `true` for directories, `false` for files.     |
| `size`     | int or null    | File size in bytes, or `null` for directories. |
| `modified` | string or null | Last modified timestamp, or `null` if unknown. |

**Errors:**

| Status | Condition                                            |
|--------|------------------------------------------------------|
| 502    | Failed to fetch data from ISKCON Desire Tree upstream server. |

**Example:**

```bash
# Browse root
curl "http://localhost:8000/api/v1/browse?path=/"

# Browse a speaker's directory
curl "http://localhost:8000/api/v1/browse?path=/HH%20Radhanath%20Swami/"
```

---

### Search Library

Search the ISKCON Desire Tree audio library by title. Results are grouped by speaker.

### `GET /browse/search`

**Query Parameters:**

| Parameter | Type   | Required | Description                        |
|-----------|--------|----------|------------------------------------|
| `q`       | string | Yes      | Search query string.               |

**Response:** `200 OK`

```json
{
  "query": "Bhagavad-gita Chapter 2",
  "total": 5,
  "groups": [
    {
      "group_title": "HH Radhanath Swami",
      "entries": [
        {
          "name": "BG 02.13 - The Soul is Eternal",
          "href": "/HH%20Radhanath%20Swami/BG_02_13.mp3",
          "is_dir": false,
          "size": 15728640,
          "modified": "2024-06-15T08:00:00Z"
        }
      ]
    },
    {
      "group_title": "HG Chaitanya Charan Prabhu",
      "entries": [
        {
          "name": "Gita Chapter 02 Overview",
          "href": "/HG%20Chaitanya%20Charan%20Prabhu/BG_Ch02.mp3",
          "is_dir": false,
          "size": 20971520,
          "modified": "2024-03-10T12:00:00Z"
        }
      ]
    }
  ]
}
```

**Response Schema -- `SearchResponse`**

| Field    | Type              | Description                                    |
|----------|-------------------|------------------------------------------------|
| `query`  | string            | The search query that was executed.            |
| `total`  | int               | Total number of matching entries across all groups. |
| `groups` | list[SearchGroup] | Results grouped by speaker or category.        |

**`SearchGroup` Schema:**

| Field         | Type              | Description                               |
|---------------|-------------------|-------------------------------------------|
| `group_title` | string            | Name of the group (typically the speaker). |
| `entries`     | list[BrowseEntry] | Matching entries within this group.        |

**Errors:**

| Status | Condition                                            |
|--------|------------------------------------------------------|
| 502    | Failed to fetch data from ISKCON Desire Tree upstream server. |

**Example:**

```bash
curl "http://localhost:8000/api/v1/browse/search?q=Bhagavad-gita%20Chapter%202"
```

---

### Topic Taxonomy

Returns a structured taxonomy of topics, organized by category. Useful for building filters and navigation in a frontend.

### `GET /browse/topics`

**Response:** `200 OK`

```json
{
  "categories": [
    {
      "category": "scriptures",
      "label": "Scriptures",
      "topics": [
        "Bhagavad-gita",
        "Srimad Bhagavatam",
        "Chaitanya Charitamrita",
        "Nectar of Instruction",
        "Isopanisad"
      ]
    },
    {
      "category": "festivals",
      "label": "Festivals",
      "topics": [
        "Janmashtami",
        "Gaura Purnima",
        "Ratha Yatra",
        "Kartik"
      ]
    },
    {
      "category": "themes",
      "label": "Themes",
      "topics": [
        "Devotional Service",
        "Holy Name",
        "Guru Tattva",
        "Varnashrama"
      ]
    },
    {
      "category": "practices",
      "label": "Practices",
      "topics": [
        "Japa",
        "Kirtan",
        "Deity Worship",
        "Book Distribution"
      ]
    }
  ]
}
```

**Response Schema -- `TopicTaxonomyResponse`**

| Field        | Type                | Description                         |
|--------------|---------------------|-------------------------------------|
| `categories` | list[TopicCategory] | List of topic categories.           |

**`TopicCategory` Schema:**

| Field      | Type         | Description                                    |
|------------|--------------|------------------------------------------------|
| `category` | string       | Machine-readable category key.                 |
| `label`    | string       | Human-readable display label.                  |
| `topics`   | list[string] | List of topic names within this category.      |

**Example:**

```bash
curl http://localhost:8000/api/v1/browse/topics
```

---

## Enumerations and Constants

### Job Statuses

| Status      | Description                                    |
|-------------|------------------------------------------------|
| `queued`    | Job is waiting to be picked up by a worker.    |
| `running`   | Job is actively being processed.               |
| `completed` | Job finished successfully. Outputs are available. |
| `failed`    | Job encountered an error and stopped.          |

### Pipeline Steps

| Step              | Description                                      |
|-------------------|--------------------------------------------------|
| `pending`         | URL has not started processing.                  |
| `downloading`     | Agent 1 is downloading and normalizing audio.    |
| `transcribing`    | Agent 2 is running speech-to-text transcription. |
| `enriching`       | Agent 3 is identifying and verifying scripture references. |
| `validating`      | Verifying enrichment output against vedabase.io. |
| `compiling`       | Agent 4 is assembling the structured Markdown book. |
| `pdf_generating`  | Converting Markdown output to PDF.               |
| `completed`       | Processing finished successfully for this URL.   |
| `failed`          | Processing failed for this URL.                  |

### Enrichment Modes

| Mode              | Description                                              |
|-------------------|----------------------------------------------------------|
| `auto`            | Automatically selects the best strategy based on content. |
| `verse-centric`   | Prioritizes identifying and annotating scripture verses. |
| `lecture-centric` | Prioritizes narrative flow and thematic structure.       |

### Whisper Backends

| Backend          | Description                                     |
|------------------|-------------------------------------------------|
| `faster-whisper` | CTranslate2-based backend. Default and recommended. |
| `whisper.cpp`    | C++ implementation of Whisper.                  |

---

## Error Handling

All error responses follow a consistent JSON structure:

```json
{
  "detail": "Human-readable error description"
}
```

### HTTP Status Codes

| Status | Meaning                 | When It Occurs                                            |
|--------|-------------------------|-----------------------------------------------------------|
| 200    | OK                      | Successful retrieval or action.                           |
| 202    | Accepted                | Job created or retry initiated; processing is asynchronous. |
| 404    | Not Found               | The specified `job_id` does not exist, or the requested file was not found. |
| 409    | Conflict                | Action is not valid for the current job state. For example: cancelling a completed job, retrying a running job, or fetching output from an incomplete job. |
| 422    | Unprocessable Entity    | Request body validation failed (missing required fields, invalid types). |
| 502    | Bad Gateway             | The upstream ISKCON Desire Tree server returned an error or is unreachable. |

### Common Error Scenarios

**Job not found (404):**

```bash
curl http://localhost:8000/api/v1/jobs/nonexistent-id
```

```json
{
  "detail": "Job not found: nonexistent-id"
}
```

**Cancel a completed job (409):**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/a1b2c3d4/cancel
```

```json
{
  "detail": "Cannot cancel job in 'completed' state. Only 'queued' or 'running' jobs can be cancelled."
}
```

**Retry a running job (409):**

```bash
curl -X POST http://localhost:8000/api/v1/jobs/a1b2c3d4/retry
```

```json
{
  "detail": "Cannot retry job in 'running' state. Only 'failed' jobs can be retried."
}
```

**Fetch output from a running job (409):**

```bash
curl http://localhost:8000/api/v1/jobs/a1b2c3d4/output
```

```json
{
  "detail": "Job is not completed. Current status: running"
}
```

**ISKCON Desire Tree upstream error (502):**

```bash
curl "http://localhost:8000/api/v1/browse?path=/invalid-path"
```

```json
{
  "detail": "Failed to fetch from ISKCON Desire Tree: upstream returned 503"
}
```

---

## Polling Pattern

Jobs are processed asynchronously. After creating a job, poll the job detail endpoint to monitor progress.

### Recommended Approach

1. Create the job and capture the `job_id`.
2. Poll `GET /jobs/{job_id}` at regular intervals.
3. Check the `status` field: continue polling while `queued` or `running`.
4. On `completed`, fetch the output or download files.
5. On `failed`, inspect the `error` field and optionally retry.

### Polling Interval Guidance

| Phase              | Recommended Interval | Rationale                                    |
|--------------------|----------------------|----------------------------------------------|
| First 30 seconds   | 2 seconds            | Quick feedback during download phase.        |
| 30 seconds -- 5 min | 5 seconds           | Transcription is underway.                   |
| After 5 minutes    | 10 seconds           | Long-running enrichment and compilation.     |

### Shell Script Example

```bash
#!/bin/bash
# submit-and-wait.sh -- Submit a job and poll until completion.

BASE_URL="http://localhost:8000/api/v1"

# Step 1: Create the job
RESPONSE=$(curl -s -X POST "$BASE_URL/jobs" \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://youtube.com/watch?v=EXAMPLE"],
    "title": "BG 2.13 Lecture",
    "generate_pdf": true
  }')

JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "Job created: $JOB_ID"

# Step 2: Poll until terminal state
while true; do
  STATUS_RESPONSE=$(curl -s "$BASE_URL/jobs/$JOB_ID")
  STATUS=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['status'])")
  STEP=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['current_step'])")
  DETAIL=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['step_detail'])")

  echo "[$STATUS] $STEP -- $DETAIL"

  if [ "$STATUS" = "completed" ]; then
    echo "Job completed successfully."
    break
  elif [ "$STATUS" = "failed" ]; then
    ERROR=$(echo "$STATUS_RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['error'])")
    echo "Job failed: $ERROR"
    exit 1
  fi

  sleep 5
done

# Step 3: Retrieve and display output file list
OUTPUT=$(curl -s "$BASE_URL/jobs/$JOB_ID")
echo "$OUTPUT" | python3 -c "
import sys, json
data = json.load(sys.stdin)
print('Output files:')
for f in data.get('output_files', []):
    print(f'  - {f}')
"

# Step 4: Download the Markdown file
FIRST_FILE=$(echo "$OUTPUT" | python3 -c "import sys,json; print(json.load(sys.stdin)['output_files'][0])")
curl -O "$BASE_URL/jobs/$JOB_ID/files/$FIRST_FILE"
echo "Downloaded: $FIRST_FILE"
```

### Python Example

```python
import time
import httpx

BASE_URL = "http://localhost:8000/api/v1"

# Step 1: Create the job
response = httpx.post(f"{BASE_URL}/jobs", json={
    "urls": ["https://youtube.com/watch?v=EXAMPLE"],
    "title": "BG 2.13 Lecture",
    "generate_pdf": True,
})
response.raise_for_status()
job_id = response.json()["job_id"]
print(f"Job created: {job_id}")

# Step 2: Poll until terminal state
while True:
    detail = httpx.get(f"{BASE_URL}/jobs/{job_id}").json()
    status = detail["status"]
    print(f"[{status}] {detail['current_step']} -- {detail['step_detail']}")

    if status == "completed":
        print("Job completed successfully.")
        break
    elif status == "failed":
        print(f"Job failed: {detail['error']}")
        # Optionally retry
        retry = httpx.post(f"{BASE_URL}/jobs/{job_id}/retry")
        if retry.status_code == 202:
            job_id = retry.json()["job_id"]
            print(f"Retry job created: {job_id}")
            continue
        else:
            raise SystemExit(1)

    time.sleep(5)

# Step 3: Download output
output = httpx.get(f"{BASE_URL}/jobs/{job_id}/output").json()
for filename in detail.get("output_files", []):
    resp = httpx.get(f"{BASE_URL}/jobs/{job_id}/files/{filename}")
    with open(filename, "wb") as f:
        f.write(resp.content)
    print(f"Downloaded: {filename}")
```
