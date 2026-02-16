"""
Agent 05: PDF Generator — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the PDF Generation Agent.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


class PDFOutput(BaseModel):
    """Top-level output contract for the PDF Generation Agent."""

    pdf_path: str = Field(..., min_length=5, description="Absolute path to generated PDF")
    title: str = Field(..., min_length=1, description="Book title used in PDF")
    total_pages: int = Field(..., ge=1)
    file_size_kb: float = Field(..., ge=0.0)
    has_cover_page: bool = Field(default=True)
    warnings: list[str] = Field(default_factory=list)
    summary: str = Field(..., min_length=10)

    @model_validator(mode="after")
    def validate_pdf_path(self) -> PDFOutput:
        if not self.pdf_path.endswith(".pdf"):
            raise ValueError(f"pdf_path must end with .pdf, got: {self.pdf_path}")
        return self
