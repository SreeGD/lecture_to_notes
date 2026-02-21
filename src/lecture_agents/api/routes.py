"""
FastAPI route handlers for the Lecture-to-Notes Pipeline API.
"""

from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from lecture_agents.api.models import (
    BrowseEntry,
    BrowseResponse,
    HealthResponse,
    JobCreateRequest,
    JobCreateResponse,
    JobDetail,
    JobOutputResponse,
    JobRetryRequest,
    JobStatus,
    JobSummary,
    ProgressLogEntry,
    SearchEntry,
    SearchGroup,
    SearchResponse,
    TopicCategory,
    TopicEntry,
    TopicTaxonomyResponse,
    URLProgress,
)

logger = logging.getLogger(__name__)

ISKCON_BASE_URL = "https://audio.iskcondesiretree.com"
_browse_cache: dict[str, tuple[float, BrowseResponse]] = {}
_CACHE_TTL = 300  # 5 minutes

router = APIRouter()


def _elapsed(record) -> float | None:
    """Calculate elapsed seconds for a job."""
    if not record.started_at:
        return None
    end = record.completed_at or datetime.now()
    return (end - record.started_at).total_seconds()


@router.get("/health", response_model=HealthResponse)
async def health_check(request: Request):
    jm = request.app.state.job_manager
    active = sum(1 for j in jm.list_jobs() if j.status == JobStatus.RUNNING)
    return HealthResponse(active_jobs=active)


@router.post("/jobs", response_model=JobCreateResponse, status_code=202)
async def create_job(body: JobCreateRequest, request: Request):
    jm = request.app.state.job_manager
    record = jm.submit_job(body)
    return JobCreateResponse(
        job_id=record.job_id,
        status=JobStatus.QUEUED,
        message=f"Job {record.job_id} queued with {len(body.urls)} URL(s).",
    )


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(request: Request):
    jm = request.app.state.job_manager
    return [
        JobSummary(
            job_id=r.job_id,
            status=r.status,
            current_step=r.current_step,
            step_detail=r.step_detail,
            title=r.title,
            url_count=len(r.urls),
            created_at=r.created_at,
            completed_at=r.completed_at,
            elapsed_seconds=_elapsed(r),
            error=r.error,
        )
        for r in jm.list_jobs()
    ]


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, request: Request):
    jm = request.app.state.job_manager
    record = jm.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobDetail(
        job_id=record.job_id,
        status=record.status,
        current_step=record.current_step,
        step_detail=record.step_detail,
        title=record.title,
        urls=record.urls,
        url_progress=[URLProgress(**up) for up in record.url_progress],
        progress_log=[
            ProgressLogEntry(
                timestamp=e.timestamp,
                step=e.step,
                message=e.message,
            )
            for e in record.progress_log
        ],
        created_at=record.created_at,
        started_at=record.started_at,
        completed_at=record.completed_at,
        elapsed_seconds=_elapsed(record),
        error=record.error,
        output_dir=record.output_dir,
        output_files=record.output_files,
        config=record.config,
    )


@router.post("/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request):
    jm = request.app.state.job_manager
    record = jm.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if record.status not in (JobStatus.QUEUED, JobStatus.RUNNING):
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is {record.status.value}, cannot cancel",
        )
    jm.cancel_job(job_id)
    return {"job_id": job_id, "message": "Cancellation requested"}


@router.post("/jobs/{job_id}/retry", response_model=JobCreateResponse, status_code=202)
async def retry_job(job_id: str, request: Request, body: JobRetryRequest = None):
    """Retry a failed job, resuming from checkpoints."""
    jm = request.app.state.job_manager
    record = jm.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if record.status != JobStatus.FAILED:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is {record.status.value}, only failed jobs can be retried",
        )
    try:
        new_record = jm.retry_job(job_id, body)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    from_agent = new_record.config.get("from_agent", 1)
    agent_names = {1: "download", 2: "transcribe", 3: "enrich", 4: "compile", 5: "pdf"}
    return JobCreateResponse(
        job_id=new_record.job_id,
        status=JobStatus.QUEUED,
        message=f"Retrying from {agent_names.get(from_agent, 'agent ' + str(from_agent))} "
                f"(original job: {job_id}).",
    )


@router.get("/jobs/{job_id}/output", response_model=JobOutputResponse)
async def get_job_output(job_id: str, request: Request):
    jm = request.app.state.job_manager
    record = jm.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if record.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is {record.status.value}, not completed",
        )
    return JobOutputResponse(
        job_id=record.job_id,
        book=record.book_output.model_dump(),
        pdf=record.pdf_output.model_dump() if record.pdf_output else None,
    )


@router.get("/jobs/{job_id}/files/{filename}")
async def download_file(job_id: str, filename: str, request: Request):
    jm = request.app.state.job_manager
    record = jm.get_job(job_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if record.status != JobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail=f"Job {job_id} is {record.status.value}, not completed",
        )
    if not record.output_dir:
        raise HTTPException(status_code=404, detail="No output directory")

    file_path = Path(record.output_dir) / filename
    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"File {filename} not found")

    # Path traversal protection
    try:
        file_path.resolve().relative_to(Path(record.output_dir).resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")

    media_type = "application/pdf" if filename.endswith(".pdf") else "text/markdown"
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type=media_type,
    )


# ---------------------------------------------------------------------------
# ISKCON Desire Tree audio browser
# ---------------------------------------------------------------------------


def _parse_iskcon_page(html: str) -> list[BrowseEntry]:
    """Parse ISKCON Desire Tree Andromeda PHP page into BrowseEntry list.

    The site uses two link patterns:
    - Folders: <a href=index.php?q=f&f=%2Fpath><font size="2">Name</font></a>
    - MP3s: <a href="/path/to/file.mp3"><font size="2">Name</font></a>
    """
    entries: list[BrowseEntry] = []
    seen_hrefs: set[str] = set()

    # Pattern 1: Folder links — index.php?q=f&f=%2Fencoded_path
    for match in re.finditer(
        r'<a\s+href=index\.php\?q=f&f=([^>]+?)>'
        r'<font\s+size="2">([^<]+)</font></a>',
        html,
    ):
        encoded_path, name = match.groups()
        # URL-decode the path: %2F -> /
        folder_path = re.sub(r'%([0-9A-Fa-f]{2})', lambda m: chr(int(m.group(1), 16)), encoded_path)
        if folder_path in seen_hrefs:
            continue
        seen_hrefs.add(folder_path)

        # Extract folder count if present nearby
        size = None
        pos = match.end()
        size_match = re.search(r'<font\s+size="1">(\d+\s*(?:folders?|files?))</font>', html[pos:pos + 200])
        if size_match:
            size = size_match.group(1).replace("\xa0", " ")

        entries.append(BrowseEntry(
            name=name.strip(),
            href=folder_path,
            is_dir=True,
            size=size,
            modified=None,
        ))

    # Pattern 2: MP3 file links — href="/path/to/file.mp3"
    for match in re.finditer(
        r'<a\s+href="(/[^"]+\.mp3)"[^>]*>'
        r'<font\s+size="2">([^<]+)</font></a>',
        html,
    ):
        mp3_path, name = match.groups()
        if mp3_path in seen_hrefs:
            continue
        seen_hrefs.add(mp3_path)

        # Extract file size from nearby text
        size = None
        pos = match.end()
        size_match = re.search(
            r'<font\s+size="1"\s+color="aaaaaa">([\d.]+\s*(?:&nbsp;)?\s*[KMG]B)',
            html[pos:pos + 300],
        )
        if size_match:
            size = size_match.group(1).replace("&nbsp;", " ")

        entries.append(BrowseEntry(
            name=name.strip(),
            href=mp3_path,
            is_dir=False,
            size=size,
            modified=None,
        ))

    return entries


@router.get("/browse", response_model=BrowseResponse)
async def browse_audio(path: str = Query(default="/", description="Directory path to browse")):
    """Browse ISKCON Desire Tree audio directory listings."""
    # Normalize path
    if not path.startswith("/"):
        path = "/" + path

    # Check cache
    now = time.time()
    cached = _browse_cache.get(path)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    # Fetch via the Andromeda PHP index
    if path == "/":
        url = f"{ISKCON_BASE_URL}/"
    else:
        url = f"{ISKCON_BASE_URL}/index.php?q=f&f={path}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Upstream error: {e}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to fetch directory: {e}")

    entries = _parse_iskcon_page(resp.text)

    # Compute parent path
    parent = None
    stripped = path.rstrip("/")
    if stripped:
        parent_path = stripped.rsplit("/", 1)[0]
        parent = parent_path if parent_path else "/"

    result = BrowseResponse(path=path, parent=parent, entries=entries)
    _browse_cache[path] = (now, result)

    return result


# ---------------------------------------------------------------------------
# ISKCON Desire Tree audio search
# ---------------------------------------------------------------------------

_search_cache: dict[str, tuple[float, SearchResponse]] = {}


def _parse_iskcon_search_page(html: str) -> list[SearchEntry]:
    """Parse ISKCON Desire Tree search results page.

    Each result has a breadcrumb row (bgcolor=333333 or 444444) with
    <nobr><a href=...>Label</a> /</nobr> segments, followed by a result
    row with a folder or MP3 link.
    """
    entries: list[SearchEntry] = []
    seen_hrefs: set[str] = set()

    # Split into result blocks by breadcrumb rows
    # Each block starts with a bgcolor row containing breadcrumbs
    blocks = re.split(r'<table cellspacing=0 cellpadding=4 border=0 width="100%" bgcolor=(?:333333|444444)>', html)

    for block in blocks[1:]:  # Skip the first block (before first result)
        # Extract breadcrumb text from the <nobr> tags
        breadcrumb_parts: list[str] = []
        for bc_match in re.finditer(r'<nobr><a[^>]*>([^<]+)</a>\s*/</nobr>', block):
            label = bc_match.group(1).strip()
            if label != "Home":
                # Clean numeric prefixes: "01 - Srila Prabhupada" -> "Srila Prabhupada"
                label = re.sub(r'^\d+\s*[-_]\s*', '', label)
                breadcrumb_parts.append(label)
        breadcrumb = " / ".join(breadcrumb_parts)

        # Extract folder entries from this block
        for match in re.finditer(
            r'<a\s+href=index\.php\?q=f&f=([^>]+?)>'
            r'<font\s+size="2">([^<]+)</font></a>',
            block,
        ):
            encoded_path, name = match.groups()
            folder_path = re.sub(
                r'%([0-9A-Fa-f]{2})',
                lambda m: chr(int(m.group(1), 16)),
                encoded_path,
            )
            if folder_path in seen_hrefs:
                continue
            seen_hrefs.add(folder_path)

            size = None
            pos = match.end()
            size_match = re.search(
                r'<font\s+size="1">(\d+\s*(?:folders?|files?))</font>',
                block[pos:pos + 200],
            )
            if size_match:
                size = size_match.group(1).replace("\xa0", " ")

            entries.append(SearchEntry(
                name=name.strip(),
                href=folder_path,
                is_dir=True,
                size=size,
                breadcrumb=breadcrumb,
            ))

        # Extract MP3 file entries from this block
        for match in re.finditer(
            r'<a\s+href="(/[^"]+\.mp3)"[^>]*>'
            r'<font\s+size="2">([^<]+)</font></a>',
            block,
        ):
            mp3_path, name = match.groups()
            if mp3_path in seen_hrefs:
                continue
            seen_hrefs.add(mp3_path)

            size = None
            pos = match.end()
            size_match = re.search(
                r'<font\s+size="1"\s+color="aaaaaa">([\d.]+\s*(?:&nbsp;)?\s*[KMG]B)',
                block[pos:pos + 300],
            )
            if size_match:
                size = size_match.group(1).replace("&nbsp;", " ")

            entries.append(SearchEntry(
                name=name.strip(),
                href=mp3_path,
                is_dir=False,
                size=size,
                breadcrumb=breadcrumb,
            ))

    return entries


def _extract_speaker_group(breadcrumb: str) -> str:
    """Extract speaker-level grouping from breadcrumb.

    Examples:
        "Srila Prabhupada / Lectures / English / ..." -> "Srila Prabhupada"
        "ISKCON Swamis / ... / His Holiness X Swami / ..." -> "His Holiness X Swami"
        "ISKCON Prabhujis / ... / His Grace X Prabhu / ..." -> "His Grace X Prabhu"
        "More / ISKCON Juhu Mumbai / ..." -> "More / ISKCON Juhu Mumbai"
    """
    parts = [p.strip() for p in breadcrumb.split("/") if p.strip()]
    if not parts:
        return "Other"

    top = parts[0]
    if top == "Srila Prabhupada":
        return "Srila Prabhupada"

    # ISKCON Swamis / ISKCON Swamis - A to C / His Holiness X Swami
    # ISKCON Prabhujis / ISKCON Prabhujis - A to J / His Grace X Prabhu
    if top in ("ISKCON Swamis", "ISKCON Prabhujis") and len(parts) >= 3:
        return parts[2]

    # "More / ISKCON Juhu Mumbai / ..." → take first two
    if len(parts) >= 2:
        return f"{parts[0]} / {parts[1]}"

    return top


def _group_search_results(entries: list[SearchEntry]) -> list[SearchGroup]:
    """Group search entries by speaker/category from breadcrumb paths."""
    groups: dict[str, list[SearchEntry]] = {}
    for entry in entries:
        key = _extract_speaker_group(entry.breadcrumb) if entry.breadcrumb else "Other"
        groups.setdefault(key, []).append(entry)

    # Sort groups: by number of entries (descending), then alphabetically
    sorted_groups = sorted(groups.items(), key=lambda x: (-len(x[1]), x[0]))

    return [
        SearchGroup(group_title=title, entries=items)
        for title, items in sorted_groups
    ]


@router.get("/browse/search", response_model=SearchResponse)
async def search_audio(q: str = Query(..., min_length=2, description="Search query")):
    """Search ISKCON Desire Tree audio library by title."""
    q = q.strip()

    # Check cache
    now = time.time()
    cached = _search_cache.get(q)
    if cached and (now - cached[0]) < _CACHE_TTL:
        return cached[1]

    url = f"{ISKCON_BASE_URL}/index.php?q=s&s={q}"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"Upstream error: {e}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Failed to search: {e}")

    entries = _parse_iskcon_search_page(resp.text)
    groups = _group_search_results(entries)

    result = SearchResponse(query=q, total=len(entries), groups=groups)
    _search_cache[q] = (now, result)

    return result


# ---------------------------------------------------------------------------
# Topic taxonomy for browse-by-topic
# ---------------------------------------------------------------------------

_TOPIC_TAXONOMY: list[TopicCategory] = [
    TopicCategory(
        category="scripture",
        label="Scriptures",
        topics=[
            TopicEntry(slug="bhagavad-gita", label="Bhagavad Gita", search_terms=["Bhagavad Gita", "BG"], category="scripture"),
            TopicEntry(slug="srimad-bhagavatam", label="Srimad Bhagavatam", search_terms=["Srimad Bhagavatam", "Bhagavatam", "SB"], category="scripture"),
            TopicEntry(slug="chaitanya-charitamrita", label="Chaitanya Charitamrita", search_terms=["Chaitanya Charitamrita", "CC"], category="scripture"),
            TopicEntry(slug="nectar-of-devotion", label="Nectar of Devotion", search_terms=["Nectar of Devotion"], category="scripture"),
            TopicEntry(slug="nectar-of-instruction", label="Nectar of Instruction", search_terms=["Nectar of Instruction", "Upadesamrita"], category="scripture"),
            TopicEntry(slug="isopanisad", label="Sri Isopanisad", search_terms=["Isopanisad", "Isopanishad"], category="scripture"),
            TopicEntry(slug="bhagavat-purana", label="Bhagavat Purana", search_terms=["Bhagavat Purana"], category="scripture"),
        ],
    ),
    TopicCategory(
        category="festival",
        label="Festivals",
        topics=[
            TopicEntry(slug="janmashtami", label="Janmashtami", search_terms=["Janmashtami", "Janmastami"], category="festival"),
            TopicEntry(slug="gaura-purnima", label="Gaura Purnima", search_terms=["Gaura Purnima"], category="festival"),
            TopicEntry(slug="radhastami", label="Radhastami", search_terms=["Radhastami", "Radhashtami"], category="festival"),
            TopicEntry(slug="ratha-yatra", label="Ratha Yatra", search_terms=["Ratha Yatra"], category="festival"),
            TopicEntry(slug="vyasa-puja", label="Vyasa Puja", search_terms=["Vyasa Puja"], category="festival"),
            TopicEntry(slug="govardhan-puja", label="Govardhan Puja", search_terms=["Govardhan"], category="festival"),
            TopicEntry(slug="kartik", label="Kartik", search_terms=["Kartik", "Damodara"], category="festival"),
            TopicEntry(slug="ekadashi", label="Ekadashi", search_terms=["Ekadashi"], category="festival"),
            TopicEntry(slug="appearance-day", label="Appearance Day", search_terms=["Appearance Day"], category="festival"),
            TopicEntry(slug="disappearance-day", label="Disappearance Day", search_terms=["Disappearance Day"], category="festival"),
        ],
    ),
    TopicCategory(
        category="theme",
        label="Themes",
        topics=[
            TopicEntry(slug="surrender", label="Surrender", search_terms=["Surrender"], category="theme"),
            TopicEntry(slug="compassion", label="Compassion", search_terms=["Compassion"], category="theme"),
            TopicEntry(slug="anger", label="Anger", search_terms=["Anger"], category="theme"),
            TopicEntry(slug="detachment", label="Detachment", search_terms=["Detachment", "Vairagya"], category="theme"),
            TopicEntry(slug="devotion", label="Devotion", search_terms=["Devotion", "Bhakti"], category="theme"),
            TopicEntry(slug="karma", label="Karma", search_terms=["Karma"], category="theme"),
            TopicEntry(slug="dharma", label="Dharma", search_terms=["Dharma"], category="theme"),
            TopicEntry(slug="maya", label="Maya", search_terms=["Maya"], category="theme"),
            TopicEntry(slug="guru", label="Guru", search_terms=["Guru"], category="theme"),
            TopicEntry(slug="holy-name", label="Holy Name", search_terms=["Holy Name", "Chanting"], category="theme"),
            TopicEntry(slug="death", label="Death", search_terms=["Death"], category="theme"),
            TopicEntry(slug="love-of-god", label="Love of God", search_terms=["Love of God", "Prema"], category="theme"),
            TopicEntry(slug="humility", label="Humility", search_terms=["Humility"], category="theme"),
            TopicEntry(slug="forgiveness", label="Forgiveness", search_terms=["Forgiveness"], category="theme"),
            TopicEntry(slug="faith", label="Faith", search_terms=["Faith", "Sraddha"], category="theme"),
        ],
    ),
    TopicCategory(
        category="practice",
        label="Practices",
        topics=[
            TopicEntry(slug="kirtan", label="Kirtan", search_terms=["Kirtan", "Kirtana"], category="practice"),
            TopicEntry(slug="japa", label="Japa", search_terms=["Japa"], category="practice"),
            TopicEntry(slug="deity-worship", label="Deity Worship", search_terms=["Deity Worship", "Arcana"], category="practice"),
            TopicEntry(slug="book-distribution", label="Book Distribution", search_terms=["Book Distribution"], category="practice"),
            TopicEntry(slug="preaching", label="Preaching", search_terms=["Preaching"], category="practice"),
            TopicEntry(slug="sadhu-sanga", label="Sadhu Sanga", search_terms=["Sadhu Sanga", "Association"], category="practice"),
            TopicEntry(slug="prasadam", label="Prasadam", search_terms=["Prasadam"], category="practice"),
            TopicEntry(slug="sannyasa", label="Sannyasa", search_terms=["Sannyasa"], category="practice"),
        ],
    ),
]


@router.get("/browse/topics", response_model=TopicTaxonomyResponse)
async def get_topics():
    """Return the topic taxonomy for browse-by-topic."""
    return TopicTaxonomyResponse(categories=_TOPIC_TAXONOMY)
