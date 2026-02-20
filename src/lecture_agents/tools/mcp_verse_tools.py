"""
Enrichment Tool: MCP-powered verse lookup and fuzzy matching.

Connects to the Vedabase MCP Server to provide:
- Verse lookup with Prabhupada's translation, synonyms, and purport
- Fuzzy matching of garbled Sanskrit from transcripts
- Keyword search across all 700 BG verses

Designed to plug into the enrichment agent alongside the existing
vedabase_fetcher.py (which handles BG, SB, CC, NOI, ISO, BS).
The MCP server currently covers Bhagavad Gita only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Check for MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    HAS_MCP = True
except ImportError:
    HAS_MCP = False


# Path to the Vedabase MCP server package
_VEDABASE_MCP_DIR = str(Path.home() / "Projects" / "Vedabase MCP Server")


def _get_server_params() -> "StdioServerParameters":
    """Build StdioServerParameters for the Vedabase MCP server."""
    venv_python = str(Path(_VEDABASE_MCP_DIR) / ".venv" / "bin" / "python")
    return StdioServerParameters(
        command=venv_python,
        args=["-m", "vedabase_mcp"],
    )


# ---------------------------------------------------------------------------
# Async core — these run inside an MCP client session
# ---------------------------------------------------------------------------


async def _call_tool(tool_name: str, arguments: dict) -> str:
    """Connect to MCP server, call a single tool, return the text result."""
    params = _get_server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return result.content[0].text


async def _call_tools_batch(calls: list[tuple[str, dict]]) -> list[str]:
    """Connect once, call multiple tools sequentially, return all results."""
    params = _get_server_params()
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            results = []
            for tool_name, arguments in calls:
                result = await session.call_tool(tool_name, arguments)
                results.append(result.content[0].text)
            return results


# ---------------------------------------------------------------------------
# Sync wrappers — usable from the existing synchronous pipeline
# ---------------------------------------------------------------------------


def _run_async(coro):
    """Run an async coroutine from sync code, handling existing event loops."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an existing event loop (e.g., Jupyter, FastAPI)
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as pool:
            return pool.submit(asyncio.run, coro).result()
    else:
        return asyncio.run(coro)


def mcp_lookup_verse(reference: str) -> dict:
    """
    Look up a BG verse via the Vedabase MCP server.

    Returns a dict compatible with the existing vedabase_fetcher format:
        url, verified, devanagari, verse_text, synonyms,
        translation, purport_excerpt, fetch_source, error
    """
    if not HAS_MCP:
        return {
            "url": None,
            "verified": False,
            "fetch_source": "not_found",
            "error": "mcp SDK not installed. pip install mcp[cli]",
        }

    try:
        text = _run_async(_call_tool("lookup_verse", {"reference": reference}))

        if text.startswith("Error:"):
            return {
                "url": None,
                "verified": False,
                "fetch_source": "not_found",
                "error": text,
            }

        # Parse the markdown response into structured fields
        return _parse_mcp_verse_response(text, reference)

    except Exception as e:
        logger.error("MCP lookup_verse failed for %s: %s", reference, e)
        return {
            "url": None,
            "verified": False,
            "fetch_source": "not_found",
            "error": str(e),
        }


def mcp_fuzzy_match(garbled_sanskrit: str, top_n: int = 3) -> list[dict]:
    """
    Fuzzy-match garbled Sanskrit via the Vedabase MCP server.

    Returns a list of match dicts:
        [{"ref": "BG 9.34", "score": 0.82, "text": "..."}, ...]
    """
    if not HAS_MCP:
        logger.warning("mcp SDK not available; skipping fuzzy match")
        return []

    try:
        text = _run_async(
            _call_tool(
                "fuzzy_match_verse",
                {"garbled_sanskrit": garbled_sanskrit, "top_n": top_n},
            )
        )
        return _parse_fuzzy_response(text)

    except Exception as e:
        logger.error("MCP fuzzy_match failed: %s", e)
        return []


def mcp_search_verses(query: str, max_results: int = 5) -> str:
    """Search cached BG verses by keyword via the Vedabase MCP server."""
    if not HAS_MCP:
        return "mcp SDK not installed"

    try:
        return _run_async(
            _call_tool(
                "search_verses",
                {"query": query, "max_results": max_results},
            )
        )
    except Exception as e:
        logger.error("MCP search_verses failed: %s", e)
        return f"Error: {e}"


def mcp_seed_database() -> str:
    """Seed the MCP server's database with all 700 BG verses."""
    if not HAS_MCP:
        return "mcp SDK not installed"

    try:
        return _run_async(_call_tool("seed_database", {}))
    except Exception as e:
        logger.error("MCP seed_database failed: %s", e)
        return f"Error: {e}"


def mcp_is_available() -> bool:
    """Check if the MCP SDK is installed and the server is reachable."""
    if not HAS_MCP:
        return False
    try:
        # Quick check: list tools
        async def _check():
            params = _get_server_params()
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    return len(tools.tools) > 0

        return _run_async(_check())
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Response parsers — convert MCP markdown responses to structured dicts
# ---------------------------------------------------------------------------


def _parse_mcp_verse_response(markdown: str, reference: str) -> dict:
    """Parse the markdown output from lookup_verse into a structured dict."""
    import re

    result = {
        "url": None,
        "verified": False,
        "devanagari": None,
        "verse_text": None,
        "synonyms": None,
        "translation": None,
        "purport_excerpt": None,
        "purport_full": None,
        "cross_refs_in_purport": [],
        "fetch_source": "mcp",
        "error": None,
    }

    # Extract URL
    url_match = re.search(r"\[Read on Vedabase\]\(([^)]+)\)", markdown)
    if url_match:
        result["url"] = url_match.group(1)

    # Extract sections by markdown headers
    sections = {
        "devanagari": r"\*\*Sanskrit:\*\*\s*\n(.*?)(?=\n\*\*|\n\[|$)",
        "verse_text": r"\*\*Transliteration:\*\*\s*\n_?(.*?)_?(?=\n\*\*|\n\[|$)",
        "synonyms": r"\*\*Synonyms:\*\*\s*\n(.*?)(?=\n\*\*|\n\[|$)",
        "translation": r"\*\*Translation \(Srila Prabhupada\):\*\*\s*\n(.*?)(?=\n\*\*|\n\[|$)",
        "purport_excerpt": r"\*\*Purport:\*\*\s*\n(.*?)(?=\n\*\*|\n\[|$)",
    }

    for key, pattern in sections.items():
        match = re.search(pattern, markdown, re.DOTALL)
        if match:
            result[key] = match.group(1).strip()

    # Mark as verified if we got at least a translation
    result["verified"] = bool(result.get("translation"))

    # Extract cross-references from purport
    if result.get("purport_excerpt"):
        result["purport_full"] = result["purport_excerpt"]
        bg_refs = re.findall(r"(?:Bg\.|BG)\s*(\d+\.\d+)", result["purport_excerpt"])
        result["cross_refs_in_purport"] = [f"BG {r}" for r in bg_refs]

    return result


def _parse_fuzzy_response(text: str) -> list[dict]:
    """Parse the markdown output from fuzzy_match_verse into a list of dicts."""
    import re

    matches = []
    # Pattern: "1. **BG 9.34** (score: 0.82)"
    for m in re.finditer(
        r"\d+\.\s+\*\*([^*]+)\*\*\s+\(score:\s+([\d.]+)\)\s*\n\s+_([^_]+)_",
        text,
    ):
        matches.append({
            "ref": m.group(1).strip(),
            "score": float(m.group(2)),
            "transliteration": m.group(3).strip(),
        })

    return matches
