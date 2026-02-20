"""
Enrichment Tool: Fetch and cache content from vedabase.io.

The single source of truth for Srila Prabhupada's translations and purports.
Implements polite rate-limiting, JSON file caching, and HTML parsing.
Pure function + BaseTool wrapper pattern.

CRITICAL: This tool fetches ONLY from vedabase.io. It never generates,
interpolates, or speculates about verse content.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

import httpx
from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from lecture_agents.config.constants import (
    CC_DIVISIONS,
    SCRIPTURE_ABBREVIATIONS,
    VEDABASE_BASE_URL,
    VEDABASE_CACHE_FILE,
    VEDABASE_REQUEST_DELAY,
    VEDABASE_TIMEOUT,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------


def _load_cache(cache_path: str) -> dict:
    """Load the vedabase cache from JSON file."""
    path = Path(cache_path)
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cache load failed: %s", e)
    return {}


def _save_cache(cache_path: str, cache: dict) -> None:
    """Save the vedabase cache to JSON file."""
    path = Path(cache_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False), encoding="utf-8")


def _cache_key(scripture: str, chapter: str, verse: str) -> str:
    """Build a normalized cache key."""
    return f"{scripture.upper()}_{chapter}_{verse}"


# ---------------------------------------------------------------------------
# URL building
# ---------------------------------------------------------------------------


def build_vedabase_url(scripture: str, chapter: str, verse: str) -> Optional[str]:
    """
    Build vedabase.io URL from reference components.

    Examples:
        ("BG", "2", "47")      -> "https://vedabase.io/en/library/bg/2/47/"
        ("SB", "1.2", "6")     -> "https://vedabase.io/en/library/sb/1/2/6/"
        ("CC", "Adi.1", "1")   -> "https://vedabase.io/en/library/cc/adi/1/1/"
        ("NOI", "", "1")       -> "https://vedabase.io/en/library/noi/1/"
    """
    abbrev = SCRIPTURE_ABBREVIATIONS.get(scripture.upper())
    if not abbrev:
        return None

    # Parse chapter — may contain dots for multi-level references
    chapter_parts = []
    if chapter:
        for part in chapter.replace(".", "/").split("/"):
            part = part.strip()
            if not part:
                continue
            # Handle CC division names
            upper = part.upper()
            if upper in CC_DIVISIONS:
                chapter_parts.append(CC_DIVISIONS[upper])
            else:
                chapter_parts.append(part.lower())

    # Take first verse if range (e.g., "1-3" -> "1")
    verse_num = verse.split("-")[0].strip()

    if chapter_parts:
        path = "/".join(chapter_parts) + "/" + verse_num
    else:
        path = verse_num

    return f"{VEDABASE_BASE_URL}/{abbrev}/{path}/"


# ---------------------------------------------------------------------------
# HTML parsing
# ---------------------------------------------------------------------------


def _parse_vedabase_page(html: str) -> dict:
    """
    Parse a vedabase.io verse page and extract structured content.

    Extracts: devanagari, verse_text (transliteration), synonyms,
    translation, purport (full text and excerpt).
    """
    soup = BeautifulSoup(html, "html.parser")
    result: dict = {}

    # The vedabase.io page structure uses specific div classes/sections
    # We look for known patterns in the page content

    # Devanagari text
    devanagari_div = soup.find("div", class_="r-devanagari")
    if devanagari_div:
        result["devanagari"] = devanagari_div.get_text(strip=True)

    # Verse text (transliteration)
    verse_div = soup.find("div", class_="r-verse-text")
    if verse_div:
        result["verse_text"] = verse_div.get_text(separator="\n", strip=True)

    # Synonyms
    synonyms_div = soup.find("div", class_="r-synonyms")
    if synonyms_div:
        result["synonyms"] = synonyms_div.get_text(strip=True)

    # Translation
    translation_div = soup.find("div", class_="r-translation")
    if translation_div:
        result["translation"] = translation_div.get_text(strip=True)

    # Purport
    purport_div = soup.find("div", class_="r-purport")
    if purport_div:
        full_purport = purport_div.get_text(separator="\n", strip=True)
        result["purport_full"] = full_purport
        result["purport_excerpt"] = full_purport[:500] if full_purport else None

    # Fallback: try generic content parsing if specific classes not found
    if not result:
        # Look for any verse-like content in the main content area
        main = soup.find("main") or soup.find("article") or soup.find("div", class_="content")
        if main:
            text_blocks = main.find_all(["p", "div"])
            texts = [b.get_text(strip=True) for b in text_blocks if b.get_text(strip=True)]
            if texts:
                # Heuristic: first block with Sanskrit = verse, next = synonyms, etc.
                for text in texts:
                    if not result.get("translation") and (
                        text.startswith("TRANSLATION") or "Translation" in text[:20]
                    ):
                        result["translation"] = text.replace("TRANSLATION", "").strip()
                    elif not result.get("purport_excerpt") and (
                        text.startswith("PURPORT") or "Purport" in text[:20]
                    ):
                        purport = text.replace("PURPORT", "").strip()
                        result["purport_excerpt"] = purport[:500]
                        result["purport_full"] = purport

    # Extract cross-references from purport
    if result.get("purport_full"):
        result["cross_refs_in_purport"] = _extract_refs_from_purport(
            result["purport_full"]
        )
    else:
        result["cross_refs_in_purport"] = []

    return result


def _extract_refs_from_purport(purport_text: str) -> list[str]:
    """Extract scripture references mentioned within a purport text."""
    refs: list[str] = []

    # BG references
    for m in re.finditer(r"(?:Bg\.|BG|Bhagavad-gītā)\s*(\d+\.\d+)", purport_text):
        refs.append(f"BG {m.group(1)}")

    # SB references
    for m in re.finditer(r"(?:SB|Bhāg\.)\s*(\d+\.\d+\.\d+)", purport_text):
        refs.append(f"SB {m.group(1)}")

    # CC references
    for m in re.finditer(
        r"(?:Cc\.|CC)\s*(Ādi|Madhya|Antya|adi|madhya|antya)\s*(\d+\.\d+)",
        purport_text,
    ):
        refs.append(f"CC {m.group(1).title()} {m.group(2)}")

    return list(dict.fromkeys(refs))  # deduplicate preserving order


# ---------------------------------------------------------------------------
# Core fetch function
# ---------------------------------------------------------------------------


def fetch_verse(
    scripture: str,
    chapter: str,
    verse: str,
    cache_path: str = VEDABASE_CACHE_FILE,
) -> dict:
    """
    Fetch a verse from vedabase.io with caching.

    1. Check cache first
    2. If not cached, fetch live from vedabase.io
    3. Parse HTML to extract verse content
    4. Cache the result for future use
    5. Respect rate limiting (1s delay between live fetches)

    Args:
        scripture: Scripture abbreviation (BG, SB, CC, etc.).
        chapter: Chapter reference (may include canto: "1.2").
        verse: Verse number or range ("47", "1-3").
        cache_path: Path to cache JSON file.

    Returns:
        dict with keys:
            url: vedabase.io URL
            verified: bool — whether verse was found and has translation
            devanagari: str or None
            verse_text: str or None (IAST transliteration)
            synonyms: str or None
            translation: str or None (Prabhupada's translation)
            purport_excerpt: str or None
            cross_refs_in_purport: list[str]
            fetch_source: "live" | "cache" | "not_found"
            error: str or None
    """
    key = _cache_key(scripture, chapter, verse)

    # Step 1: Check cache
    cache = _load_cache(cache_path)
    if key in cache:
        cached = cache[key]
        logger.debug("Cache hit: %s", key)
        return {**cached, "fetch_source": "cache"}

    # Step 2: Build URL
    url = build_vedabase_url(scripture, chapter, verse)
    if not url:
        return {
            "url": None,
            "verified": False,
            "fetch_source": "not_found",
            "error": f"Unknown scripture abbreviation: {scripture}",
        }

    # Step 3: Fetch live
    try:
        logger.info("Fetching from vedabase.io: %s", url)
        response = httpx.get(
            url,
            timeout=VEDABASE_TIMEOUT,
            follow_redirects=True,
            headers={"User-Agent": "LectureToBook/1.0 (vedabase-reference-tool)"},
        )

        if response.status_code == 200:
            content = _parse_vedabase_page(response.text)
            has_translation = bool(content.get("translation"))

            result = {
                "url": url,
                "verified": has_translation,
                "devanagari": content.get("devanagari"),
                "verse_text": content.get("verse_text"),
                "synonyms": content.get("synonyms"),
                "translation": content.get("translation"),
                "purport_excerpt": content.get("purport_excerpt"),
                "cross_refs_in_purport": content.get("cross_refs_in_purport", []),
                "fetch_source": "live",
                "error": None,
            }

            # Cache the result (without fetch_source)
            cache_entry = {k: v for k, v in result.items() if k != "fetch_source"}
            cache[key] = cache_entry
            _save_cache(cache_path, cache)

            # Rate limiting
            time.sleep(VEDABASE_REQUEST_DELAY)

            return result

        elif response.status_code == 404:
            logger.warning("Verse not found on vedabase.io: %s", url)
            return {
                "url": url,
                "verified": False,
                "fetch_source": "not_found",
                "error": f"HTTP 404: Verse not found at {url}",
            }
        else:
            return {
                "url": url,
                "verified": False,
                "fetch_source": "not_found",
                "error": f"HTTP {response.status_code} from vedabase.io",
            }

    except httpx.TimeoutException:
        logger.error("Vedabase.io request timed out: %s", url)
        return {
            "url": url,
            "verified": False,
            "fetch_source": "not_found",
            "error": f"Request timed out after {VEDABASE_TIMEOUT}s",
        }
    except Exception as e:
        logger.error("Vedabase.io fetch failed: %s — %s", url, e)
        return {
            "url": url,
            "verified": False,
            "fetch_source": "not_found",
            "error": str(e),
        }


def batch_fetch_verses(
    references: list[dict],
    cache_path: str = VEDABASE_CACHE_FILE,
) -> list[dict]:
    """
    Fetch multiple verses from vedabase.io with batched cache reads/writes.

    Optimization over calling fetch_verse() in a loop:
    1. Load cache once
    2. Separate cache hits from cache misses
    3. Fetch all misses sequentially (with rate limiting)
    4. Save cache once at the end

    Args:
        references: List of dicts with keys: scripture, chapter, verse.
        cache_path: Path to vedabase cache JSON file.

    Returns:
        List of result dicts in the same order as input references.
    """
    if not references:
        return []

    cache = _load_cache(cache_path)
    results: list[dict] = [None] * len(references)  # type: ignore[list-item]
    misses: list[tuple[int, dict]] = []  # (index, ref_dict) for cache misses

    # Pass 1: check cache
    for i, ref in enumerate(references):
        scripture = ref.get("scripture", "")
        chapter = ref.get("chapter", "")
        verse = ref.get("verse", "")
        key = _cache_key(scripture, chapter, verse)

        if key in cache:
            logger.debug("Batch cache hit: %s", key)
            results[i] = {**cache[key], "fetch_source": "cache"}
        else:
            misses.append((i, ref))

    # Pass 2: fetch misses from vedabase.io
    cache_modified = False
    for idx, ref in misses:
        scripture = ref.get("scripture", "")
        chapter = ref.get("chapter", "")
        verse = ref.get("verse", "")

        url = build_vedabase_url(scripture, chapter, verse)
        if not url:
            results[idx] = {
                "url": None,
                "verified": False,
                "fetch_source": "not_found",
                "error": f"Unknown scripture abbreviation: {scripture}",
            }
            continue

        try:
            logger.info("Batch fetching from vedabase.io: %s", url)
            response = httpx.get(
                url,
                timeout=VEDABASE_TIMEOUT,
                follow_redirects=True,
                headers={"User-Agent": "LectureToBook/1.0 (vedabase-reference-tool)"},
            )

            if response.status_code == 200:
                content = _parse_vedabase_page(response.text)
                has_translation = bool(content.get("translation"))
                result = {
                    "url": url,
                    "verified": has_translation,
                    "devanagari": content.get("devanagari"),
                    "verse_text": content.get("verse_text"),
                    "synonyms": content.get("synonyms"),
                    "translation": content.get("translation"),
                    "purport_excerpt": content.get("purport_excerpt"),
                    "cross_refs_in_purport": content.get("cross_refs_in_purport", []),
                    "fetch_source": "live",
                    "error": None,
                }
                # Update cache
                key = _cache_key(scripture, chapter, verse)
                cache[key] = {k: v for k, v in result.items() if k != "fetch_source"}
                cache_modified = True
                results[idx] = result
            elif response.status_code == 404:
                logger.warning("Verse not found on vedabase.io: %s", url)
                results[idx] = {
                    "url": url,
                    "verified": False,
                    "fetch_source": "not_found",
                    "error": f"HTTP 404: Verse not found at {url}",
                }
            else:
                results[idx] = {
                    "url": url,
                    "verified": False,
                    "fetch_source": "not_found",
                    "error": f"HTTP {response.status_code} from vedabase.io",
                }

        except httpx.TimeoutException:
            logger.error("Vedabase.io request timed out: %s", url)
            results[idx] = {
                "url": url,
                "verified": False,
                "fetch_source": "not_found",
                "error": f"Request timed out after {VEDABASE_TIMEOUT}s",
            }
        except Exception as e:
            logger.error("Vedabase.io fetch failed: %s — %s", url, e)
            results[idx] = {
                "url": url,
                "verified": False,
                "fetch_source": "not_found",
                "error": str(e),
            }

        # Rate limiting between live fetches
        time.sleep(VEDABASE_REQUEST_DELAY)

    # Pass 3: save cache once if modified
    if cache_modified:
        _save_cache(cache_path, cache)

    return results


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class VedabaseFetchInput(BaseModel):
    scripture: str = Field(..., description="Scripture abbreviation: BG, SB, CC, etc.")
    chapter: str = Field(..., description="Chapter reference e.g. '2', '1.2', 'Adi.1'")
    verse: str = Field(..., description="Verse number e.g. '47', '6', '1-3'")


class VedabaseFetchTool(BaseTool):
    name: str = "fetch_verse_from_vedabase"
    description: str = (
        "Fetch a verse from vedabase.io — the authoritative source for "
        "Srila Prabhupada's translations and purports. Returns the verse "
        "text, translation, synonyms, and purport excerpt."
    )
    args_schema: type[BaseModel] = VedabaseFetchInput

    def _run(self, scripture: str, chapter: str, verse: str) -> str:
        result = fetch_verse(scripture, chapter, verse)
        return json.dumps(result, ensure_ascii=False)
