"""
Compiler Tool: Markdown formatting for book output.

Formats chapters, verse blocks, front matter, and back matter
as publication-ready Markdown.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def format_verse_block(verification: dict) -> str:
    """Format a verified verse reference as a Markdown blockquote."""
    ref = verification.get("reference", {})
    canonical = ref.get("canonical_ref", "Unknown")
    url = verification.get("vedabase_url", "")
    verse_text = verification.get("verse_text", "")
    translation = verification.get("translation", "")
    synonyms = verification.get("synonyms", "")
    purport = verification.get("purport_excerpt", "")

    lines = [f"> **Reference:** {canonical}"]
    if verse_text:
        lines.append(f"> *{verse_text}*")
    lines.append(">")
    if translation:
        lines.append(f"> **Translation (Srila Prabhupada):** {translation}")
    if synonyms:
        lines.extend([">", f"> **Synonyms:** {synonyms}"])
    if purport:
        lines.extend([">", f"> **Purport Summary:** {purport}"])
    if url:
        lines.extend([">", f"> [Vedabase.io]({url})"])
    return "\n".join(lines)


def format_chapter_markdown(chapter: dict, verifications: list[dict]) -> str:
    """Format a single chapter as Markdown."""
    lines: list[str] = []

    # Use LLM-enriched content when available; fall back to raw segments
    enriched_md = chapter.get("enriched_markdown")
    if enriched_md:
        # Enriched markdown has its own title/headers — no extra Chapter header
        lines.append(enriched_md)
    else:
        number = chapter.get("number", 1)
        title = chapter.get("title", f"Chapter {number}")
        lines.append(f"# Chapter {number}: {title}")
        lines.append("")

        duration = chapter.get("duration_seconds", 0)
        if duration:
            lines.extend([f"*{duration / 60:.0f} minutes*", ""])
        # Fallback: build paragraphs from raw transcript segments
        segments = chapter.get("segments", [])
        current_speaker = None
        prev_end = 0.0
        para_lines: list[str] = []

        def _flush_para():
            if para_lines:
                lines.append(" ".join(para_lines))
                lines.append("")
                para_lines.clear()

        for seg in segments:
            speaker = seg.get("speaker")
            text = seg.get("text", "").strip()
            if not text:
                continue
            start = seg.get("start", 0.0)
            gap = start - prev_end if prev_end else 0.0
            prev_end = seg.get("end", start)

            if speaker and speaker != current_speaker:
                _flush_para()
                lines.extend([f"**{speaker}:**", ""])
                current_speaker = speaker
            elif gap > 2.0 and para_lines:
                _flush_para()

            para_lines.append(text)

        _flush_para()

        refs = chapter.get("references", [])
        if refs:
            ver_lookup = {
                v.get("reference", {}).get("canonical_ref", ""): v
                for v in verifications
            }
            blocks = [format_verse_block(ver_lookup[r]) for r in refs if r in ver_lookup]
            if blocks:
                lines.extend(["---", "", "### Scripture Spotlight", ""])
                for block in blocks:
                    lines.extend([block, ""])

    return "\n".join(lines)


def format_front_matter(
    title: str,
    subtitle: Optional[str] = None,
    speaker: Optional[str] = None,
    source_references: Optional[list[dict]] = None,
) -> str:
    """Generate title page in Markdown."""
    lines = [f"# {title}"]
    if speaker:
        lines.append(f"*By {speaker}*")
    lines.append("")

    # Source information right after title
    if source_references:
        for ref in source_references:
            url = ref.get("url", "")
            dur = ref.get("duration_seconds", 0)
            info_parts = []
            if url:
                info_parts.append(f"**Source:** [{url}]({url})")
            if dur:
                info_parts.append(f"**Duration:** {dur / 60:.0f} minutes")
            if ref.get("date"):
                info_parts.append(f"**Date:** {ref['date']}")
            if info_parts:
                lines.append(" | ".join(info_parts))
        lines.append("")

    lines.append(f"*Compiled on {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")

    return "\n".join(lines)


def format_back_matter(
    glossary_entries: Optional[list[dict]] = None,
    verse_index: Optional[dict[str, list[int]]] = None,
    theme_index: Optional[dict[str, list[int]]] = None,
    source_references: Optional[list[dict]] = None,
) -> str:
    """Generate back matter sections in Markdown."""
    lines = ["---", ""]

    if glossary_entries:
        lines.extend(["# Glossary", ""])
        for entry in sorted(glossary_entries, key=lambda e: e.get("term", "").lower()):
            lines.extend([f"**{entry.get('term', '')}** — {entry.get('definition', '')}", ""])

    if verse_index:
        lines.extend(["# Scripture Index", ""])
        for ref in sorted(verse_index.keys()):
            ch_list = ", ".join(f"Ch. {c}" for c in verse_index[ref])
            lines.append(f"- **{ref}** — {ch_list}")
        lines.append("")

    if theme_index:
        lines.extend(["# Thematic Index", ""])
        for theme in sorted(theme_index.keys()):
            ch_list = ", ".join(f"Ch. {c}" for c in theme_index[theme])
            lines.append(f"- **{theme}** — {ch_list}")
        lines.append("")

    if source_references:
        lines.extend(["# Source References", ""])
        if len(source_references) == 1:
            ref = source_references[0]
            lines.extend([
                "| Field | Details |",
                "|-------|---------|",
                f'| **Original Audio** | [{ref.get("url", "")}]({ref.get("url", "")}) |',
                f'| **Title** | {ref.get("title", "Unknown")} |',
            ])
            if ref.get("date"):
                lines.append(f'| **Date** | {ref["date"]} |')
            if ref.get("duration_seconds"):
                lines.append(f'| **Duration** | {ref["duration_seconds"]/60:.0f} minutes |')
        else:
            lines.extend(["| # | Title | URL |", "|---|-------|-----|"])
            for ref in source_references:
                url = ref.get("url", "")
                lines.append(f"| {ref.get('order', 0)} | {ref.get('title', '')} | [{url}]({url}) |")
        lines.append("")

    lines.extend([
        "---", "",
        "*These notes were compiled using the Lecture-to-Notes Pipeline.*",
        "*All scripture references verified against [vedabase.io](https://vedabase.io).*",
    ])
    return "\n".join(lines)
