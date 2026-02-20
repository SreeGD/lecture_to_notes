"""
Agent 3.5: Validation Agent — Output Schema
Lecture-to-Notes Pipeline v1.0

Output contract for the Validation Agent. Defines ValidationReport
and CheckResult for transcription and enrichment quality checks.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator


class CheckSeverity(str, Enum):
    """Severity level of a validation check."""

    CRITICAL = "critical"  # Fails pipeline
    WARNING = "warning"    # Logged, pipeline continues


class CheckResult(BaseModel):
    """Result of a single validation check."""

    check_name: str = Field(..., min_length=1, description="Check identifier")
    passed: bool = Field(..., description="Whether the check passed")
    severity: CheckSeverity = Field(..., description="Impact level if failed")
    message: str = Field(..., min_length=1, description="Human-readable result")
    details: dict = Field(default_factory=dict, description="Structured diagnostic data")


class ValidationReport(BaseModel):
    """Top-level output contract for the Validation Agent."""

    transcript_checks: list[CheckResult] = Field(default_factory=list)
    enrichment_checks: list[CheckResult] = Field(default_factory=list)
    overall_pass: bool = Field(..., description="True if no CRITICAL failures")
    critical_failures: int = Field(default=0, ge=0)
    warnings: int = Field(default=0, ge=0)
    summary: str = Field(..., min_length=1, description="Human-readable summary")

    @model_validator(mode="after")
    def compute_counts(self) -> ValidationReport:
        """Auto-compute critical_failures and warnings from check results."""
        all_checks = self.transcript_checks + self.enrichment_checks
        self.critical_failures = sum(
            1 for c in all_checks
            if not c.passed and c.severity == CheckSeverity.CRITICAL
        )
        self.warnings = sum(
            1 for c in all_checks
            if not c.passed and c.severity == CheckSeverity.WARNING
        )
        self.overall_pass = self.critical_failures == 0
        return self
