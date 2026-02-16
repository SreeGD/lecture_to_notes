"""
Agent 05: PDF Generation Agent
Lecture-to-Notes Pipeline v1.0

Converts compiled book markdown into a publication-ready PDF with
Unicode IAST support, Vaishnava styling, and a title page.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

try:
    from crewai import Agent, Task
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    Agent = None  # type: ignore[assignment,misc]
    Task = None   # type: ignore[assignment,misc]

from lecture_agents.exceptions import PDFGenerationError
from lecture_agents.schemas.compiler_output import BookOutput
from lecture_agents.schemas.pdf_output import PDFOutput
from lecture_agents.tools.pdf_generator import PDFGenerateTool, generate_pdf

logger = logging.getLogger(__name__)


def run_pdf_pipeline(
    book_output: BookOutput,
    output_dir: str = "output",
    include_cover: bool = True,
) -> PDFOutput:
    """
    Run the PDF generation pipeline.

    Takes the compiled BookOutput from Agent 4 and generates a styled PDF.

    Args:
        book_output: Output from Compiler Agent.
        output_dir: Directory to write the PDF file.
        include_cover: Whether to include a title page.

    Returns:
        Validated PDFOutput.

    Raises:
        PDFGenerationError: If PDF generation fails.
    """
    pdf_filename = Path(book_output.output_path).stem + ".pdf"
    pdf_path = str(Path(output_dir) / pdf_filename)

    logger.info("Generating PDF: %s", pdf_path)

    result = generate_pdf(
        markdown_text=book_output.full_book_markdown,
        output_path=pdf_path,
        title=book_output.title,
        speaker=book_output.speaker,
        subtitle=book_output.subtitle,
        include_cover=include_cover,
    )

    if result.get("error"):
        raise PDFGenerationError(
            f"PDF generation failed: {result['error']}"
        )

    summary = (
        f"Generated PDF: {result['total_pages']} pages, "
        f"{result['file_size_kb']:.0f} KB. "
        f"Title: {book_output.title}."
    )

    return PDFOutput(
        pdf_path=result["pdf_path"],
        title=book_output.title,
        total_pages=result["total_pages"],
        file_size_kb=result["file_size_kb"],
        has_cover_page=result["has_cover_page"],
        warnings=result.get("warnings", []),
        summary=summary,
    )


# ---------------------------------------------------------------------------
# CrewAI Agentic Mode
# ---------------------------------------------------------------------------


def build_pdf_agent() -> Agent:
    """Create the PDF Generation Agent with tools. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode. pip install crewai[tools]")
    return Agent(
        role="Publication-Ready PDF Formatter",
        goal=(
            "Convert compiled Markdown book content into a beautifully styled PDF "
            "with proper Unicode IAST diacritical rendering, Vaishnava colour scheme, "
            "title page, and professional typography."
        ),
        backstory=(
            "You are a typesetting specialist for Vedic literature publications. "
            "You ensure that all Sanskrit transliterations render correctly with "
            "IAST diacritics (ā, ī, ū, ṛ, ṣ, ṇ, ś, etc.) and that the final PDF "
            "maintains the devotional mood of the content through appropriate styling, "
            "colours, and layout."
        ),
        tools=[
            PDFGenerateTool(),
        ],
        verbose=True,
    )


def build_pdf_task(agent: Agent, book_path: str, output_path: str) -> Task:
    """Create the PDF generation task. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode.")
    return Task(
        description=(
            f"Generate a publication-ready PDF from the compiled book at {book_path}. "
            f"Write the PDF to {output_path}. Include a title page with invocation, "
            "ensure all IAST diacriticals render correctly, and apply the Vaishnava "
            "colour scheme with dark red headings, gold accents, and cream backgrounds."
        ),
        expected_output=(
            "A PDFOutput JSON with the path to the generated PDF file, "
            "total page count, file size, and any rendering warnings."
        ),
        agent=agent,
    )
