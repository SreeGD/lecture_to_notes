"""
Agent 3.5: Validation Agent
Lecture-to-Notes Pipeline v1.0

Deterministic quality gate that validates transcription and enrichment
outputs before compilation. Detects hallucination patterns, content
coherence issues, and enrichment inconsistencies.

No LLM required — all checks are rule-based.
"""

from __future__ import annotations

import logging
from collections import Counter

try:
    from crewai import Agent, Task
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    Agent = None  # type: ignore[assignment,misc]
    Task = None   # type: ignore[assignment,misc]

import re

from lecture_agents.config.constants import (
    VALIDATION_DURATION_MISMATCH_THRESHOLD,
    VALIDATION_LANGUAGE_INCONSISTENCY_THRESHOLD,
    VALIDATION_MARKDOWN_MIN_SECTIONS,
    VALIDATION_MARKDOWN_REPEAT_THRESHOLD,
    VALIDATION_MAX_SEGMENT_GAP_SECONDS,
    VALIDATION_MAX_SPECULATIVE_PHRASES,
    VALIDATION_MIN_AVG_CONFIDENCE,
    VALIDATION_MIN_VERIFICATION_RATE,
    VALIDATION_MIN_WORDS_PER_MINUTE,
    VALIDATION_SLIDING_REPETITION_THRESHOLD,
    VALIDATION_SLIDING_WINDOW_SIZE,
    VALIDATION_SPECULATIVE_PHRASES,
    VALIDATION_UNVERIFIED_REF_PATTERN,
)
from lecture_agents.exceptions import ValidationError
from lecture_agents.schemas.enrichment_output import EnrichedNotes
from lecture_agents.schemas.transcript_output import TranscriptOutput
from lecture_agents.schemas.validation_output import (
    CheckResult,
    CheckSeverity,
    ValidationReport,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Transcription checks
# ---------------------------------------------------------------------------


def _check_sliding_window_repetition(transcript: TranscriptOutput) -> CheckResult:
    """Detect repetition within sliding windows of segments."""
    segments = transcript.segments
    window = VALIDATION_SLIDING_WINDOW_SIZE

    if len(segments) < window:
        return CheckResult(
            check_name="sliding_window_repetition",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message=f"Skipped: only {len(segments)} segments (< window size {window})",
        )

    worst_ratio = 0.0
    worst_text = ""
    worst_pos = 0

    for i in range(len(segments) - window + 1):
        texts = [s.text.strip() for s in segments[i : i + window]]
        counts = Counter(texts)
        most_common_text, most_common_count = counts.most_common(1)[0]
        ratio = most_common_count / window
        if ratio > worst_ratio:
            worst_ratio = ratio
            worst_text = most_common_text
            worst_pos = i

    passed = worst_ratio <= VALIDATION_SLIDING_REPETITION_THRESHOLD

    return CheckResult(
        check_name="sliding_window_repetition",
        passed=passed,
        severity=CheckSeverity.CRITICAL,
        message=(
            f"OK: max repetition ratio {worst_ratio:.0%}"
            if passed
            else f"Repetition detected: '{worst_text[:80]}' repeated in "
            f"{worst_ratio:.0%} of window at position {worst_pos}"
        ),
        details={
            "worst_ratio": round(worst_ratio, 4),
            "worst_text": worst_text[:120],
            "worst_position": worst_pos,
            "threshold": VALIDATION_SLIDING_REPETITION_THRESHOLD,
        },
    )


def _check_content_density(transcript: TranscriptOutput) -> CheckResult:
    """Check if transcript has enough words relative to audio duration."""
    word_count = len(transcript.full_text.split())
    duration_minutes = transcript.duration_seconds / 60.0

    if duration_minutes < 0.5:
        return CheckResult(
            check_name="content_density",
            passed=True,
            severity=CheckSeverity.CRITICAL,
            message=f"Skipped: audio too short ({duration_minutes:.1f}min)",
        )

    words_per_minute = word_count / duration_minutes
    passed = words_per_minute >= VALIDATION_MIN_WORDS_PER_MINUTE

    return CheckResult(
        check_name="content_density",
        passed=passed,
        severity=CheckSeverity.CRITICAL,
        message=(
            f"OK: {words_per_minute:.0f} words/min ({word_count} words in {duration_minutes:.1f}min)"
            if passed
            else f"Low content density: {words_per_minute:.1f} words/min "
            f"({word_count} words in {duration_minutes:.1f}min). "
            f"Expected >= {VALIDATION_MIN_WORDS_PER_MINUTE:.0f} words/min."
        ),
        details={
            "words_per_minute": round(words_per_minute, 2),
            "word_count": word_count,
            "duration_minutes": round(duration_minutes, 2),
            "threshold": VALIDATION_MIN_WORDS_PER_MINUTE,
        },
    )


def _check_segment_gaps(transcript: TranscriptOutput) -> CheckResult:
    """Detect large unexplained gaps between consecutive segments."""
    segments = transcript.segments
    if len(segments) < 2:
        return CheckResult(
            check_name="segment_gap_analysis",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: fewer than 2 segments",
        )

    gaps: list[dict] = []
    for i in range(1, len(segments)):
        gap = segments[i].start - segments[i - 1].end
        if gap > VALIDATION_MAX_SEGMENT_GAP_SECONDS:
            gaps.append({
                "position": i,
                "gap_seconds": round(gap, 2),
                "from_end": round(segments[i - 1].end, 2),
                "to_start": round(segments[i].start, 2),
            })

    passed = len(gaps) == 0

    return CheckResult(
        check_name="segment_gap_analysis",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            "OK: no large gaps detected"
            if passed
            else f"{len(gaps)} gap(s) > {VALIDATION_MAX_SEGMENT_GAP_SECONDS}s detected"
        ),
        details={
            "gap_count": len(gaps),
            "gaps": gaps[:10],  # Limit to first 10
            "threshold_seconds": VALIDATION_MAX_SEGMENT_GAP_SECONDS,
        },
    )


def _check_confidence(transcript: TranscriptOutput) -> CheckResult:
    """Flag low average segment confidence."""
    confidences = [
        s.confidence for s in transcript.segments if s.confidence is not None
    ]

    if not confidences:
        return CheckResult(
            check_name="low_confidence",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no confidence scores available",
        )

    avg_confidence = sum(confidences) / len(confidences)
    passed = avg_confidence >= VALIDATION_MIN_AVG_CONFIDENCE

    return CheckResult(
        check_name="low_confidence",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: average confidence {avg_confidence:.2f}"
            if passed
            else f"Low confidence: average {avg_confidence:.2f} "
            f"(threshold {VALIDATION_MIN_AVG_CONFIDENCE})"
        ),
        details={
            "average_confidence": round(avg_confidence, 4),
            "segments_with_confidence": len(confidences),
            "threshold": VALIDATION_MIN_AVG_CONFIDENCE,
        },
    )


def _check_language_consistency(transcript: TranscriptOutput) -> CheckResult:
    """Flag segments with unexpected language codes."""
    primary = transcript.language
    segments_with_lang = [
        s for s in transcript.segments if s.language is not None
    ]

    if not segments_with_lang:
        return CheckResult(
            check_name="language_consistency",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no per-segment language data",
        )

    mismatches = [s for s in segments_with_lang if s.language != primary]
    mismatch_ratio = len(mismatches) / len(segments_with_lang)
    passed = mismatch_ratio <= VALIDATION_LANGUAGE_INCONSISTENCY_THRESHOLD

    return CheckResult(
        check_name="language_consistency",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: {mismatch_ratio:.0%} language mismatch"
            if passed
            else f"Language inconsistency: {len(mismatches)}/{len(segments_with_lang)} "
            f"segments ({mismatch_ratio:.0%}) differ from primary '{primary}'"
        ),
        details={
            "primary_language": primary,
            "mismatch_count": len(mismatches),
            "mismatch_ratio": round(mismatch_ratio, 4),
            "threshold": VALIDATION_LANGUAGE_INCONSISTENCY_THRESHOLD,
        },
    )


# ---------------------------------------------------------------------------
# Enrichment checks
# ---------------------------------------------------------------------------


def _check_verification_rate(enriched: EnrichedNotes) -> CheckResult:
    """Check if enough references were verified against vedabase.io."""
    if not enriched.references_found:
        return CheckResult(
            check_name="verification_rate",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no references found to verify",
        )

    passed = enriched.verification_rate >= VALIDATION_MIN_VERIFICATION_RATE

    return CheckResult(
        check_name="verification_rate",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: {enriched.verification_rate:.0%} verification rate "
            f"({len(enriched.verifications)}/{len(enriched.references_found)})"
            if passed
            else f"Low verification rate: {enriched.verification_rate:.0%} "
            f"({len(enriched.verifications)} verified of "
            f"{len(enriched.references_found)} found). "
            f"Threshold: {VALIDATION_MIN_VERIFICATION_RATE:.0%}"
        ),
        details={
            "verification_rate": enriched.verification_rate,
            "verified_count": len(enriched.verifications),
            "total_found": len(enriched.references_found),
            "unverified_count": len(enriched.unverified_references),
            "threshold": VALIDATION_MIN_VERIFICATION_RATE,
        },
    )


def _check_cross_reference_consistency(enriched: EnrichedNotes) -> CheckResult:
    """Check that thematic index references exist in verifications."""
    verified_refs = {v.reference.canonical_ref for v in enriched.verifications}

    orphaned: list[str] = []
    for theme in enriched.thematic_index.themes:
        for ref in theme.related_references:
            if ref not in verified_refs and verified_refs:
                orphaned.append(ref)

    passed = len(orphaned) == 0

    return CheckResult(
        check_name="cross_reference_consistency",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            "OK: all thematic references are verified"
            if passed
            else f"{len(orphaned)} thematic reference(s) not in verified set: "
            f"{', '.join(orphaned[:5])}"
        ),
        details={
            "orphaned_references": orphaned[:20],
            "orphaned_count": len(orphaned),
            "verified_ref_count": len(verified_refs),
        },
    )


def _check_enriched_markdown_repetition(enriched: EnrichedNotes) -> CheckResult:
    """Check enriched markdown for repeated paragraph blocks."""
    if not enriched.enriched_markdown:
        return CheckResult(
            check_name="enriched_markdown_repetition",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no enriched markdown present",
        )

    paragraphs = [
        p.strip()
        for p in enriched.enriched_markdown.split("\n\n")
        if p.strip() and len(p.strip()) > 20
    ]

    if len(paragraphs) < 4:
        return CheckResult(
            check_name="enriched_markdown_repetition",
            passed=True,
            severity=CheckSeverity.WARNING,
            message=f"OK: only {len(paragraphs)} paragraphs",
        )

    counts = Counter(paragraphs)
    most_common_para, most_common_count = counts.most_common(1)[0]
    passed = most_common_count <= VALIDATION_MARKDOWN_REPEAT_THRESHOLD

    return CheckResult(
        check_name="enriched_markdown_repetition",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: max paragraph repetition {most_common_count}x"
            if passed
            else f"Markdown repetition: one paragraph repeated {most_common_count}x "
            f"(threshold {VALIDATION_MARKDOWN_REPEAT_THRESHOLD}x): "
            f"'{most_common_para[:80]}...'"
        ),
        details={
            "max_repetition": most_common_count,
            "repeated_text": most_common_para[:200],
            "total_paragraphs": len(paragraphs),
            "threshold": VALIDATION_MARKDOWN_REPEAT_THRESHOLD,
        },
    )


def _check_empty_enrichment(enriched: EnrichedNotes) -> CheckResult:
    """Warn if enrichment produced no useful output."""
    has_refs = len(enriched.references_found) > 0
    has_glossary = len(enriched.glossary) > 0
    has_markdown = enriched.enriched_markdown is not None

    passed = has_refs or has_glossary or has_markdown

    return CheckResult(
        check_name="empty_enrichment",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: {len(enriched.references_found)} refs, "
            f"{len(enriched.glossary)} glossary, "
            f"markdown={'yes' if has_markdown else 'no'}"
            if passed
            else "Empty enrichment: no references, glossary entries, or enriched markdown"
        ),
        details={
            "references_found": len(enriched.references_found),
            "glossary_entries": len(enriched.glossary),
            "has_markdown": has_markdown,
        },
    )


def _check_llm_speculative_content(enriched: EnrichedNotes) -> CheckResult:
    """Detect speculative or ungrounded philosophical claims in LLM output."""
    if not enriched.enriched_markdown:
        return CheckResult(
            check_name="llm_speculative_content",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no enriched markdown present",
        )

    markdown_lower = enriched.enriched_markdown.lower()
    found_phrases: list[str] = []
    for phrase in VALIDATION_SPECULATIVE_PHRASES:
        if phrase in markdown_lower:
            found_phrases.append(phrase)

    passed = len(found_phrases) <= VALIDATION_MAX_SPECULATIVE_PHRASES

    return CheckResult(
        check_name="llm_speculative_content",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: {len(found_phrases)} speculative phrase(s) detected"
            if passed
            else f"Speculative content detected: {len(found_phrases)} phrases found "
            f"(threshold {VALIDATION_MAX_SPECULATIVE_PHRASES}): "
            f"{', '.join(found_phrases[:5])}"
        ),
        details={
            "speculative_phrases_found": found_phrases,
            "count": len(found_phrases),
            "threshold": VALIDATION_MAX_SPECULATIVE_PHRASES,
        },
    )


def _check_unverified_refs_in_markdown(enriched: EnrichedNotes) -> CheckResult:
    """Check if enriched markdown references verses not in the verified set."""
    if not enriched.enriched_markdown:
        return CheckResult(
            check_name="unverified_refs_in_markdown",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no enriched markdown present",
        )

    verified_canonicals = {v.reference.canonical_ref for v in enriched.verifications}
    # Find all verse-like references in the markdown
    markdown_refs = set(re.findall(VALIDATION_UNVERIFIED_REF_PATTERN, enriched.enriched_markdown))
    # Exclude the [UNVERIFIED] tagged ones (they're expected)
    untagged_unverified = [
        ref for ref in markdown_refs
        if ref not in verified_canonicals
    ]

    passed = len(untagged_unverified) == 0

    return CheckResult(
        check_name="unverified_refs_in_markdown",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            "OK: all verse references in markdown are verified"
            if passed
            else f"{len(untagged_unverified)} verse reference(s) in markdown not in verified set: "
            f"{', '.join(untagged_unverified[:5])}"
        ),
        details={
            "untagged_unverified": untagged_unverified[:20],
            "count": len(untagged_unverified),
            "verified_count": len(verified_canonicals),
        },
    )


def _check_enriched_markdown_sections(enriched: EnrichedNotes) -> CheckResult:
    """Validate that enriched markdown contains expected section headers."""
    if not enriched.enriched_markdown:
        return CheckResult(
            check_name="enriched_markdown_sections",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no enriched markdown present",
        )

    # Count markdown heading lines (## or ###)
    headings = [
        line.strip()
        for line in enriched.enriched_markdown.split("\n")
        if line.strip().startswith("#")
    ]
    section_count = len(headings)
    passed = section_count >= VALIDATION_MARKDOWN_MIN_SECTIONS

    return CheckResult(
        check_name="enriched_markdown_sections",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: {section_count} sections found in enriched markdown"
            if passed
            else f"Enriched markdown has only {section_count} section(s) "
            f"(minimum {VALIDATION_MARKDOWN_MIN_SECTIONS})"
        ),
        details={
            "section_count": section_count,
            "headings": [h[:80] for h in headings[:20]],
            "threshold": VALIDATION_MARKDOWN_MIN_SECTIONS,
        },
    )


def _check_metadata_duration_consistency(
    transcript: TranscriptOutput,
    enriched: EnrichedNotes,
) -> CheckResult:
    """Check that segment timestamps are consistent with reported duration."""
    if not transcript.segments:
        return CheckResult(
            check_name="metadata_duration_consistency",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no segments",
        )

    last_segment_end = max(s.end for s in transcript.segments)
    reported_duration = transcript.duration_seconds

    if reported_duration <= 0:
        return CheckResult(
            check_name="metadata_duration_consistency",
            passed=True,
            severity=CheckSeverity.WARNING,
            message="Skipped: no duration reported",
        )

    mismatch = abs(last_segment_end - reported_duration) / reported_duration
    passed = mismatch <= VALIDATION_DURATION_MISMATCH_THRESHOLD

    return CheckResult(
        check_name="metadata_duration_consistency",
        passed=passed,
        severity=CheckSeverity.WARNING,
        message=(
            f"OK: segment end {last_segment_end:.0f}s vs reported {reported_duration:.0f}s "
            f"({mismatch:.0%} mismatch)"
            if passed
            else f"Duration mismatch: last segment ends at {last_segment_end:.0f}s but "
            f"reported duration is {reported_duration:.0f}s ({mismatch:.0%} mismatch, "
            f"threshold {VALIDATION_DURATION_MISMATCH_THRESHOLD:.0%})"
        ),
        details={
            "last_segment_end": round(last_segment_end, 2),
            "reported_duration": round(reported_duration, 2),
            "mismatch_ratio": round(mismatch, 4),
            "threshold": VALIDATION_DURATION_MISMATCH_THRESHOLD,
        },
    )


# ---------------------------------------------------------------------------
# Pipeline entry point
# ---------------------------------------------------------------------------


def _build_summary(checks: list[CheckResult]) -> str:
    """Build a human-readable summary from check results."""
    failed = [c for c in checks if not c.passed]
    if not failed:
        return f"All {len(checks)} validation checks passed."

    critical = [c for c in failed if c.severity == CheckSeverity.CRITICAL]
    warnings = [c for c in failed if c.severity == CheckSeverity.WARNING]

    parts: list[str] = []
    if critical:
        parts.append(
            f"{len(critical)} CRITICAL: "
            + "; ".join(c.check_name for c in critical)
        )
    if warnings:
        parts.append(
            f"{len(warnings)} WARNING: "
            + "; ".join(c.check_name for c in warnings)
        )

    return f"Validation failed — {'. '.join(parts)}."


def run_validation_pipeline(
    transcript: TranscriptOutput,
    enriched: EnrichedNotes,
) -> ValidationReport:
    """
    Agent 3.5: Validate transcription and enrichment quality.

    Runs deterministic quality checks on both outputs. Critical failures
    raise ValidationError to stop the pipeline. Warnings are logged.

    Args:
        transcript: Output from the Transcriber Agent.
        enriched: Output from the Enrichment Agent.

    Returns:
        ValidationReport with per-check results and overall verdict.

    Raises:
        ValidationError: If any CRITICAL check fails.
    """
    logger.info("Running validation checks on transcript and enrichment")
    all_checks: list[CheckResult] = []

    # Step 1: Transcription quality checks
    logger.info("Step 1: Transcription quality checks")
    all_checks.append(_check_sliding_window_repetition(transcript))
    all_checks.append(_check_content_density(transcript))
    all_checks.append(_check_segment_gaps(transcript))
    all_checks.append(_check_confidence(transcript))
    all_checks.append(_check_language_consistency(transcript))

    # Step 2: Enrichment quality checks
    logger.info("Step 2: Enrichment quality checks")
    all_checks.append(_check_verification_rate(enriched))
    all_checks.append(_check_cross_reference_consistency(enriched))
    all_checks.append(_check_enriched_markdown_repetition(enriched))
    all_checks.append(_check_empty_enrichment(enriched))
    all_checks.append(_check_llm_speculative_content(enriched))
    all_checks.append(_check_unverified_refs_in_markdown(enriched))
    all_checks.append(_check_enriched_markdown_sections(enriched))

    # Step 3: Cross-agent consistency checks
    logger.info("Step 3: Cross-agent consistency checks")
    all_checks.append(_check_metadata_duration_consistency(transcript, enriched))

    # Step 4: Build report
    transcript_check_names = {
        "sliding_window_repetition",
        "content_density",
        "segment_gap_analysis",
        "low_confidence",
        "language_consistency",
        "metadata_duration_consistency",
    }
    transcript_checks = [
        c for c in all_checks if c.check_name in transcript_check_names
    ]
    enrichment_checks = [
        c for c in all_checks if c.check_name not in transcript_check_names
    ]

    summary = _build_summary(all_checks)

    report = ValidationReport(
        transcript_checks=transcript_checks,
        enrichment_checks=enrichment_checks,
        overall_pass=True,  # Auto-computed by model_validator
        critical_failures=0,
        warnings=0,
        summary=summary,
    )

    # Log results
    for check in all_checks:
        level = logging.INFO if check.passed else logging.WARNING
        logger.log(level, "[%s] %s", check.check_name, check.message)

    logger.info(
        "Validation complete: %d critical, %d warnings, overall %s",
        report.critical_failures,
        report.warnings,
        "PASS" if report.overall_pass else "FAIL",
    )

    if not report.overall_pass:
        raise ValidationError(summary)

    return report


# ---------------------------------------------------------------------------
# CrewAI wrappers (optional, for agentic mode)
# ---------------------------------------------------------------------------


def build_validation_agent() -> Agent | None:
    """Build a CrewAI agent for validation (optional)."""
    if not HAS_CREWAI:
        return None
    return Agent(
        role="Quality Assurance Validator",
        goal=(
            "Validate transcription and enrichment outputs for hallucination "
            "patterns, content coherence, and scripture reference accuracy."
        ),
        backstory=(
            "You are a meticulous quality validator for the Lecture-to-Notes "
            "pipeline. You check transcriptions for Whisper hallucinations and "
            "enrichment outputs for consistency with vedabase.io-verified data. "
            "Your job is to catch problems before they reach the compilation stage."
        ),
        verbose=True,
    )


def build_validation_task(
    agent: Agent,
    transcript: TranscriptOutput,
    enriched: EnrichedNotes,
) -> Task | None:
    """Build a CrewAI task for validation (optional)."""
    if not HAS_CREWAI:
        return None
    return Task(
        description=(
            "Validate the transcription and enrichment outputs. "
            f"Transcript has {len(transcript.segments)} segments, "
            f"{transcript.duration_seconds:.0f}s audio. "
            f"Enrichment has {len(enriched.references_found)} references, "
            f"{enriched.verification_rate:.0%} verification rate."
        ),
        expected_output="ValidationReport with pass/fail for each check.",
        agent=agent,
    )
