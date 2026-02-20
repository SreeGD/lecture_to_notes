"""
Enrichment Tool: Purpose-driven transcript chunking.

Splits long transcripts into meaningful chunks based on temporal gaps,
speaker transitions, and verse reference boundaries. Each chunk is
processed independently by the LLM enrichment generator, then merged.

Only activates for transcripts exceeding CHUNK_ACTIVATION_THRESHOLD_TOKENS.
Short transcripts pass through as a single chunk (backward compatible).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field

from lecture_agents.config.constants import (
    CHUNK_ACTIVATION_THRESHOLD_TOKENS,
    CHUNK_GAP_THRESHOLD_SECONDS,
    CHUNK_MAX_TOKENS,
    CHUNK_MIN_TOKENS,
)

logger = logging.getLogger(__name__)

_TOKENS_PER_WORD = 1.3


@dataclass
class TranscriptChunk:
    """A purposeful segment of the transcript for independent enrichment."""

    chunk_index: int
    text: str
    segments: list[dict]
    references: list[dict]  # Refs whose segment_index falls in this chunk
    verified_verses: list[dict]  # Matching verified verse data
    start_time: float
    end_time: float
    start_segment_index: int
    end_segment_index: int  # exclusive
    estimated_tokens: int
    themes: list[str] = field(default_factory=list)  # Scripture types present


def chunk_transcript_by_purpose(
    segments: list[dict],
    full_text: str,
    references: list[dict],
    verified_verses: list[dict],
    min_chunk_tokens: int = CHUNK_MIN_TOKENS,
    max_chunk_tokens: int = CHUNK_MAX_TOKENS,
    activation_threshold: int = CHUNK_ACTIVATION_THRESHOLD_TOKENS,
) -> list[TranscriptChunk]:
    """
    Split a transcript into purposeful chunks for independent LLM enrichment.

    Strategy:
    1. Estimate total tokens. If below activation_threshold, return single chunk.
    2. Find natural break points using temporal gaps, speaker transitions,
       and verse reference boundaries.
    3. Score and select breaks producing chunks within [min, max] token range.
    4. Assign each reference and its verified verse data to the appropriate chunk.

    Args:
        segments: List of segment dicts (from TranscriptOutput.segments dumped).
        full_text: Full transcript text.
        references: All identified reference dicts.
        verified_verses: All verified verse data dicts.
        min_chunk_tokens: Minimum tokens per chunk.
        max_chunk_tokens: Maximum tokens per chunk.
        activation_threshold: Only chunk if total exceeds this.

    Returns:
        List of TranscriptChunk objects, sorted by chunk_index.
    """
    if not segments:
        return []

    total_tokens = int(len(full_text.split()) * _TOKENS_PER_WORD)

    # Below threshold: return everything as a single chunk
    if total_tokens <= activation_threshold:
        logger.info(
            "Transcript below chunking threshold (~%d tokens <= %d); single chunk",
            total_tokens, activation_threshold,
        )
        return [_build_single_chunk(segments, full_text, references, verified_verses)]

    # Build a set of segment indices that contain verse references
    ref_segment_indices = {r.get("segment_index", -1) for r in references}

    # Find and score break candidates
    break_candidates = _find_break_candidates(segments, ref_segment_indices)

    # Select breaks that produce well-sized chunks
    selected_breaks = _select_breaks(
        segments, break_candidates, min_chunk_tokens, max_chunk_tokens,
    )

    # Build chunks from selected breaks
    chunks = _build_chunks(
        segments, selected_breaks, references, verified_verses,
    )

    logger.info(
        "Split transcript into %d chunks (~%d total tokens, %d-%d tokens/chunk)",
        len(chunks), total_tokens,
        min(c.estimated_tokens for c in chunks),
        max(c.estimated_tokens for c in chunks),
    )

    return chunks


def group_verses_by_scripture(
    verified_verses: list[dict],
) -> dict[str, list[dict]]:
    """
    Group verified verses by their scripture type.

    Returns:
        Dict mapping scripture abbreviation (BG, SB, CC, etc.) to list of
        verse dicts. Ordered with most common scriptures first.
    """
    groups: dict[str, list[dict]] = defaultdict(list)

    for v in verified_verses:
        canonical = v.get("canonical_ref", "")
        parts = canonical.split()
        scripture = parts[0] if parts else "OTHER"
        groups[scripture].append(v)

    # Sort groups: BG first (most common), then alphabetically
    priority = ["BG", "SB", "CC", "NOI", "ISO", "BS"]
    ordered: dict[str, list[dict]] = {}
    for key in priority:
        if key in groups:
            ordered[key] = groups.pop(key)
    for key in sorted(groups.keys()):
        ordered[key] = groups[key]

    return ordered


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_single_chunk(
    segments: list[dict],
    full_text: str,
    references: list[dict],
    verified_verses: list[dict],
) -> TranscriptChunk:
    """Build a single chunk containing the entire transcript."""
    start_time = segments[0].get("start", 0.0) if segments else 0.0
    end_time = segments[-1].get("end", 0.0) if segments else 0.0
    themes = list({
        r.get("canonical_ref", "").split()[0]
        for r in references
        if r.get("canonical_ref", "").split()
    })
    return TranscriptChunk(
        chunk_index=0,
        text=full_text,
        segments=segments,
        references=references,
        verified_verses=verified_verses,
        start_time=start_time,
        end_time=end_time,
        start_segment_index=0,
        end_segment_index=len(segments),
        estimated_tokens=int(len(full_text.split()) * _TOKENS_PER_WORD),
        themes=themes,
    )


@dataclass
class _BreakCandidate:
    """A potential break point between segments."""

    segment_index: int  # Break BEFORE this segment
    score: float
    reason: str


def _find_break_candidates(
    segments: list[dict],
    ref_segment_indices: set[int],
) -> list[_BreakCandidate]:
    """Find and score potential break points in the segment sequence."""
    candidates: list[_BreakCandidate] = []

    for i in range(1, len(segments)):
        prev = segments[i - 1]
        curr = segments[i]

        gap = curr.get("start", 0.0) - prev.get("end", 0.0)
        speaker_change = (
            prev.get("speaker") is not None
            and curr.get("speaker") is not None
            and prev.get("speaker") != curr.get("speaker")
        )
        # Break near a reference boundary (transition from non-ref to ref segment)
        ref_boundary = (
            i in ref_segment_indices and (i - 1) not in ref_segment_indices
        ) or (
            (i - 1) in ref_segment_indices and i not in ref_segment_indices
        )

        score = 0.0
        reasons = []

        if gap >= CHUNK_GAP_THRESHOLD_SECONDS:
            score += gap * 1.0
            reasons.append(f"gap={gap:.1f}s")

        if speaker_change:
            score += 2.0
            reasons.append("speaker_change")

        if ref_boundary:
            score += 1.5
            reasons.append("ref_boundary")

        if score > 0:
            candidates.append(_BreakCandidate(
                segment_index=i,
                score=score,
                reason="+".join(reasons),
            ))

    return candidates


def _estimate_segment_range_tokens(segments: list[dict], start: int, end: int) -> int:
    """Estimate token count for a range of segments."""
    text = " ".join(s.get("text", "") for s in segments[start:end])
    return int(len(text.split()) * _TOKENS_PER_WORD)


def _select_breaks(
    segments: list[dict],
    candidates: list[_BreakCandidate],
    min_tokens: int,
    max_tokens: int,
) -> list[int]:
    """
    Greedily select break points that produce chunks within [min, max] tokens.

    Returns a sorted list of segment indices where breaks should occur.
    Always includes 0 (start) implicitly.
    """
    if not candidates:
        return []

    # Sort by score descending
    sorted_candidates = sorted(candidates, key=lambda c: c.score, reverse=True)

    # Start with all candidate positions
    selected: set[int] = set()

    # Add candidates greedily, checking chunk sizes
    for candidate in sorted_candidates:
        trial = sorted(selected | {candidate.segment_index})
        # Check all chunks formed by these breaks
        endpoints = [0] + trial + [len(segments)]
        all_ok = True
        for a, b in zip(endpoints, endpoints[1:]):
            tokens = _estimate_segment_range_tokens(segments, a, b)
            if tokens < min_tokens:
                all_ok = False
                break
        if all_ok:
            selected.add(candidate.segment_index)

    # Verify no chunk exceeds max_tokens; if so, force-split
    result = sorted(selected)
    endpoints = [0] + result + [len(segments)]
    final_breaks: list[int] = []

    for a, b in zip(endpoints, endpoints[1:]):
        tokens = _estimate_segment_range_tokens(segments, a, b)
        if tokens > max_tokens and (b - a) > 2:
            # Force-split at midpoint
            mid = a + (b - a) // 2
            final_breaks.append(mid)
        # Keep existing breaks
        if b != len(segments) and b in selected:
            final_breaks.append(b)

    return sorted(set(final_breaks))


def _build_chunks(
    segments: list[dict],
    breaks: list[int],
    references: list[dict],
    verified_verses: list[dict],
) -> list[TranscriptChunk]:
    """Build TranscriptChunk objects from break points."""
    # Build canonical_ref -> verse data lookup
    verse_lookup = {v.get("canonical_ref"): v for v in verified_verses}

    endpoints = [0] + breaks + [len(segments)]
    chunks: list[TranscriptChunk] = []

    for idx, (start, end) in enumerate(zip(endpoints, endpoints[1:])):
        chunk_segments = segments[start:end]
        chunk_text = " ".join(s.get("text", "") for s in chunk_segments)

        # Assign references whose segment_index falls in [start, end)
        chunk_refs = [
            r for r in references
            if start <= r.get("segment_index", -1) < end
        ]

        # Assign matching verified verses
        chunk_canonical_refs = {r.get("canonical_ref") for r in chunk_refs}
        chunk_verses = [
            v for v in verified_verses
            if v.get("canonical_ref") in chunk_canonical_refs
        ]

        # Scripture themes in this chunk
        themes = list({
            r.get("canonical_ref", "").split()[0]
            for r in chunk_refs
            if r.get("canonical_ref", "").split()
        })

        start_time = chunk_segments[0].get("start", 0.0) if chunk_segments else 0.0
        end_time = chunk_segments[-1].get("end", 0.0) if chunk_segments else 0.0

        chunks.append(TranscriptChunk(
            chunk_index=idx,
            text=chunk_text,
            segments=chunk_segments,
            references=chunk_refs,
            verified_verses=chunk_verses,
            start_time=start_time,
            end_time=end_time,
            start_segment_index=start,
            end_segment_index=end,
            estimated_tokens=int(len(chunk_text.split()) * _TOKENS_PER_WORD),
            themes=themes,
        ))

    return chunks
