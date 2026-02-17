# Contributing

Thank you for your interest in contributing to the Lecture-to-Notes Pipeline.

## Getting Started

1. Fork and clone the repository
2. Install dependencies:
   ```bash
   pip install -e ".[llm,pdf]"
   brew install ffmpeg
   ```
3. Copy `.env.example` to `.env` and add your `ANTHROPIC_API_KEY` (needed for LLM tests)
4. Run the tests to verify your setup:
   ```bash
   pytest -m schema    # Fast, no external deps — start here
   pytest -m tool      # Tool function tests (may use mocks)
   pytest -m pipeline  # Deterministic pipeline tests
   ```

## Development Workflow

1. Create a branch from `main` for your work
2. Make your changes
3. Run the relevant tests (see below)
4. Submit a pull request

## Architecture Overview

The pipeline has 4 agents (plus an optional 5th for PDF) that run sequentially. Each agent has:
- A **deterministic path** (`run_*_pipeline()`) — no LLM, used by tests
- An **agentic path** (`build_*_agent()` + `build_*_task()`) — CrewAI + LLM

Each tool follows a consistent pattern — a pure function plus a `BaseTool` wrapper:

```python
def download_with_ytdlp(url: str, output_dir: str) -> dict: ...
class YtDlpDownloadTool(BaseTool): ...
```

All inter-agent data flows through validated Pydantic schemas defined in `src/lecture_agents/schemas/`.

## Testing

### Test markers

| Marker        | What it tests                              | Requires           |
|---------------|--------------------------------------------|---------------------|
| `schema`      | Pydantic schema validation                 | Nothing             |
| `tool`        | Individual tool functions                  | May use mocks       |
| `pipeline`    | Deterministic agent pipelines              | ffmpeg              |
| `llm`         | LLM-dependent code paths                   | `ANTHROPIC_API_KEY` |
| `integration` | Full cross-agent flows                     | ffmpeg, network     |
| `slow`        | Audio download and transcription           | ffmpeg, network     |

### Running tests

```bash
# Quick validation (no network, no LLM)
pytest -m schema -v

# All fast tests
pytest -m "not slow and not llm"

# Everything
pytest
```

### Writing tests

- Add tests in `tests/unit/` for new tools or schema changes
- Use `@pytest.mark.<marker>` to categorize your test
- Use mocks for external services (vedabase.io, YouTube, LLM APIs)
- Schema tests should construct Pydantic models and assert field values — no I/O

## Code Guidelines

### Schemas

All data between agents is passed as Pydantic models. If you change agent inputs/outputs, update the corresponding schema in `src/lecture_agents/schemas/` and add schema tests.

### Tools

- Keep pure functions separate from `BaseTool` wrappers
- Tools should be stateless — all state lives in the pipeline schemas
- Add type hints to function signatures

### Vedabase verification

This is the most important rule in the project: **all scripture references must be verified against vedabase.io**. Never hardcode verses, translations, or purports. Never generate philosophical content from LLM training data alone. If a verse can't be verified, flag it as `[UNVERIFIED]`.

Supported vedabase.io URL patterns:

| Scripture | URL pattern |
|-----------|-------------|
| Bhagavad-gita | `vedabase.io/en/library/bg/{chapter}/{verse}/` |
| Srimad-Bhagavatam | `vedabase.io/en/library/sb/{canto}/{chapter}/{verse}/` |
| Caitanya-caritamrta | `vedabase.io/en/library/cc/{division}/{chapter}/{verse}/` |
| Nectar of Instruction | `vedabase.io/en/library/noi/{verse}/` |
| Sri Isopanisad | `vedabase.io/en/library/iso/{verse}/` |

### Commit messages

- Use imperative mood ("Add feature" not "Added feature")
- Keep the subject line under 72 characters
- Explain *why* in the body when the change isn't obvious

## Areas for Contribution

- **Language support** — improving transcription accuracy for Sanskrit, Bengali, and Hindi terms
- **Additional scripture sources** — extending vedabase verification to other texts
- **Output formats** — EPUB, DOCX, or other export targets
- **Test coverage** — especially integration and pipeline tests
- **Documentation** — usage examples, tutorials, and guides

## Questions?

Open an issue if you have questions or want to discuss a contribution before starting work.
