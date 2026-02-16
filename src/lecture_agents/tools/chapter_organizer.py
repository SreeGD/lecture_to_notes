"""
Compiler Tool: Organize enriched transcripts into chapter structure.

Segments transcript content into logical chapters based on thematic breaks,
timestamp gaps, and speaker transitions.
"""

from __future__ import annotations

import logging

from lecture_agents.config.constants import CHAPTER_MIN_SEGMENTS

logger = logging.getLogger(__name__)


def organize_chapters(
    enriched_notes_list: list[dict],
    transcript_outputs: list[dict],
    mode: str = "single",
) -> list[dict]:
    """
    Organize enriched transcripts into chapter structure.

    Single mode: Transcript is divided into chapters based on thematic breaks.
    Multi mode: Each transcript becomes one chapter/part.

    Returns:
        list of dicts with keys: number, title, segments, references,
        themes, source_url, duration_seconds.
    """
    chapters: list[dict] = []

    if mode == "multi":
        for i, (enriched, transcript) in enumerate(
            zip(enriched_notes_list, transcript_outputs), 1
        ):
            topic = enriched.get("thematic_index", {}).get("primary_topic", f"Part {i}")
            ch = {
                "number": i,
                "title": topic,
                "segments": transcript.get("segments", []),
                "references": [
                    r.get("canonical_ref", "")
                    for r in enriched.get("references_found", [])
                ],
                "themes": [
                    t.get("tag", "")
                    for t in enriched.get("thematic_index", {}).get("themes", [])
                ],
                "source_url": transcript.get("source_audio", ""),
                "duration_seconds": transcript.get("duration_seconds", 0),
            }
            if enriched.get("enriched_markdown"):
                ch["enriched_markdown"] = enriched["enriched_markdown"]
            chapters.append(ch)
    else:
        if not enriched_notes_list:
            return chapters
        enriched = enriched_notes_list[0]
        transcript = transcript_outputs[0] if transcript_outputs else {}
        segments = transcript.get("segments", [])

        if len(segments) < CHAPTER_MIN_SEGMENTS * 2:
            ch = {
                "number": 1,
                "title": enriched.get("thematic_index", {}).get(
                    "primary_topic", "Main Discourse"
                ),
                "segments": segments,
                "references": [
                    r.get("canonical_ref", "")
                    for r in enriched.get("references_found", [])
                ],
                "themes": [
                    t.get("tag", "")
                    for t in enriched.get("thematic_index", {}).get("themes", [])
                ],
                "source_url": transcript.get("source_audio", ""),
                "duration_seconds": transcript.get("duration_seconds", 0),
            }
            if enriched.get("enriched_markdown"):
                ch["enriched_markdown"] = enriched["enriched_markdown"]
            chapters.append(ch)
            return chapters

        breaks = _find_chapter_breaks(segments)
        themes = enriched.get("thematic_index", {}).get("themes", [])
        refs = enriched.get("references_found", [])

        endpoints = breaks + [len(segments)]
        for ch_num, (start_idx, end_idx) in enumerate(
            zip(endpoints, endpoints[1:]), 1
        ):
            ch_segments = segments[start_idx:end_idx]
            ch_refs = [
                r.get("canonical_ref", "")
                for r in refs
                if start_idx <= r.get("segment_index", -1) < end_idx
            ]
            title = themes[ch_num - 1]["tag"] if ch_num <= len(themes) and themes else (
                f"Discussion of {ch_refs[0]}" if ch_refs else f"Chapter {ch_num}"
            )
            ch = {
                "number": ch_num,
                "title": title,
                "segments": ch_segments,
                "references": ch_refs,
                "themes": [t.get("tag", "") for t in themes[:2]] if themes else [],
                "source_url": transcript.get("source_audio", ""),
                "duration_seconds": sum(
                    s.get("end", 0) - s.get("start", 0) for s in ch_segments
                ),
            }
            # Attach enriched markdown to the first chapter
            if ch_num == 1 and enriched.get("enriched_markdown"):
                ch["enriched_markdown"] = enriched["enriched_markdown"]
            chapters.append(ch)

    return chapters


def _find_chapter_breaks(segments: list[dict]) -> list[int]:
    """Find natural chapter break points based on pauses and speaker changes."""
    breaks = [0]
    for i in range(1, len(segments)):
        prev = segments[i - 1]
        curr = segments[i]
        gap = curr.get("start", 0) - prev.get("end", 0)
        if gap > 5.0 and i - breaks[-1] >= CHAPTER_MIN_SEGMENTS:
            breaks.append(i)
    return breaks
