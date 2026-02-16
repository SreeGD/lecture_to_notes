"""
Compiler Tool: Compile and deduplicate glossary entries across lectures.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def compile_glossary(enriched_notes_list: list[dict]) -> list[dict]:
    """
    Compile glossary from all enriched notes, deduplicating entries.
    For duplicates, keeps the entry with the longest definition.
    """
    term_map: dict[str, dict] = {}
    for enriched in enriched_notes_list:
        for entry in enriched.get("glossary", []):
            term_lower = entry.get("term", "").lower()
            existing = term_map.get(term_lower)
            if existing is None or len(entry.get("definition", "")) > len(existing.get("definition", "")):
                term_map[term_lower] = entry

    result = sorted(term_map.values(), key=lambda e: e.get("term", "").lower())
    logger.info("Compiled glossary: %d entries from %d sources", len(result), len(enriched_notes_list))
    return result
