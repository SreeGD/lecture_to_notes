"""
Agent 03: Enrichment Agent — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the Enrichment Agent. Defines EnrichedNotes,
Reference, VerificationResult, GlossaryEntry, and ThematicIndex.

CRITICAL: All verses must be verified against vedabase.io.
Unverified references are excluded from enriched output.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator


class Reference(BaseModel):
    """A scripture reference identified in the transcript."""

    scripture: str = Field(..., min_length=1, description="e.g. BG, SB, CC")
    chapter: str = Field(default="", description="Chapter or canto.chapter (empty for NOI/ISO)")
    verse: str = Field(..., min_length=1, description="Verse number or range")
    canonical_ref: str = Field(
        ..., min_length=3,
        description="Canonical form e.g. 'BG 2.47', 'SB 1.2.6', 'CC Adi 1.1'",
    )
    segment_index: int = Field(..., ge=0, description="Index into transcript segments")
    context_text: str = Field(
        ..., min_length=5,
        description="Surrounding text from transcript where reference appears",
    )


class VerificationResult(BaseModel):
    """Result of verifying a reference against vedabase.io."""

    reference: Reference = Field(...)
    status: Literal["verified", "not_found", "partial_match", "cache_only"] = Field(...)
    vedabase_url: Optional[str] = Field(None, description="Full vedabase.io URL")
    devanagari: Optional[str] = Field(None, description="Sanskrit in Devanagari")
    verse_text: Optional[str] = Field(None, description="IAST transliteration")
    synonyms: Optional[str] = Field(None, description="Prabhupada's word-for-word")
    translation: Optional[str] = Field(None, description="Prabhupada's translation")
    purport_excerpt: Optional[str] = Field(None, description="First ~500 chars of purport")
    cross_refs_in_purport: list[str] = Field(
        default_factory=list,
        description="Other verses cited within this purport",
    )
    error: Optional[str] = Field(None)

    @model_validator(mode="after")
    def validate_verified_has_content(self) -> VerificationResult:
        if self.status == "verified" and not self.translation:
            raise ValueError("Verified reference must include Prabhupada's translation")
        if self.status == "verified" and not self.vedabase_url:
            raise ValueError("Verified reference must include vedabase.io URL")
        return self


class GlossaryEntry(BaseModel):
    """A Sanskrit/domain term for the book glossary."""

    term: str = Field(..., min_length=1)
    definition: str = Field(..., min_length=5, description="From Prabhupada's books")
    category: Literal["sanskrit", "bengali", "philosophical", "historical", "general"] = Field(...)
    source: Optional[str] = Field(None, description="Source of definition e.g. 'BG Glossary'")
    first_occurrence_segment: Optional[int] = Field(None, ge=0)


class ThematicTag(BaseModel):
    """A thematic tag for content organization."""

    tag: str = Field(..., min_length=1, description="Theme name")
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: str = Field(..., min_length=5, description="Why this theme was identified")
    related_references: list[str] = Field(
        default_factory=list,
        description="Canonical refs supporting this theme",
    )


class ThematicIndex(BaseModel):
    """Index of themes identified in the lecture."""

    themes: list[ThematicTag] = Field(default_factory=list)
    primary_topic: str = Field(..., min_length=3, description="Main topic of the lecture")
    scripture_focus: Optional[str] = Field(
        None, description="Primary scripture discussed e.g. 'Bhagavad-gita'",
    )


class EnrichedNotes(BaseModel):
    """Top-level output contract for the Enrichment Agent."""

    source_transcript: str = Field(..., min_length=1, description="Path to transcript")
    transcript_text: str = Field(..., min_length=20, description="Original transcript text")
    references_found: list[Reference] = Field(default_factory=list)
    verifications: list[VerificationResult] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    thematic_index: ThematicIndex = Field(...)
    enrichment_source: Literal["llm", "regex", "hybrid"] = Field(default="hybrid")
    verification_rate: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Fraction of references successfully verified",
    )
    unverified_references: list[Reference] = Field(
        default_factory=list,
        description="References that could not be verified — excluded from annotations",
    )
    summary: str = Field(..., min_length=10)
    enriched_markdown: Optional[str] = Field(
        None,
        description="LLM-generated 15-section enriched notes in markdown format",
    )
    saranagathi_mapping: Optional[dict] = Field(
        None,
        description="SARANAGATHI classification mapping from LLM enrichment",
    )

    @model_validator(mode="after")
    def validate_all_refs_have_verification(self) -> EnrichedNotes:
        """Every found reference must have a verification attempt."""
        ref_keys = {r.canonical_ref for r in self.references_found}
        ver_keys = {v.reference.canonical_ref for v in self.verifications}
        unver_keys = {r.canonical_ref for r in self.unverified_references}
        covered = ver_keys | unver_keys
        missing = ref_keys - covered
        if missing:
            raise ValueError(
                f"References without verification attempt: {missing}"
            )
        return self

    @model_validator(mode="after")
    def compute_verification_rate(self) -> EnrichedNotes:
        """Auto-compute verification rate from results."""
        total = len(self.references_found)
        if total > 0:
            verified = sum(
                1 for v in self.verifications
                if v.status in ("verified", "cache_only")
            )
            self.verification_rate = round(verified / total, 4)
        return self
