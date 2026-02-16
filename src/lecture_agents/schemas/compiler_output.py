"""
Agent 04: Compiler Agent — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the Compiler Agent. Defines BookOutput,
Chapter, GlossarySection, IndexSection, and CompilationReport.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Chapter(BaseModel):
    """A single chapter in the compiled book."""

    number: int = Field(..., ge=1)
    title: str = Field(..., min_length=3)
    content_markdown: str = Field(..., min_length=20)
    source_url: Optional[str] = Field(None, description="Original audio URL")
    source_date: Optional[str] = Field(None, description="Lecture date")
    duration_seconds: Optional[float] = Field(None, ge=0)
    verse_references: list[str] = Field(
        default_factory=list,
        description="Canonical refs cited in this chapter",
    )
    themes: list[str] = Field(default_factory=list)
    application_items: list[str] = Field(
        default_factory=list,
        description="Read & Apply practical exercises",
    )


class GlossarySection(BaseModel):
    """The compiled glossary for the book."""

    entries: list[dict] = Field(..., min_length=1, description="term, definition, category")
    total_entries: int = Field(..., ge=1)

    @model_validator(mode="after")
    def validate_count(self) -> GlossarySection:
        if self.total_entries != len(self.entries):
            raise ValueError(
                f"total_entries ({self.total_entries}) must match "
                f"entries length ({len(self.entries)})"
            )
        return self


class IndexSection(BaseModel):
    """The compiled index (verse and thematic)."""

    verse_index: dict[str, list[int]] = Field(
        default_factory=dict,
        description="verse_ref -> list of chapter numbers",
    )
    theme_index: dict[str, list[int]] = Field(
        default_factory=dict,
        description="theme -> list of chapter numbers",
    )


class SourceReference(BaseModel):
    """A source reference entry for the back matter."""

    order: int = Field(..., ge=1)
    title: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    date: Optional[str] = Field(None)
    duration_seconds: Optional[float] = Field(None, ge=0)
    status: Literal["success", "failed"] = Field(default="success")


class CompilationReport(BaseModel):
    """Build report for the compilation."""

    total_chapters: int = Field(..., ge=1)
    total_words: int = Field(..., ge=0)
    total_verses_referenced: int = Field(default=0, ge=0)
    total_glossary_entries: int = Field(default=0, ge=0)
    verified_verse_count: int = Field(default=0, ge=0)
    unverified_verse_count: int = Field(default=0, ge=0)
    compilation_strategy: Literal["single", "unified", "anthology"] = Field(
        default="single",
    )
    compilation_source: Literal["deterministic", "llm_enhanced"] = Field(
        default="deterministic",
    )
    warnings: list[str] = Field(default_factory=list)


class BookOutput(BaseModel):
    """Top-level output contract for the Compiler Agent."""

    title: str = Field(..., min_length=3)
    subtitle: Optional[str] = Field(None)
    speaker: Optional[str] = Field(None)
    chapters: list[Chapter] = Field(..., min_length=1)
    glossary: Optional[GlossarySection] = Field(None)
    index: Optional[IndexSection] = Field(None)
    source_references: list[SourceReference] = Field(default_factory=list)
    front_matter_markdown: str = Field(..., min_length=10)
    back_matter_markdown: Optional[str] = Field(None)
    full_book_markdown: str = Field(..., min_length=50, description="Complete book as single Markdown")
    report: CompilationReport = Field(...)
    output_path: str = Field(..., min_length=1)
    summary: str = Field(..., min_length=10)

    @model_validator(mode="after")
    def validate_chapter_count(self) -> BookOutput:
        if len(self.chapters) != self.report.total_chapters:
            raise ValueError(
                f"chapters length ({len(self.chapters)}) must match "
                f"report.total_chapters ({self.report.total_chapters})"
            )
        return self
