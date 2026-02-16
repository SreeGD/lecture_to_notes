"""
Compiler Tool: Build verse and thematic indices for the book.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def build_verse_index(chapters: list[dict]) -> dict[str, list[int]]:
    """Build verse reference -> chapter number index."""
    index: dict[str, list[int]] = {}
    for ch in chapters:
        ch_num = ch.get("number", 0)
        for ref in ch.get("references", []):
            if ref not in index:
                index[ref] = []
            if ch_num not in index[ref]:
                index[ref].append(ch_num)
    return dict(sorted(index.items()))


def build_theme_index(chapters: list[dict]) -> dict[str, list[int]]:
    """Build theme -> chapter number index."""
    index: dict[str, list[int]] = {}
    for ch in chapters:
        ch_num = ch.get("number", 0)
        for theme in ch.get("themes", []):
            if theme not in index:
                index[theme] = []
            if ch_num not in index[theme]:
                index[theme].append(ch_num)
    return dict(sorted(index.items()))
