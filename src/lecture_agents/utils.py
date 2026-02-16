"""
Utility functions for the Lecture-to-Notes Pipeline.

Provides URL-to-folder-name helpers for organizing per-run outputs.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from urllib.parse import unquote, urlparse


def url_to_slug(url: str, max_length: int = 80) -> str:
    """
    Derive a filesystem-safe folder name from a URL.

    Combines a human-readable name extracted from the URL filename
    with a short SHA-256 hash for uniqueness.

    Example:
        "https://example.com/2026-02-11_SB_03-13-04_Lecture.mp3"
        → "2026-02-11_SB_03-13-04_Lecture_a7b8c9d1"
    """
    url_hash = hashlib.sha256(url.encode()).hexdigest()[:8]

    parsed = urlparse(url)
    path = unquote(parsed.path)
    filename = Path(path).stem  # Remove extension

    if not filename or filename in (".", "/", ""):
        # Fallback: use domain + path fragment
        filename = f"{parsed.netloc}_{parsed.path}"

    # Clean: keep only alphanumeric, underscores, hyphens
    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", filename)
    # Collapse multiple underscores
    slug = re.sub(r"_+", "_", slug).strip("_")

    # Truncate, leaving room for _<8-char-hash>
    limit = max_length - 9  # 1 underscore + 8 hash chars
    if len(slug) > limit:
        slug = slug[:limit].rstrip("_")

    return f"{slug}_{url_hash}"


def title_to_slug(title: str, urls: list[str], max_length: int = 80) -> str:
    """
    Derive a folder name from a book title (used for multi-URL runs).

    Falls back to url_to_slug of the first URL if title is generic.
    """
    if not title or title == "Lecture Notes":
        return url_to_slug(urls[0], max_length) if urls else "run"

    slug = re.sub(r"[^a-zA-Z0-9_-]", "_", title)
    slug = re.sub(r"_+", "_", slug).strip("_")
    url_hash = hashlib.sha256("_".join(urls).encode()).hexdigest()[:8]

    limit = max_length - 9
    if len(slug) > limit:
        slug = slug[:limit].rstrip("_")

    return f"{slug}_{url_hash}"


LATEST_RUN_FILE = ".latest_run"


def resolve_run_dir(
    base_output: str,
    url: str | None = None,
    urls: list[str] | None = None,
    title: str | None = None,
    from_agent: int = 1,
) -> str:
    """
    Resolve the per-run output directory.

    For new runs (from_agent == 1): creates a new slug-based subfolder
    under base_output and writes a .latest_run marker.

    For resume (from_agent > 1): finds the existing run directory by:
      1. Checking if base_output itself has checkpoints/ (explicit path)
      2. Reading .latest_run marker in base_output
      3. Scanning base_output for any subfolder with checkpoints/

    Returns:
        Absolute path to the run directory.
    """
    base = Path(base_output)

    # Resume: find existing run dir
    if from_agent > 1:
        # Direct path: user specified the run dir explicitly
        if (base / "checkpoints").exists():
            return str(base)

        # .latest_run marker
        latest_file = base / LATEST_RUN_FILE
        if latest_file.exists():
            slug = latest_file.read_text().strip()
            candidate = base / slug
            if (candidate / "checkpoints").exists():
                return str(candidate)

        # Scan for any subfolder with checkpoints
        if base.exists():
            for child in sorted(base.iterdir()):
                if child.is_dir() and (child / "checkpoints").exists():
                    return str(child)

        # Nothing found — fall through (checkpoint validation will catch this)
        return str(base)

    # New run: compute slug and create folder
    if url:
        slug = url_to_slug(url)
    elif urls:
        slug = title_to_slug(title or "Lecture Notes", urls)
    else:
        slug = "run"

    run_dir = base / slug
    run_dir.mkdir(parents=True, exist_ok=True)

    # Write .latest_run marker so --from-agent can find it
    base.mkdir(parents=True, exist_ok=True)
    (base / LATEST_RUN_FILE).write_text(slug)

    return str(run_dir)
