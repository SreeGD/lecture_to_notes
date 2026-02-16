"""
Level 1: Schema validation tests for Agent 04 (Compiler).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from lecture_agents.schemas.compiler_output import (
    BookOutput,
    Chapter,
    CompilationReport,
    GlossarySection,
    IndexSection,
    SourceReference,
)


def _make_chapter(**overrides) -> Chapter:
    defaults = {
        "number": 1,
        "title": "The Science of Self-Realization",
        "content_markdown": "# Chapter 1: The Science of Self-Realization\n\nContent here.",
    }
    return Chapter(**(defaults | overrides))


def _make_report(**overrides) -> CompilationReport:
    defaults = {
        "total_chapters": 1,
        "total_words": 5000,
    }
    return CompilationReport(**(defaults | overrides))


def _make_book(**overrides) -> BookOutput:
    defaults = {
        "title": "Lecture Notes on Bhagavad-gita",
        "chapters": [_make_chapter()],
        "front_matter_markdown": "# Lecture Notes\n\nFront matter content.",
        "full_book_markdown": "# Full Book\n\nThis is the complete book content with sufficient length for validation.",
        "report": _make_report(),
        "output_path": "/output/final_book.md",
        "summary": "Compiled 1 chapter, 5000 words.",
    }
    return BookOutput(**(defaults | overrides))


@pytest.mark.schema
class TestChapter:

    def test_valid_chapter(self):
        c = _make_chapter()
        assert c.number == 1

    def test_title_min_length(self):
        with pytest.raises(ValidationError):
            _make_chapter(title="ab")

    def test_content_min_length(self):
        with pytest.raises(ValidationError):
            _make_chapter(content_markdown="short")

    def test_number_positive(self):
        with pytest.raises(ValidationError):
            _make_chapter(number=0)


@pytest.mark.schema
class TestGlossarySection:

    def test_valid_glossary(self):
        g = GlossarySection(
            entries=[{"term": "bhakti", "definition": "devotion"}],
            total_entries=1,
        )
        assert g.total_entries == 1

    def test_count_mismatch(self):
        with pytest.raises(ValidationError):
            GlossarySection(
                entries=[{"term": "a", "definition": "b"}],
                total_entries=5,
            )


@pytest.mark.schema
class TestCompilationReport:

    def test_valid_report(self):
        r = _make_report()
        assert r.total_chapters == 1

    def test_strategy_enum(self):
        for s in ["single", "unified", "anthology"]:
            r = _make_report(compilation_strategy=s)
            assert r.compilation_strategy == s


@pytest.mark.schema
class TestBookOutput:

    def test_valid_book(self):
        b = _make_book()
        assert b.title == "Lecture Notes on Bhagavad-gita"

    def test_chapter_count_mismatch(self):
        with pytest.raises(ValidationError, match="chapters length"):
            _make_book(
                chapters=[_make_chapter(), _make_chapter(number=2)],
                report=_make_report(total_chapters=1),
            )

    def test_full_markdown_min_length(self):
        with pytest.raises(ValidationError):
            _make_book(full_book_markdown="short")

    def test_multi_chapter_book(self):
        chs = [
            _make_chapter(number=1, title="Chapter One Title"),
            _make_chapter(number=2, title="Chapter Two Title"),
        ]
        b = _make_book(
            chapters=chs,
            report=_make_report(total_chapters=2),
        )
        assert len(b.chapters) == 2

    def test_source_reference(self):
        sr = SourceReference(order=1, title="Lecture 1", url="https://example.com/audio.mp3")
        assert sr.status == "success"
