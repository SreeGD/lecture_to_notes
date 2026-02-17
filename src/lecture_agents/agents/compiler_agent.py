"""
Agent 04: Compiler Agent
Lecture-to-Notes Pipeline v1.0

Assembles enriched notes into a professionally structured, readable
book in Markdown format.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

try:
    from crewai import Agent, Task
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    Agent = None  # type: ignore[assignment,misc]
    Task = None   # type: ignore[assignment,misc]

from lecture_agents.config.constants import PIPELINE_OUTPUT_DIR
from lecture_agents.exceptions import CompilationError
from lecture_agents.schemas.compiler_output import (
    BookOutput,
    Chapter,
    CompilationReport,
    GlossarySection,
    IndexSection,
    SourceReference,
)
from lecture_agents.schemas.enrichment_output import EnrichedNotes
from lecture_agents.schemas.transcript_output import TranscriptOutput
from lecture_agents.tools.chapter_organizer import organize_chapters
from lecture_agents.tools.glossary_builder import compile_glossary
from lecture_agents.tools.index_builder import build_theme_index, build_verse_index
from lecture_agents.tools.markdown_formatter import (
    format_back_matter,
    format_chapter_markdown,
    format_front_matter,
)

logger = logging.getLogger(__name__)


def run_compiler_pipeline(
    enriched_notes_list: list[EnrichedNotes],
    transcript_outputs: list[TranscriptOutput],
    title: str = "Lecture Notes",
    output_dir: str = PIPELINE_OUTPUT_DIR,
    mode: str = "single",
    speaker: Optional[str] = None,
    original_urls: Optional[list[str]] = None,
) -> BookOutput:
    """
    Run the deterministic compiler pipeline.

    Steps:
    1. Organize enriched notes into chapters
    2. Format each chapter as Markdown with verse annotations
    3. Compile glossary across all chapters
    4. Build verse and thematic indices
    5. Generate front matter and back matter
    6. Assemble full book Markdown
    7. Write to output directory

    Args:
        enriched_notes_list: List of EnrichedNotes (one per source).
        transcript_outputs: List of TranscriptOutput (parallel).
        title: Book title.
        output_dir: Directory for output files.
        mode: "single" or "multi".
        speaker: Speaker name.

    Returns:
        Validated BookOutput.
    """
    if not enriched_notes_list:
        raise CompilationError("No enriched notes to compile")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Convert to dicts for tool functions
    enriched_dicts = [e.model_dump() for e in enriched_notes_list]
    transcript_dicts = [t.model_dump() for t in transcript_outputs]

    # Step 1: Organize chapters
    logger.info("Step 1: Organizing chapters (mode=%s)", mode)
    chapter_dicts = organize_chapters(enriched_dicts, transcript_dicts, mode=mode)

    if not chapter_dicts:
        raise CompilationError("No chapters could be organized")

    # Step 2: Collect all verifications for verse block rendering
    all_verifications = []
    for enriched in enriched_dicts:
        all_verifications.extend(enriched.get("verifications", []))

    # Step 3: Format each chapter as Markdown
    logger.info("Step 2: Formatting %d chapters", len(chapter_dicts))
    chapters: list[Chapter] = []
    for ch in chapter_dicts:
        ch_markdown = format_chapter_markdown(ch, all_verifications)
        chapters.append(Chapter(
            number=ch["number"],
            title=ch["title"],
            content_markdown=ch_markdown,
            source_url=ch.get("source_url"),
            duration_seconds=ch.get("duration_seconds"),
            verse_references=ch.get("references", []),
            themes=ch.get("themes", []),
        ))

    # Step 4: Compile glossary
    logger.info("Step 3: Compiling glossary")
    glossary_entries = compile_glossary(enriched_dicts)
    glossary = None
    if glossary_entries:
        glossary = GlossarySection(
            entries=glossary_entries,
            total_entries=len(glossary_entries),
        )

    # Step 5: Build indices
    logger.info("Step 4: Building indices")
    verse_idx = build_verse_index(chapter_dicts)
    theme_idx = build_theme_index(chapter_dicts)
    index = IndexSection(verse_index=verse_idx, theme_index=theme_idx)

    # Step 6: Source references
    source_refs = []
    for i, transcript in enumerate(transcript_outputs, 1):
        # Use original URL if available, otherwise fall back to local audio path
        url = transcript.source_audio
        if original_urls and i <= len(original_urls):
            url = original_urls[i - 1]
        source_refs.append(SourceReference(
            order=i,
            title=title,
            url=url,
            duration_seconds=transcript.duration_seconds,
        ))

    # Step 7: Generate front and back matter
    logger.info("Step 5: Generating front and back matter")
    front_matter = format_front_matter(
        title=title,
        speaker=speaker,
        source_references=[r.model_dump() for r in source_refs],
    )
    back_matter = format_back_matter(
        glossary_entries=glossary_entries,
        verse_index=verse_idx,
        theme_index=theme_idx,
        source_references=[r.model_dump() for r in source_refs],
    )

    # Step 8: Assemble full book
    full_parts = [front_matter]
    for ch in chapters:
        full_parts.append(ch.content_markdown)
    full_parts.append(back_matter)
    full_book = "\n\n".join(full_parts)

    # Write to file — use title as filename
    safe_name = re.sub(r"[^\w\s-]", "", title).strip().replace(" ", "_")
    output_path = str(Path(output_dir) / f"{safe_name}.md")
    Path(output_path).write_text(full_book, encoding="utf-8")
    logger.info("Book written to: %s", output_path)

    # Build report
    total_words = len(full_book.split())
    all_refs = set()
    for ch in chapter_dicts:
        all_refs.update(ch.get("references", []))

    verified_count = sum(
        1 for v in all_verifications
        if v.get("status") in ("verified", "cache_only")
    )
    unverified_count = sum(
        len(e.unverified_references) for e in enriched_notes_list
    )

    warnings = []
    if total_words < 1000:
        warnings.append("Book is unusually short (< 1000 words)")
    if unverified_count > 0:
        warnings.append(f"{unverified_count} verse references could not be verified")

    report = CompilationReport(
        total_chapters=len(chapters),
        total_words=total_words,
        total_verses_referenced=len(all_refs),
        total_glossary_entries=len(glossary_entries),
        verified_verse_count=verified_count,
        unverified_verse_count=unverified_count,
        compilation_strategy="single" if mode == "single" else "unified",
        warnings=warnings,
    )

    summary = (
        f"Compiled '{title}': {len(chapters)} chapters, "
        f"{total_words} words, {len(all_refs)} verse references "
        f"({verified_count} verified). "
        f"Output: {output_path}"
    )

    return BookOutput(
        title=title,
        speaker=speaker,
        chapters=chapters,
        glossary=glossary,
        index=index,
        source_references=source_refs,
        front_matter_markdown=front_matter,
        back_matter_markdown=back_matter,
        full_book_markdown=full_book,
        report=report,
        output_path=output_path,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# CrewAI Agentic Mode
# ---------------------------------------------------------------------------


def build_compiler_agent() -> Agent:
    """Create the Compiler Agent. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode.")
    return Agent(
        role="Book Compiler and Markdown Formatter",
        goal=(
            "Assemble enriched lecture notes into a professionally structured "
            "Markdown book with chapters, verse annotations, glossary, "
            "scripture index, and source references."
        ),
        backstory=(
            "You are an expert book compiler who transforms lecture transcripts "
            "into beautiful, readable publications. You respect the speaker's "
            "voice while adding scholarly apparatus — verse blocks, glossary, "
            "and indices — that enhance the reader's study."
        ),
        verbose=True,
    )
