"""
Agent 03: Enrichment Agent
Lecture-to-Notes Pipeline v1.0

Transforms raw transcripts into annotated study notes with
vedabase.io-verified scripture references, glossary, and thematic index.

CRITICAL: All verses must be verified against vedabase.io.
No speculation. Only parampara-authorized content.
"""

from __future__ import annotations

import logging
from typing import Optional

try:
    from crewai import Agent, Task
    HAS_CREWAI = True
except ImportError:
    HAS_CREWAI = False
    Agent = None  # type: ignore[assignment,misc]
    Task = None   # type: ignore[assignment,misc]

from lecture_agents.config.constants import VEDABASE_CACHE_FILE
from lecture_agents.exceptions import EnrichmentError
from lecture_agents.schemas.enrichment_output import (
    EnrichedNotes,
    GlossaryEntry,
    Reference,
    ThematicIndex,
    ThematicTag,
    VerificationResult,
)
from lecture_agents.schemas.transcript_output import TranscriptOutput
from lecture_agents.tools.enrichment_annotator import (
    GlossaryBuildTool,
    build_glossary,
    build_thematic_index,
)
from lecture_agents.tools.vedabase_fetcher import (
    VedabaseFetchTool,
    batch_fetch_verses,
    fetch_verse,
)
from lecture_agents.tools.mcp_verse_tools import (
    mcp_batch_fuzzy_match,
    mcp_batch_lookup_verses,
    mcp_fuzzy_match,
    mcp_lookup_verse,
    HAS_MCP,
)
from lecture_agents.config.lecture_prompt import LECTURE_CENTRIC_PROMPT_V7
from lecture_agents.tools.llm_enrichment_generator import (
    LlmEnrichmentTool,
    generate_enriched_notes_llm,
    identify_references_llm,
)
from lecture_agents.tools.verse_identifier import (
    VerseIdentifyTool,
    identify_references,
)

logger = logging.getLogger(__name__)


def run_enrichment_pipeline(
    transcript: TranscriptOutput,
    cache_path: str = VEDABASE_CACHE_FILE,
    enable_llm: bool = True,
    user_prompt: Optional[str] = None,
    enrichment_mode: str = "auto",
) -> EnrichedNotes:
    """
    Run the enrichment pipeline.

    Steps:
    1. Identify scripture references in transcript (regex)
    2. Verify each reference against vedabase.io (with caching)
    3. Build glossary from domain vocabulary
    4. Build thematic index
    5. (Optional) LLM enrichment — auto-selects prompt based on mode
    6. Assemble EnrichedNotes

    When enable_llm=True, Step 5 generates enriched notes using Claude.
    The prompt is selected based on enrichment_mode:
    - "auto": lecture-centric (v7.0) if ≤2 verified verses, else verse-centric (v6.0)
    - "lecture-centric": always use lecture-centric prompt (v7.0)
    - "verse-centric": always use verse-centric prompt (v6.0)

    CRITICAL: Only verified references appear in the enriched output.
    Unverified references are tracked separately for manual review.

    Args:
        transcript: Output from Transcriber Agent.
        cache_path: Path to vedabase.io JSON cache.
        enable_llm: Enable LLM enriched notes generation.
        user_prompt: Custom instructions for LLM enrichment.
        enrichment_mode: "auto", "verse-centric", or "lecture-centric".

    Returns:
        Validated EnrichedNotes.
    """
    text = transcript.full_text
    segments = [s.model_dump() for s in transcript.segments]

    if not text or len(text.strip()) < 50:
        raise EnrichmentError("Transcript text too short for enrichment")

    # Step 1: Identify scripture references
    logger.info("Step 1: Identifying scripture references")
    raw_refs = identify_references(text, segments)
    logger.info("Found %d candidate references", len(raw_refs))

    # Also check detected slokas from the transcriber
    for sloka in transcript.detected_slokas:
        if sloka.probable_reference:
            # Parse the reference and add if not already found
            parts = sloka.probable_reference.split()
            if len(parts) >= 2:
                existing_canonicals = {r["canonical_ref"] for r in raw_refs}
                if sloka.probable_reference not in existing_canonicals:
                    # Try to parse into scripture/chapter/verse
                    scripture = parts[0]
                    rest = " ".join(parts[1:]).replace(" ", ".")
                    if "." in rest:
                        last_dot = rest.rfind(".")
                        chapter = rest[:last_dot]
                        verse = rest[last_dot + 1:]
                    else:
                        chapter = ""
                        verse = rest
                    raw_refs.append({
                        "scripture": scripture,
                        "chapter": chapter,
                        "verse": verse,
                        "canonical_ref": sloka.probable_reference,
                        "segment_index": sloka.segment_index,
                        "context_text": sloka.text[:100],
                    })

    # Step 1b: LLM-based reference identification (optional)
    if enable_llm:
        logger.info("Step 1b: LLM-based reference identification")
        existing_canonicals = [r["canonical_ref"] for r in raw_refs]
        llm_refs = identify_references_llm(text, existing_canonicals)
        if llm_refs:
            raw_refs.extend(llm_refs)
            logger.info("LLM identified %d additional references (total: %d)", len(llm_refs), len(raw_refs))
        else:
            logger.info("LLM found no additional references")
    else:
        logger.info("Step 1b: Skipping LLM reference identification (enable_llm=False)")

    # Step 1c: MCP fuzzy matching for detected slokas without references (batched)
    if HAS_MCP:
        existing_canonicals = {r["canonical_ref"] for r in raw_refs}
        unmatched_slokas = [
            s for s in transcript.detected_slokas
            if not s.probable_reference or s.probable_reference not in existing_canonicals
        ]
        if unmatched_slokas:
            logger.info(
                "Step 1c: MCP batch fuzzy matching for %d unmatched slokas",
                len(unmatched_slokas),
            )
            sloka_texts = [s.text for s in unmatched_slokas]
            batch_results = mcp_batch_fuzzy_match(sloka_texts, top_n=1)
            for sloka, matches in zip(unmatched_slokas, batch_results):
                if matches and matches[0]["score"] >= 0.4:
                    best = matches[0]
                    ref_str = best["ref"]  # e.g. "BG 9.34"
                    parts = ref_str.split()
                    if len(parts) == 2 and "." in parts[1]:
                        ch, vs = parts[1].split(".", 1)
                        if ref_str not in existing_canonicals:
                            raw_refs.append({
                                "scripture": "BG",
                                "chapter": ch,
                                "verse": vs,
                                "canonical_ref": ref_str,
                                "segment_index": sloka.segment_index,
                                "context_text": sloka.text[:100],
                            })
                            existing_canonicals.add(ref_str)
                            logger.info(
                                "    Fuzzy matched: '%s' -> %s (score: %.2f)",
                                sloka.text[:60], ref_str, best["score"],
                            )
    else:
        logger.info("Step 1c: Skipping MCP fuzzy matching (mcp SDK not available)")

    # Build Reference objects
    references: list[Reference] = []
    for ref_dict in raw_refs:
        try:
            references.append(Reference(**ref_dict))
        except Exception as e:
            logger.warning("Skipping invalid reference %s: %s", ref_dict, e)

    # Step 2: Verify references against vedabase.io (batched by scripture)
    logger.info("Step 2: Verifying %d references against vedabase.io (batched)", len(references))
    verifications, unverified = _batch_verify_references(references, cache_path)

    verified_count = len(verifications)
    total_refs = len(references)
    rate = verified_count / total_refs if total_refs > 0 else 0.0

    logger.info(
        "Verification complete: %d/%d verified (%.0f%%)",
        verified_count, total_refs, rate * 100,
    )

    # Step 3: Build glossary
    logger.info("Step 3: Building glossary")
    glossary_dicts = build_glossary(text, segments)
    glossary = [
        GlossaryEntry(**g) for g in glossary_dicts
    ]

    # Step 4: Build thematic index
    logger.info("Step 4: Building thematic index")
    theme_dict = build_thematic_index(
        text,
        [r.model_dump() for r in references],
        [v.model_dump() for v in verifications],
    )
    thematic_index = ThematicIndex(
        themes=[ThematicTag(**t) for t in theme_dict.get("themes", [])],
        primary_topic=theme_dict.get("primary_topic", "Gaudiya Vaishnava Discourse"),
        scripture_focus=theme_dict.get("scripture_focus"),
    )

    # Step 5: LLM enrichment (optional — auto-selects prompt based on mode)
    enriched_markdown = None
    saranagathi_mapping = None

    if enable_llm:
        # Prepare verified verse data for LLM — only vedabase.io-sourced content
        verified_verse_data = _prepare_verified_verse_data(verifications)
        prompt_to_use, mode_label = _select_prompt(verified_verse_data, enrichment_mode)

        # Estimate tokens to decide chunking strategy
        from lecture_agents.config.constants import CHUNK_ACTIVATION_THRESHOLD_TOKENS
        estimated_tokens = len(text.split()) * 1.3
        segments_dicts = [s.model_dump() for s in transcript.segments]

        if estimated_tokens > CHUNK_ACTIVATION_THRESHOLD_TOKENS and len(segments_dicts) > 20:
            # CHUNKED PATH: Split transcript, process each chunk with LLM
            logger.info(
                "Step 5: Chunked LLM enrichment (%s, ~%.0f tokens, %d verified verses)",
                mode_label, estimated_tokens, len(verified_verse_data),
            )
            from lecture_agents.tools.transcript_chunker import chunk_transcript_by_purpose
            from lecture_agents.tools.llm_enrichment_generator import generate_enriched_notes_chunked

            chunks = chunk_transcript_by_purpose(
                segments=segments_dicts,
                full_text=text,
                references=[r.model_dump() for r in references],
                verified_verses=verified_verse_data,
            )
            llm_result = generate_enriched_notes_chunked(
                chunks=chunks,
                master_prompt=prompt_to_use,
                user_prompt=user_prompt,
            )
        else:
            # SINGLE-PASS PATH: Existing behavior (with grouped verses)
            logger.info(
                "Step 5: Single-pass LLM enrichment (%s, %d verified verses)",
                mode_label, len(verified_verse_data),
            )
            llm_result = generate_enriched_notes_llm(
                transcript_text=text,
                verified_verses=verified_verse_data,
                master_prompt=prompt_to_use,
                user_prompt=user_prompt,
            )

        if llm_result.get("enriched_markdown"):
            enriched_markdown = llm_result["enriched_markdown"]
            saranagathi_mapping = llm_result.get("saranagathi_mapping")
            logger.info(
                "LLM enrichment complete (%s): %d verses processed, %d chars output",
                mode_label,
                llm_result.get("verses_processed", 0),
                len(enriched_markdown),
            )
        else:
            logger.warning(
                "LLM enrichment returned no output: %s",
                llm_result.get("error", "unknown error"),
            )
    else:
        logger.info("Step 5: Skipping LLM enrichment (enable_llm=False)")

    # Step 6: Assemble output
    summary = (
        f"Enriched transcript with {verified_count} verified references "
        f"out of {total_refs} found. "
        f"Glossary: {len(glossary)} entries. "
        f"Themes: {len(thematic_index.themes)}. "
        f"Primary topic: {thematic_index.primary_topic}."
    )
    if unverified:
        summary += f" {len(unverified)} references could not be verified."
    if enriched_markdown:
        summary += " LLM-enriched 15-section notes generated."

    return EnrichedNotes(
        source_transcript=transcript.source_audio,
        transcript_text=text,
        references_found=references,
        verifications=verifications,
        glossary=glossary,
        thematic_index=thematic_index,
        enrichment_source="hybrid" if enable_llm else "regex",
        unverified_references=unverified,
        summary=summary,
        enriched_markdown=enriched_markdown,
        saranagathi_mapping=saranagathi_mapping,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _build_verification(ref: Reference, fetch_result: dict) -> VerificationResult:
    """Build a VerificationResult from a reference and fetch result."""
    source = fetch_result.get("fetch_source", "live")
    return VerificationResult(
        reference=ref,
        status="cache_only" if source == "cache" else "verified",
        vedabase_url=fetch_result.get("url"),
        devanagari=fetch_result.get("devanagari"),
        verse_text=fetch_result.get("verse_text"),
        synonyms=fetch_result.get("synonyms"),
        translation=fetch_result.get("translation"),
        purport_excerpt=fetch_result.get("purport_excerpt"),
        cross_refs_in_purport=fetch_result.get("cross_refs_in_purport", []),
    )


def _batch_verify_references(
    references: list[Reference],
    cache_path: str,
) -> tuple[list[VerificationResult], list[Reference]]:
    """
    Verify all references using batched operations.

    Strategy:
    1. Separate BG references from non-BG references
    2. BG refs: use mcp_batch_lookup_verses() for one MCP session
    3. Non-BG refs + BG fallbacks: use batch_fetch_verses() for optimized cache
    """
    verifications: list[VerificationResult] = []
    unverified: list[Reference] = []

    bg_refs = [r for r in references if r.scripture.upper() == "BG"]
    other_refs = [r for r in references if r.scripture.upper() != "BG"]

    # Batch 1: BG refs via MCP (single session)
    bg_fallback: list[Reference] = []
    if HAS_MCP and bg_refs:
        logger.info("  Batch MCP lookup for %d BG references", len(bg_refs))
        canonical_strs = [r.canonical_ref for r in bg_refs]
        mcp_results = mcp_batch_lookup_verses(canonical_strs)
        for ref, result in zip(bg_refs, mcp_results):
            if result.get("verified"):
                verifications.append(_build_verification(ref, result))
                logger.info("    -> Verified (MCP): %s", ref.canonical_ref)
            else:
                bg_fallback.append(ref)  # Will try vedabase direct
    else:
        bg_fallback = list(bg_refs)

    # Batch 2: Non-BG refs + BG fallbacks via vedabase fetcher (single cache load/save)
    all_direct = other_refs + bg_fallback
    if all_direct:
        logger.info("  Batch vedabase fetch for %d references", len(all_direct))
        ref_dicts = [
            {"scripture": r.scripture, "chapter": r.chapter, "verse": r.verse}
            for r in all_direct
        ]
        fetch_results = batch_fetch_verses(ref_dicts, cache_path=cache_path)
        for ref, result in zip(all_direct, fetch_results):
            if result.get("verified"):
                verifications.append(_build_verification(ref, result))
                logger.info("    -> Verified: %s", ref.canonical_ref)
            else:
                unverified.append(ref)
                logger.warning(
                    "    -> NOT VERIFIED: %s — %s",
                    ref.canonical_ref,
                    result.get("error", "no content found"),
                )

    verified_count = len(verifications)
    total_refs = len(references)
    rate = verified_count / total_refs if total_refs > 0 else 0.0
    logger.info(
        "Verification complete: %d/%d verified (%.0f%%)",
        verified_count, total_refs, rate * 100,
    )

    return verifications, unverified


def _prepare_verified_verse_data(
    verifications: list[VerificationResult],
) -> list[dict]:
    """Prepare verified verse data dicts for LLM consumption."""
    verified_verse_data = []
    for v in verifications:
        if v.status in ("verified", "cache_only"):
            verified_verse_data.append({
                "canonical_ref": v.reference.canonical_ref,
                "devanagari": v.devanagari,
                "verse_text": v.verse_text,
                "synonyms": v.synonyms,
                "translation": v.translation,
                "purport_excerpt": v.purport_excerpt,
                "vedabase_url": v.vedabase_url,
                "cross_refs": v.cross_refs_in_purport,
            })
    return verified_verse_data


def _select_prompt(
    verified_verse_data: list[dict],
    enrichment_mode: str,
) -> tuple[str, str]:
    """Select the appropriate prompt and return (prompt, mode_label)."""
    verified_count = len(verified_verse_data)
    if enrichment_mode == "auto":
        use_lecture_centric = verified_count <= 2
    elif enrichment_mode == "lecture-centric":
        use_lecture_centric = True
    else:
        use_lecture_centric = False

    if use_lecture_centric:
        prompt_to_use = LECTURE_CENTRIC_PROMPT_V7
        mode_label = "lecture-centric v7.0"
    else:
        from lecture_agents.config.enrichment_prompt import ENRICHMENT_MASTER_PROMPT_V6
        prompt_to_use = ENRICHMENT_MASTER_PROMPT_V6
        mode_label = "verse-centric v6.0"

    return prompt_to_use, mode_label


# ---------------------------------------------------------------------------
# CrewAI Agentic Mode
# ---------------------------------------------------------------------------


def build_enrichment_agent() -> Agent:
    """Create the Enrichment Agent with all tools. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode. pip install crewai[tools]")
    return Agent(
        role="Acarya-Level Vedabase-Verified Scripture Enrichment Specialist",
        goal=(
            "Transform raw lecture transcripts into deeply enriched study notes "
            "with 15 specialized sections per verse, following Master Prompt v6.0. "
            "Every verse must be verified against vedabase.io. Generate SARANAGATHI "
            "classification, acarya commentaries, bhajan connections, cross-references, "
            "and practical applications. Never speculate — only include verified content."
        ),
        backstory=(
            "You are a scholarly Vaisnava educator with deep expertise in Sanskrit "
            "grammar, IAST transliteration, Srila Prabhupada's teachings, and the "
            "full parampara tradition of Gaudiya Vaisnava acarya commentaries. You "
            "verify every verse citation against vedabase.io — the single source of "
            "truth. You enrich transcripts with 15 specialized sections including "
            "word-by-word analysis, purport deep dives, acarya commentaries from "
            "Sridhara Svami, Visvanatha Cakravarti Thakura, Jiva Gosvami, Rupa "
            "Gosvami, Sanatana Gosvami, and Bhaktivinoda Thakura, plus bhajan "
            "connections, SARANAGATHI classification, practical applications, teaching "
            "strategies, and memorization guides. You never generate translations or "
            "purports from memory; you always use exact text from vedabase.io. "
            "Silence is preferred over speculation."
        ),
        tools=[
            VerseIdentifyTool(),
            VedabaseFetchTool(),
            GlossaryBuildTool(),
            LlmEnrichmentTool(),
        ],
        verbose=True,
    )


def build_enrichment_task(agent: Agent, transcript_path: str) -> Task:
    """Create the Enrichment task. Requires crewai."""
    if not HAS_CREWAI:
        raise ImportError("crewai is required for agentic mode.")
    return Task(
        description=(
            f"Enrich the transcript at {transcript_path}. "
            "Identify all scripture references and verify each against vedabase.io. "
            "Build a glossary and thematic index. Then generate comprehensive "
            "15-section enriched class notes following Master Prompt v6.0 with "
            "SARANAGATHI classification, acarya commentaries, bhajan connections, "
            "cross-references, and practical applications. "
            "CRITICAL: Do NOT include any unverified references in annotations. "
            "Use ONLY vedabase.io-verified data for translations and purports."
        ),
        expected_output=(
            "An EnrichedNotes JSON with verified references, glossary, "
            "thematic index, list of unverified references for manual review, "
            "and LLM-generated 15-section enriched markdown with SARANAGATHI mapping."
        ),
        agent=agent,
    )
