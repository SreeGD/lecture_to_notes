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
from lecture_agents.tools.vedabase_fetcher import VedabaseFetchTool, fetch_verse
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
) -> EnrichedNotes:
    """
    Run the enrichment pipeline.

    Steps:
    1. Identify scripture references in transcript (regex)
    2. Verify each reference against vedabase.io (with caching)
    3. Build glossary from domain vocabulary
    4. Build thematic index
    5. (Optional) LLM enrichment with Master Prompt v6.0
    6. Assemble EnrichedNotes

    When enable_llm=True and verified verses exist, Step 5 generates
    15-section enriched class notes using Claude with the verified
    vedabase.io data as authoritative input.

    CRITICAL: Only verified references appear in the enriched output.
    Unverified references are tracked separately for manual review.

    Args:
        transcript: Output from Transcriber Agent.
        cache_path: Path to vedabase.io JSON cache.
        enable_llm: Enable LLM for 15-section enriched notes generation.

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

    # Build Reference objects
    references: list[Reference] = []
    for ref_dict in raw_refs:
        try:
            references.append(Reference(**ref_dict))
        except Exception as e:
            logger.warning("Skipping invalid reference %s: %s", ref_dict, e)

    # Step 2: Verify each reference against vedabase.io
    logger.info("Step 2: Verifying %d references against vedabase.io", len(references))
    verifications: list[VerificationResult] = []
    unverified: list[Reference] = []

    for ref in references:
        logger.info("  Verifying: %s", ref.canonical_ref)
        fetch_result = fetch_verse(
            ref.scripture, ref.chapter, ref.verse, cache_path=cache_path,
        )

        if fetch_result.get("verified"):
            verifications.append(VerificationResult(
                reference=ref,
                status="verified" if fetch_result["fetch_source"] != "cache" else "cache_only",
                vedabase_url=fetch_result.get("url"),
                devanagari=fetch_result.get("devanagari"),
                verse_text=fetch_result.get("verse_text"),
                synonyms=fetch_result.get("synonyms"),
                translation=fetch_result.get("translation"),
                purport_excerpt=fetch_result.get("purport_excerpt"),
                cross_refs_in_purport=fetch_result.get("cross_refs_in_purport", []),
            ))
            logger.info("    -> Verified: %s", ref.canonical_ref)
        else:
            # Reference could not be verified — exclude from enriched output
            unverified.append(ref)
            logger.warning(
                "    -> NOT VERIFIED: %s — %s",
                ref.canonical_ref,
                fetch_result.get("error", "no content found"),
            )

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

    # Step 5: LLM enrichment (optional — Master Prompt v6.0)
    enriched_markdown = None
    saranagathi_mapping = None

    if enable_llm:
        logger.info("Step 5: Generating LLM-enhanced enriched notes (Master Prompt v6.0)")

        # Prepare verified verse data for LLM — only vedabase.io-sourced content
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

        llm_result = generate_enriched_notes_llm(
            transcript_text=text,
            verified_verses=verified_verse_data,
        )

        if llm_result.get("enriched_markdown"):
            enriched_markdown = llm_result["enriched_markdown"]
            saranagathi_mapping = llm_result.get("saranagathi_mapping")
            logger.info(
                "LLM enrichment complete: %d verses processed, %d chars output",
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
