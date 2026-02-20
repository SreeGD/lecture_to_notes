"""
Enrichment Tool: LLM-based generation of 15-section enriched class notes.

Uses Claude with the Master Prompt v6.0 to generate comprehensive enriched
notes from vedabase.io-verified verse data. Pure function + BaseTool wrapper.

CRITICAL: This tool receives ONLY verified verse data from vedabase.io.
It never generates translations, purports, or philosophical content
from LLM training data alone.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

import httpx

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.enrichment_prompt import ENRICHMENT_MASTER_PROMPT_V6

logger = logging.getLogger(__name__)

# Check for anthropic SDK
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

# Token estimation: ~1.3 tokens per word on average
_TOKENS_PER_WORD = 1.3
_MAX_INPUT_TOKENS = 100_000
_MAX_VERSES_FALLBACK = 20


def generate_enriched_notes_llm(
    transcript_text: str,
    verified_verses: list[dict],
    master_prompt: str = ENRICHMENT_MASTER_PROMPT_V6,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 16384,
    user_prompt: Optional[str] = None,
) -> dict:
    """
    Generate 15-section enriched notes using Claude with verified verse data.

    The master prompt is sent as the system message. The user message contains
    the transcript text and all vedabase.io-verified verse data (devanagari,
    transliteration, synonyms, translation, purport excerpt, URL).

    The LLM generates enriched class notes following the 15-section format
    defined in Master Prompt v6.0, using ONLY the verified data provided.

    Args:
        transcript_text: Full transcript text from the lecture.
        verified_verses: List of dicts with verified verse data. Each dict
            should contain: canonical_ref, devanagari, verse_text, synonyms,
            translation, purport_excerpt, vedabase_url, cross_refs.
        master_prompt: System prompt for the LLM (default: v6.0).
        model: Claude model to use.
        max_tokens: Max output tokens.

    Returns:
        dict with keys:
            enriched_markdown: str or None — The 15-section markdown output
            saranagathi_mapping: dict or None — SARANAGATHI classification
            verses_processed: int — Number of verses included
            truncated: bool — Whether input was truncated
            error: str or None — Error message if generation failed
    """
    if not HAS_ANTHROPIC:
        logger.warning("anthropic SDK not available; skipping LLM enrichment")
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": False,
            "error": "anthropic SDK not installed. pip install anthropic",
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; skipping LLM enrichment")
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": False,
            "error": "ANTHROPIC_API_KEY environment variable not set",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=600.0),
        max_retries=2,
    )

    # Build user message with transcript + verified verse data
    truncated = False
    user_message = _build_enrichment_context(transcript_text, verified_verses)

    # Append user-provided custom instructions if present
    if user_prompt:
        user_message += (
            "\n\n## Additional Instructions from User\n\n"
            f"{user_prompt}\n"
        )

    # Check estimated token count and trim if necessary
    estimated_tokens = len(user_message.split()) * _TOKENS_PER_WORD
    system_tokens = len(master_prompt.split()) * _TOKENS_PER_WORD
    if estimated_tokens + system_tokens > _MAX_INPUT_TOKENS:
        logger.warning(
            "Estimated %.0f tokens exceeds limit; limiting to %d verses",
            estimated_tokens + system_tokens,
            _MAX_VERSES_FALLBACK,
        )
        verified_verses = verified_verses[:_MAX_VERSES_FALLBACK]
        user_message = _build_enrichment_context(transcript_text, verified_verses)
        truncated = True

    try:
        logger.info(
            "Calling Claude for LLM enrichment: %d verses, ~%.0f input tokens",
            len(verified_verses),
            len(user_message.split()) * _TOKENS_PER_WORD + system_tokens,
        )
        # Use streaming to avoid connection timeouts on large responses
        chunks: list[str] = []
        with client.messages.stream(
            model=model,
            max_tokens=max_tokens,
            system=master_prompt,
            messages=[{
                "role": "user",
                "content": user_message,
            }],
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)

        enriched_markdown = "".join(chunks).strip()

        # Extract SARANAGATHI mapping if present in the output
        saranagathi_mapping = _extract_saranagathi_mapping(enriched_markdown)

        logger.info(
            "LLM enrichment complete: %d chars, %d verses processed",
            len(enriched_markdown),
            len(verified_verses),
        )

        return {
            "enriched_markdown": enriched_markdown,
            "saranagathi_mapping": saranagathi_mapping,
            "verses_processed": len(verified_verses),
            "truncated": truncated,
            "error": None,
        }

    except Exception as e:
        logger.error("LLM enrichment failed: %s", e)
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": truncated,
            "error": str(e),
        }


def _build_enrichment_context(
    transcript_text: str,
    verified_verses: list[dict],
) -> str:
    """
    Build the user message containing transcript + verified verse data.

    The message is structured so the LLM can find verified data easily
    and use it as the authoritative source for enrichment. The LLM must
    use ONLY this data for translations, purports, and Sanskrit text.

    When verses span multiple scriptures (3+ verses from 2+ scriptures),
    they are grouped by scripture type for better organization.
    """
    parts: list[str] = []

    parts.append("## Lecture Transcript\n\n")
    parts.append(transcript_text)
    parts.append("\n\n---\n\n")

    if verified_verses:
        # Determine if we should group by scripture
        scripture_types = set()
        for v in verified_verses:
            canonical = v.get("canonical_ref", "")
            sp = canonical.split()
            if sp:
                scripture_types.add(sp[0])

        use_grouping = len(verified_verses) >= 3 and len(scripture_types) >= 2

        if use_grouping:
            from lecture_agents.tools.transcript_chunker import group_verses_by_scripture
            grouped = group_verses_by_scripture(verified_verses)

            parts.append("## Verified Verses from Vedabase.io\n\n")
            parts.append(
                "The following verses have been verified against vedabase.io, "
                "grouped by scripture. Use ONLY this data for translations, "
                "purports, and Sanskrit text. Do NOT generate scripture content "
                "from memory or training data.\n\n"
            )

            for scripture, verses in grouped.items():
                display_name = _SCRIPTURE_DISPLAY_NAMES.get(scripture, scripture)
                parts.append(f"### {display_name} References\n\n")
                for v in verses:
                    _append_verse_block(parts, v)
        else:
            parts.append("## Verified Verses from Vedabase.io\n\n")
            parts.append(
                "The following verses have been verified against vedabase.io. "
                "Use ONLY this data for translations, purports, and Sanskrit text. "
                "Do NOT generate scripture content from memory or training data.\n\n"
            )
            for v in verified_verses:
                _append_verse_block(parts, v)
    else:
        parts.append("## Note on Verse References\n\n")
        parts.append(
            "No verse references could be verified against vedabase.io for this "
            "lecture. Identify verses discussed by the speaker from context and "
            "mark them as [From Lecture — Verify Against Vedabase.io]. "
            "Do NOT generate translations or purports from training data.\n\n"
        )

    parts.append("## Instructions\n\n")
    parts.append(
        "Generate structured lecture notes following the system prompt format. "
        "Use verified vedabase.io data where available as the authoritative source. "
        "For unverified references, present the speaker's explanation only.\n"
    )

    return "".join(parts)


# Scripture display names for grouped verse context
_SCRIPTURE_DISPLAY_NAMES = {
    "BG": "Bhagavad-gita",
    "SB": "Srimad-Bhagavatam",
    "CC": "Caitanya-caritamrita",
    "NOI": "Nectar of Instruction",
    "ISO": "Sri Isopanisad",
    "BS": "Brahma-samhita",
}


def _append_verse_block(parts: list[str], v: dict) -> None:
    """Append a single verse's data block to the parts list."""
    ref = v.get("canonical_ref", "Unknown")
    parts.append(f"#### {ref}\n\n")

    if v.get("vedabase_url"):
        parts.append(f"**Vedabase URL:** {v['vedabase_url']}\n\n")
    if v.get("devanagari"):
        parts.append(f"**Devanagari:**\n{v['devanagari']}\n\n")
    if v.get("verse_text"):
        parts.append(f"**IAST Transliteration:**\n{v['verse_text']}\n\n")
    if v.get("synonyms"):
        parts.append(f"**Synonyms:**\n{v['synonyms']}\n\n")
    if v.get("translation"):
        parts.append(f"**Translation:**\n{v['translation']}\n\n")
    if v.get("purport_excerpt"):
        parts.append(f"**Purport (excerpt):**\n{v['purport_excerpt']}\n\n")
    if v.get("cross_refs"):
        parts.append(
            f"**Cross-references in purport:** {', '.join(v['cross_refs'])}\n\n"
        )

    parts.append("---\n\n")


def _extract_saranagathi_mapping(markdown: str) -> Optional[dict]:
    """
    Extract SARANAGATHI classification data from the enriched markdown.

    Looks for the SARANAGATHI mapping section and parses the letter-theme
    assignments for each verse.

    Returns:
        dict mapping SARANAGATHI letters to lists of verse references,
        or None if no mapping found.
    """
    # Look for SARANAGATHI mapping section
    pattern = r"(?:SARANAGATHI\s+(?:Position|Mapping|Classification|Framework))"
    matches = list(re.finditer(pattern, markdown, re.IGNORECASE))

    if not matches:
        return None

    mapping: dict[str, list[str]] = {}

    saranagathi_letters = {
        "S": "Shelter",
        "A": "Approach",
        "R": "Recognition",
        "N": "Negation",
        "G": "Grace",
        "T": "Transcendence",
        "H": "Humility",
        "I": "Intimacy",
    }

    for match in matches:
        # Extract the block of text after each SARANAGATHI heading
        block_start = match.start()
        block_end = min(block_start + 500, len(markdown))
        block = markdown[block_start:block_end]

        # Look for letter-theme assignments like "S - Shelter" or "[S] Shelter"
        for letter, theme in saranagathi_letters.items():
            letter_pattern = rf"(?:\b{letter}\b\s*[-:]\s*{theme}|{theme})"
            if re.search(letter_pattern, block, re.IGNORECASE):
                # Try to find associated verse references
                verse_pattern = r"(?:SB|BG|CC|NOI|ISO|BS)\s+[\d.]+(?:\.\d+)*"
                nearby_verses = re.findall(verse_pattern, block)
                if nearby_verses:
                    mapping.setdefault(letter, []).extend(nearby_verses)

    # Deduplicate
    for letter in mapping:
        mapping[letter] = list(dict.fromkeys(mapping[letter]))

    return mapping if mapping else None


# ---------------------------------------------------------------------------
# Chunked LLM enrichment — processes long transcripts in segments
# ---------------------------------------------------------------------------


def generate_enriched_notes_chunked(
    chunks: list,
    master_prompt: str = ENRICHMENT_MASTER_PROMPT_V6,
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens_per_chunk: int = 16384,
    user_prompt: Optional[str] = None,
) -> dict:
    """
    Generate enriched notes by processing each chunk independently, then merging.

    For each chunk:
    1. Build chunk-specific context with its transcript text and relevant verses
    2. Call Claude with the master prompt
    3. Collect the enriched markdown

    After all chunks:
    4. Merge chunk outputs into a single coherent document

    Args:
        chunks: List of TranscriptChunk objects from chunk_transcript_by_purpose().
        master_prompt: System prompt for the LLM.
        model: Claude model to use.
        max_tokens_per_chunk: Max output tokens per chunk.
        user_prompt: Optional custom instructions.

    Returns:
        dict with same keys as generate_enriched_notes_llm() plus
        chunks_processed and chunks_failed.
    """
    if not HAS_ANTHROPIC:
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": False,
            "error": "anthropic SDK not installed",
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": False,
            "error": "ANTHROPIC_API_KEY not set",
        }

    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=600.0),
        max_retries=2,
    )

    total_chunks = len(chunks)
    chunk_markdowns: list[tuple[int, str]] = []
    chunks_failed: list[int] = []
    total_verses = 0

    for chunk in chunks:
        chunk_idx = chunk.chunk_index
        logger.info(
            "Processing chunk %d/%d (~%d tokens, %d verses, %.0f-%.0fs)",
            chunk_idx + 1, total_chunks, chunk.estimated_tokens,
            len(chunk.verified_verses), chunk.start_time, chunk.end_time,
        )

        # Build chunk-specific context
        user_message = _build_chunk_enrichment_context(
            chunk_text=chunk.text,
            chunk_verses=chunk.verified_verses,
            chunk_index=chunk_idx,
            total_chunks=total_chunks,
            start_time=chunk.start_time,
            end_time=chunk.end_time,
        )

        if user_prompt:
            user_message += (
                "\n\n## Additional Instructions from User\n\n"
                f"{user_prompt}\n"
            )

        try:
            text_chunks: list[str] = []
            with client.messages.stream(
                model=model,
                max_tokens=max_tokens_per_chunk,
                system=master_prompt,
                messages=[{"role": "user", "content": user_message}],
            ) as stream:
                for text in stream.text_stream:
                    text_chunks.append(text)

            markdown = "".join(text_chunks).strip()
            if markdown:
                chunk_markdowns.append((chunk_idx, markdown))
                total_verses += len(chunk.verified_verses)
                logger.info(
                    "Chunk %d/%d complete: %d chars",
                    chunk_idx + 1, total_chunks, len(markdown),
                )
            else:
                chunks_failed.append(chunk_idx)
                logger.warning("Chunk %d/%d returned empty output", chunk_idx + 1, total_chunks)

        except Exception as e:
            chunks_failed.append(chunk_idx)
            logger.error("Chunk %d/%d failed: %s", chunk_idx + 1, total_chunks, e)

    # Merge all chunk outputs
    if not chunk_markdowns:
        return {
            "enriched_markdown": None,
            "saranagathi_mapping": None,
            "verses_processed": 0,
            "truncated": False,
            "error": f"All {total_chunks} chunks failed",
            "chunks_processed": 0,
            "chunks_failed": chunks_failed,
        }

    merged = _merge_chunk_outputs(chunk_markdowns, total_chunks, chunks_failed)
    saranagathi = _extract_saranagathi_mapping(merged)

    logger.info(
        "Chunked enrichment complete: %d/%d chunks succeeded, %d chars merged",
        len(chunk_markdowns), total_chunks, len(merged),
    )

    return {
        "enriched_markdown": merged,
        "saranagathi_mapping": saranagathi,
        "verses_processed": total_verses,
        "truncated": False,
        "error": None,
        "chunks_processed": len(chunk_markdowns),
        "chunks_failed": chunks_failed,
    }


def _build_chunk_enrichment_context(
    chunk_text: str,
    chunk_verses: list[dict],
    chunk_index: int,
    total_chunks: int,
    start_time: float,
    end_time: float,
) -> str:
    """
    Build user message for a single chunk's LLM enrichment call.

    Adds chunk context (section N of M, time range) and groups
    verses by scripture within the chunk.
    """
    def _fmt_time(seconds: float) -> str:
        m, s = divmod(int(seconds), 60)
        h, m = divmod(m, 60)
        return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"

    parts: list[str] = []

    parts.append("## Context\n\n")
    parts.append(
        f"This is section {chunk_index + 1} of {total_chunks} "
        f"from a lecture transcript.\n"
        f"Time range: {_fmt_time(start_time)} — {_fmt_time(end_time)}\n\n"
    )

    parts.append(f"## Lecture Transcript (Section {chunk_index + 1})\n\n")
    parts.append(chunk_text)
    parts.append("\n\n---\n\n")

    if chunk_verses:
        parts.append("## Verified Verses from Vedabase.io\n\n")
        parts.append(
            "Use ONLY this data for translations, purports, and Sanskrit text. "
            "Do NOT generate scripture content from memory or training data.\n\n"
        )
        for v in chunk_verses:
            _append_verse_block(parts, v)
    else:
        parts.append("## Note on Verse References\n\n")
        parts.append(
            "No verified verse data is available for this section. "
            "Identify verses discussed by the speaker from context and mark them as "
            "[From Lecture — Verify Against Vedabase.io].\n\n"
        )

    parts.append("## Instructions\n\n")
    parts.append(
        "Generate structured lecture notes for this section following the "
        "system prompt format. Use verified vedabase.io data where available. "
        "For unverified references, present the speaker's explanation only.\n"
    )

    return "".join(parts)


def _merge_chunk_outputs(
    chunk_markdowns: list[tuple[int, str]],
    total_chunks: int,
    failed_chunks: list[int],
) -> str:
    """
    Merge enriched markdown outputs from multiple chunks into a cohesive document.

    Strategy:
    - First chunk's output is used as-is (has document header)
    - Subsequent chunks: strip duplicate preamble headers
    - Insert section dividers between chunks
    - Insert placeholders for failed chunks
    """
    # Sort by chunk index
    sorted_chunks = sorted(chunk_markdowns, key=lambda x: x[0])

    if len(sorted_chunks) == 1 and not failed_chunks:
        return sorted_chunks[0][1]

    parts: list[str] = []

    # Track which indices we have
    present = {idx for idx, _ in sorted_chunks}
    chunk_map = {idx: md for idx, md in sorted_chunks}

    for i in range(total_chunks):
        if i in chunk_map:
            markdown = chunk_map[i]

            if i == 0:
                # First chunk: use as-is
                parts.append(markdown)
            else:
                # Subsequent chunks: strip duplicate headers
                cleaned = _strip_duplicate_header(markdown)
                parts.append(f"\n\n---\n\n## Continued: Section {i + 1}\n\n")
                parts.append(cleaned)
        elif i in failed_chunks:
            parts.append(
                f"\n\n---\n\n> **[Section {i + 1}]:** "
                f"This portion could not be processed.\n\n"
            )

    return "".join(parts)


def _strip_duplicate_header(markdown: str) -> str:
    """Strip duplicate preamble from subsequent chunk outputs."""
    lines = markdown.split("\n")
    # Look for common preamble patterns to skip
    skip_patterns = [
        "all glories to",
        "# lecture notes",
        "# all glories",
        "## version",
    ]
    start_idx = 0
    for i, line in enumerate(lines[:10]):  # Only check first 10 lines
        lower = line.strip().lower()
        if any(p in lower for p in skip_patterns):
            start_idx = i + 1

    return "\n".join(lines[start_idx:]).lstrip("\n")


# ---------------------------------------------------------------------------
# LLM-based reference identification
# ---------------------------------------------------------------------------

_REFERENCE_IDENTIFICATION_PROMPT = """\
You are a Gaudiya Vaishnava scripture reference identifier. Your task is to \
analyze a lecture transcript and identify ALL scripture references that can be \
verified against vedabase.io.

SUPPORTED SCRIPTURES (vedabase.io URL patterns):
- BG (Bhagavad-gita): BG {{chapter}}.{{verse}}
- SB (Srimad-Bhagavatam): SB {{canto}}.{{chapter}}.{{verse}}
- CC (Caitanya-caritamrita): CC {{Adi|Madhya|Antya}} {{chapter}}.{{verse}}
- NOI (Nectar of Instruction): NOI {{verse}}
- ISO (Sri Isopanisad): ISO {{verse}}
- BS (Brahma-samhita): BS {{chapter}}.{{verse}}

RULES:
1. Only return references you are confident about — must have scripture + \
chapter + verse (or just verse for NOI/ISO).
2. Do NOT return vague references like "Bhagavatam says" without a verse number.
3. Do NOT speculate or guess verse numbers — only identify references where \
the speaker clearly indicates which verse.
4. Include paraphrased verses ONLY if the specific verse can be identified \
from context (e.g., speaker discusses BG 2.47 content without naming it \
but the verse is clearly identifiable).
5. Return ONLY a JSON array. No explanation or commentary.

ALREADY FOUND BY REGEX (do not duplicate these):
{existing_refs}

Return a JSON array of objects:
[{{"scripture": "SB", "chapter": "3.25", "verse": "21", \
"canonical_ref": "SB 3.25.21", "context_text": "brief quote from transcript"}}]

Return an empty array [] if no additional references are found.\
"""


def identify_references_llm(
    transcript_text: str,
    regex_refs: list[str],
    model: str = "claude-sonnet-4-5-20250929",
    max_tokens: int = 4096,
) -> list[dict]:
    """
    Use Claude to identify implicit scripture references missed by regex.

    Sends the transcript to Claude with instructions to find references
    that can be verified against vedabase.io. Only returns references with
    specific scripture + chapter + verse identifiers.

    Args:
        transcript_text: Full transcript text.
        regex_refs: List of canonical_ref strings already found by regex.
        model: Claude model to use.
        max_tokens: Max output tokens.

    Returns:
        list of dicts with keys: scripture, chapter, verse, canonical_ref,
        context_text. Empty list on error or no results.
    """
    if not HAS_ANTHROPIC:
        logger.warning("anthropic SDK not available; skipping LLM reference identification")
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; skipping LLM reference identification")
        return []

    client = anthropic.Anthropic(
        api_key=api_key,
        timeout=httpx.Timeout(connect=10.0, read=600.0, write=600.0, pool=600.0),
        max_retries=2,
    )

    existing_refs_str = ", ".join(regex_refs) if regex_refs else "(none)"
    system_prompt = _REFERENCE_IDENTIFICATION_PROMPT.format(
        existing_refs=existing_refs_str,
    )

    # Trim transcript if too long (keep first ~60k words ≈ ~78k tokens)
    words = transcript_text.split()
    if len(words) > 60000:
        transcript_text = " ".join(words[:60000])
        logger.info("Trimmed transcript to 60k words for LLM reference identification")

    try:
        logger.info(
            "Calling Claude for reference identification (~%d words, %d existing refs)",
            len(words), len(regex_refs),
        )
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{
                "role": "user",
                "content": f"Identify all scripture references in this lecture transcript:\n\n{transcript_text}",
            }],
        )

        raw_text = response.content[0].text.strip()

        # Extract JSON array from response (handle markdown code blocks)
        json_match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not json_match:
            logger.warning("LLM reference identification returned no JSON array")
            return []

        candidates = json.loads(json_match.group())

        # Validate and filter results
        valid_refs: list[dict] = []
        valid_scriptures = {"BG", "SB", "CC", "NOI", "ISO", "BS"}
        existing_set = set(regex_refs)

        for ref in candidates:
            if not isinstance(ref, dict):
                continue
            canonical = ref.get("canonical_ref", "")
            scripture = ref.get("scripture", "")
            if not canonical or not scripture:
                continue
            if scripture not in valid_scriptures:
                continue
            if canonical in existing_set:
                continue
            # Ensure required fields
            if scripture in ("NOI", "ISO"):
                if not ref.get("verse"):
                    continue
                ref.setdefault("chapter", "")
            else:
                if not ref.get("chapter") or not ref.get("verse"):
                    continue

            ref.setdefault("segment_index", 0)
            ref.setdefault("context_text", "")
            valid_refs.append(ref)
            existing_set.add(canonical)

        logger.info("LLM identified %d additional references", len(valid_refs))
        return valid_refs

    except Exception as e:
        logger.error("LLM reference identification failed: %s", e)
        return []


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class LlmEnrichmentInput(BaseModel):
    transcript_text: str = Field(..., description="Lecture transcript text")
    verified_verses_json: str = Field(
        ...,
        description="JSON string of verified verse data from vedabase.io",
    )


class LlmEnrichmentTool(BaseTool):
    name: str = "generate_enriched_notes"
    description: str = (
        "Use Claude LLM to generate 15-section enriched class notes from "
        "a lecture transcript and vedabase.io-verified verse data. Produces "
        "comprehensive markdown with SARANAGATHI classification, acarya "
        "commentaries, bhajan connections, and practical applications."
    )
    args_schema: type[BaseModel] = LlmEnrichmentInput

    def _run(self, transcript_text: str, verified_verses_json: str) -> str:
        verified_verses = json.loads(verified_verses_json)
        result = generate_enriched_notes_llm(transcript_text, verified_verses)
        return json.dumps(result, ensure_ascii=False)
