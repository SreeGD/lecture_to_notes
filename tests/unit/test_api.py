"""
API endpoint tests with mocked pipeline.
"""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from lecture_agents.api.app import create_app
from lecture_agents.api.job_manager import JobManager, JobRecord
from lecture_agents.api.models import JobStatus, PipelineStep
from lecture_agents.schemas.compiler_output import (
    BookOutput,
    Chapter,
    CompilationReport,
)
from lecture_agents.schemas.pdf_output import PDFOutput


def _mock_book(output_dir: str) -> BookOutput:
    return BookOutput(
        title="Test Book",
        chapters=[
            Chapter(
                number=1,
                title="Karma Yoga Discussion",
                content_markdown="# Chapter 1: Karma Yoga\n\nContent about duty.",
            )
        ],
        front_matter_markdown="# Test Book\n\nFront matter.",
        full_book_markdown=(
            "# Test Book\n\nFront matter.\n\n"
            "# Chapter 1\n\nContent about duty.\n\n---\nBack matter."
        ),
        report=CompilationReport(total_chapters=1, total_words=50),
        output_path=f"{output_dir}/Test_Book.md",
        summary="Compiled 1 chapter.",
    )


def _mock_pdf(output_dir: str) -> PDFOutput:
    return PDFOutput(
        pdf_path=f"{output_dir}/Test_Book.pdf",
        title="Test Book",
        total_pages=5,
        file_size_kb=120.0,
        summary="Generated 5-page PDF.",
    )


@pytest.fixture()
def app(tmp_path):
    """Create a fresh FastAPI app with its own JobManager for each test."""
    application = create_app()
    with patch(
        "lecture_agents.api.job_manager.PIPELINE_OUTPUT_DIR", str(tmp_path)
    ):
        application.state.job_manager = JobManager(max_workers=2)
    return application


@pytest.fixture()
def client(app):
    from starlette.testclient import TestClient

    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["active_jobs"] == 0


# ---------------------------------------------------------------------------
# Job creation
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestCreateJob:
    def test_create_job_returns_202(self, client):
        resp = client.post("/api/v1/jobs", json={
            "urls": ["https://example.com/lecture.mp3"],
        })
        assert resp.status_code == 202
        data = resp.json()
        assert "job_id" in data
        assert data["status"] == "queued"

    def test_create_job_requires_urls(self, client):
        resp = client.post("/api/v1/jobs", json={})
        assert resp.status_code == 422

    def test_create_job_rejects_empty_urls(self, client):
        resp = client.post("/api/v1/jobs", json={"urls": []})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Job listing
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestListJobs:
    def test_list_empty(self, client):
        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_create(self, client):
        client.post("/api/v1/jobs", json={"urls": ["https://example.com/a.mp3"]})
        resp = client.get("/api/v1/jobs")
        assert resp.status_code == 200
        jobs = resp.json()
        assert len(jobs) == 1
        assert jobs[0]["url_count"] == 1


# ---------------------------------------------------------------------------
# Job detail
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestGetJob:
    def test_get_nonexistent_returns_404(self, client):
        resp = client.get("/api/v1/jobs/nonexistent")
        assert resp.status_code == 404

    def test_get_created_job(self, client):
        create_resp = client.post("/api/v1/jobs", json={
            "urls": ["https://example.com/lecture.mp3"],
            "title": "My Lecture",
        })
        job_id = create_resp.json()["job_id"]
        resp = client.get(f"/api/v1/jobs/{job_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == job_id
        assert data["title"] == "My Lecture"
        assert len(data["urls"]) == 1


# ---------------------------------------------------------------------------
# Job output
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestGetJobOutput:
    def test_output_not_ready_returns_409(self, client, app):
        # Manually insert a running job
        jm = app.state.job_manager
        record = JobRecord(
            job_id="test123",
            urls=["https://example.com/a.mp3"],
            title="Test",
            config={},
            status=JobStatus.RUNNING,
            current_step=PipelineStep.TRANSCRIBING,
        )
        jm._jobs["test123"] = record

        resp = client.get("/api/v1/jobs/test123/output")
        assert resp.status_code == 409

    def test_output_returns_book_json(self, client, app, tmp_path):
        # Manually insert a completed job
        jm = app.state.job_manager
        book = _mock_book(str(tmp_path))
        record = JobRecord(
            job_id="done456",
            urls=["https://example.com/a.mp3"],
            title="Test Book",
            config={},
            status=JobStatus.COMPLETED,
            current_step=PipelineStep.COMPLETED,
            book_output=book,
        )
        jm._jobs["done456"] = record

        resp = client.get("/api/v1/jobs/done456/output")
        assert resp.status_code == 200
        data = resp.json()
        assert data["job_id"] == "done456"
        assert data["book"]["title"] == "Test Book"
        assert data["pdf"] is None


# ---------------------------------------------------------------------------
# File download
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestDownloadFile:
    def test_download_md_file(self, client, app, tmp_path):
        # Create a real file
        md_file = tmp_path / "Lecture.md"
        md_file.write_text("# Test Lecture")

        jm = app.state.job_manager
        record = JobRecord(
            job_id="file789",
            urls=["https://example.com/a.mp3"],
            title="Test",
            config={},
            status=JobStatus.COMPLETED,
            current_step=PipelineStep.COMPLETED,
            output_dir=str(tmp_path),
            output_files=["Lecture.md"],
            book_output=_mock_book(str(tmp_path)),
        )
        jm._jobs["file789"] = record

        resp = client.get("/api/v1/jobs/file789/files/Lecture.md")
        assert resp.status_code == 200
        assert "# Test Lecture" in resp.text

    def test_download_nonexistent_file_returns_404(self, client, app, tmp_path):
        jm = app.state.job_manager
        record = JobRecord(
            job_id="file000",
            urls=["https://example.com/a.mp3"],
            title="Test",
            config={},
            status=JobStatus.COMPLETED,
            current_step=PipelineStep.COMPLETED,
            output_dir=str(tmp_path),
            book_output=_mock_book(str(tmp_path)),
        )
        jm._jobs["file000"] = record

        resp = client.get("/api/v1/jobs/file000/files/nope.md")
        assert resp.status_code == 404

    def test_path_traversal_blocked(self, client, app, tmp_path):
        jm = app.state.job_manager
        record = JobRecord(
            job_id="traversal",
            urls=["https://example.com/a.mp3"],
            title="Test",
            config={},
            status=JobStatus.COMPLETED,
            current_step=PipelineStep.COMPLETED,
            output_dir=str(tmp_path),
            book_output=_mock_book(str(tmp_path)),
        )
        jm._jobs["traversal"] = record

        resp = client.get("/api/v1/jobs/traversal/files/../../etc/passwd")
        assert resp.status_code in (403, 404)

    def test_download_from_running_job_returns_409(self, client, app):
        jm = app.state.job_manager
        record = JobRecord(
            job_id="running1",
            urls=["https://example.com/a.mp3"],
            title="Test",
            config={},
            status=JobStatus.RUNNING,
            current_step=PipelineStep.DOWNLOADING,
        )
        jm._jobs["running1"] = record

        resp = client.get("/api/v1/jobs/running1/files/out.md")
        assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Full lifecycle (mocked pipeline)
# ---------------------------------------------------------------------------


@pytest.mark.api
class TestFullLifecycle:
    @patch("lecture_agents.orchestrator.run_single_url_pipeline")
    def test_submit_and_poll_to_completion(self, mock_pipeline, client, app, tmp_path):
        # Set up mock to return a completed book
        md_path = tmp_path / "Test_Book.md"
        md_path.write_text("# Test Book\n\nFull content.")

        book = _mock_book(str(tmp_path))
        book.output_path = str(md_path)
        mock_pipeline.return_value = (book, None)

        # Submit
        resp = client.post("/api/v1/jobs", json={
            "urls": ["https://example.com/lecture.mp3"],
            "title": "Test Book",
        })
        assert resp.status_code == 202
        job_id = resp.json()["job_id"]

        # Wait for background thread to finish
        for _ in range(50):
            detail = client.get(f"/api/v1/jobs/{job_id}").json()
            if detail["status"] == "completed":
                break
            time.sleep(0.1)
        else:
            pytest.fail("Job did not complete in time")

        assert detail["status"] == "completed"

        # Get output
        output_resp = client.get(f"/api/v1/jobs/{job_id}/output")
        assert output_resp.status_code == 200
        assert output_resp.json()["book"]["title"] == "Test Book"

        # Download file
        file_resp = client.get(f"/api/v1/jobs/{job_id}/files/Test_Book.md")
        assert file_resp.status_code == 200
        assert "# Test Book" in file_resp.text
