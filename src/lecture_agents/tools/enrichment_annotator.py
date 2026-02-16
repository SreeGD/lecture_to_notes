"""
Enrichment Tool: Build glossary, thematic index, and annotations.

Analyzes transcript content to produce glossary entries and thematic tags.
Uses domain vocabulary for deterministic extraction with optional LLM enhancement.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
import re
from collections import Counter
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.constants import (
    ACARYA_NAMES,
    DEITY_NAMES,
    DOMAIN_VOCABULARY,
    PHILOSOPHICAL_TERMS,
    PLACE_NAMES,
    SCRIPTURE_NAMES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Glossary definitions (from Prabhupada's books)
# Only include definitions directly sourced from Prabhupada's glossaries
# ---------------------------------------------------------------------------

GLOSSARY_DEFINITIONS: dict[str, tuple[str, str]] = {
    # (definition, source)
    "bhakti": ("Devotional service to the Supreme Lord.", "BG Glossary"),
    "karma": ("Material activities for which one incurs reactions.", "BG Glossary"),
    "dharma": ("Religious principles; one's occupational duty.", "BG Glossary"),
    "maya": ("The external, illusory energy of the Lord.", "BG Glossary"),
    "prema": ("Pure love of God; the highest perfection of life.", "CC Glossary"),
    "rasa": ("A relationship between the Lord and the living entities.", "NOD"),
    "guru": ("Spiritual master.", "BG Glossary"),
    "parampara": ("Disciplic succession.", "BG Glossary"),
    "sampradaya": ("A chain of disciplic succession.", "CC Glossary"),
    "diksa": ("Spiritual initiation.", "CC Glossary"),
    "sankirtana": ("Congregational chanting of the holy names of God.", "CC Glossary"),
    "japa": ("Soft chanting of the holy names of God.", "CC Glossary"),
    "prasadam": ("The Lord's mercy; food offered to the Lord.", "BG Glossary"),
    "murti": ("The form of the Lord in the temple.", "SB Glossary"),
    "tattva": ("Truth; reality.", "CC Glossary"),
    "lila": ("Pastimes of the Supreme Lord.", "CC Glossary"),
    "svarupa": ("The eternal constitutional form of the soul.", "CC Glossary"),
    "acarya": ("A spiritual master who teaches by example.", "BG Glossary"),
    "sadhu": ("A saintly person; a devotee.", "BG Glossary"),
    "sastra": ("Revealed scriptures.", "BG Glossary"),
    "vaisnava": ("A devotee of Lord Visnu or Krsna.", "CC Glossary"),
    "seva": ("Service, especially devotional service to the Lord.", "CC Glossary"),
    "kirtana": ("Glorification of the Lord, especially by chanting.", "CC Glossary"),
    "arcana": ("Deity worship.", "SB Glossary"),
    "mantra": ("A transcendental sound vibration.", "BG Glossary"),
    "yoga": ("Linking the consciousness with the Supreme.", "BG Glossary"),
    "jnana": ("Knowledge; especially spiritual knowledge.", "BG Glossary"),
    "moksa": ("Liberation from the cycle of birth and death.", "BG Glossary"),
    "samsara": ("The cycle of repeated birth and death.", "BG Glossary"),
}


def build_glossary(
    text: str,
    segments: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Build glossary entries from domain terms found in the text.

    Deterministic: uses DOMAIN_VOCABULARY matching and GLOSSARY_DEFINITIONS.

    Args:
        text: Transcript text to analyze.
        segments: Optional segments for first-occurrence tracking.

    Returns:
        list of dicts matching GlossaryEntry schema fields.
    """
    entries: list[dict] = []
    seen_terms: set[str] = set()

    # Search for each known term in the text
    text_lower = text.lower()
    for term in DOMAIN_VOCABULARY:
        term_lower = term.lower()
        if term_lower in text_lower and term_lower not in seen_terms:
            # Check if we have a definition
            definition_key = term_lower.replace("ā", "a").replace("ī", "i").replace(
                "ū", "u").replace("ṛ", "r").replace("ṣ", "s").replace("ṇ", "n"
            ).replace("ṁ", "m").replace("ḥ", "h")

            # Try to find a matching definition
            defn = None
            source = None
            for key, (d, s) in GLOSSARY_DEFINITIONS.items():
                if key == definition_key or key == term_lower:
                    defn = d
                    source = s
                    break

            if defn is None:
                continue  # Skip terms without Prabhupada-sourced definitions

            # Determine category
            category = _categorize_for_glossary(term)

            # Find first occurrence segment
            first_seg = None
            if segments:
                for i, seg in enumerate(segments):
                    if term_lower in seg.get("text", "").lower():
                        first_seg = i
                        break

            seen_terms.add(term_lower)
            entries.append({
                "term": term,
                "definition": defn,
                "category": category,
                "source": source,
                "first_occurrence_segment": first_seg,
            })

    # Sort by first occurrence
    entries.sort(key=lambda e: e.get("first_occurrence_segment") or 999)
    logger.info("Built glossary with %d entries", len(entries))
    return entries


def build_thematic_index(
    text: str,
    references: list[dict],
    verifications: list[dict],
) -> dict:
    """
    Identify themes from the lecture content.

    Deterministic approach:
    1. Count scripture reference frequencies to identify focus
    2. Detect philosophical concept keywords
    3. Identify the primary topic based on frequency analysis

    Args:
        text: Transcript text.
        references: Identified references.
        verifications: Verification results with content.

    Returns:
        dict matching ThematicIndex schema fields.
    """
    themes: list[dict] = []
    text_lower = text.lower()

    # Analyze scripture focus
    scripture_counts: Counter = Counter()
    for ref in references:
        scripture_counts[ref["scripture"]] += 1

    scripture_focus = None
    if scripture_counts:
        most_common = scripture_counts.most_common(1)[0]
        scripture_map = {
            "BG": "Bhagavad-gita",
            "SB": "Srimad-Bhagavatam",
            "CC": "Caitanya-caritamrita",
            "NOI": "Nectar of Instruction",
            "ISO": "Sri Isopanisad",
        }
        scripture_focus = scripture_map.get(most_common[0], most_common[0])

    # Detect philosophical themes from keyword frequency
    theme_keywords: dict[str, list[str]] = {
        "Devotional Service (Bhakti)": ["bhakti", "devotion", "service", "seva", "worship"],
        "Surrender": ["surrender", "saranagati", "take shelter", "depend on"],
        "Knowledge (Jnana)": ["knowledge", "jnana", "understand", "realize"],
        "Renunciation (Vairagya)": ["renunciation", "detachment", "vairagya", "give up"],
        "Holy Name": ["chanting", "holy name", "hare krsna", "mantra", "japa", "kirtana"],
        "Guru-Disciple": ["guru", "spiritual master", "disciple", "parampara", "initiation"],
        "Soul and Supersoul": ["soul", "atma", "spirit", "consciousness", "paramatma"],
        "Material Nature (Maya)": ["maya", "illusion", "material", "attachment", "modes"],
        "Liberation (Moksa)": ["liberation", "moksa", "free", "transcend"],
        "Love of God (Prema)": ["love", "prema", "affection", "rasa"],
    }

    for theme_name, keywords in theme_keywords.items():
        count = sum(text_lower.count(kw) for kw in keywords)
        if count >= 3:  # Minimum threshold
            confidence = min(1.0, count / 20)  # Normalize
            evidence_kws = [kw for kw in keywords if kw in text_lower]
            themes.append({
                "tag": theme_name,
                "confidence": round(confidence, 2),
                "evidence": f"Keywords found: {', '.join(evidence_kws[:5])}",
                "related_references": [
                    r["canonical_ref"] for r in references[:3]
                ],
            })

    # Sort by confidence
    themes.sort(key=lambda t: t["confidence"], reverse=True)

    # Determine primary topic
    if themes:
        primary = themes[0]["tag"]
    elif scripture_focus:
        primary = f"Study of {scripture_focus}"
    else:
        primary = "Gaudiya Vaishnava Discourse"

    return {
        "themes": themes[:10],  # Top 10 themes
        "primary_topic": primary,
        "scripture_focus": scripture_focus,
    }


def _categorize_for_glossary(term: str) -> str:
    """Categorize a term for glossary entry."""
    term_lower = term.lower()
    for name in DEITY_NAMES + ACARYA_NAMES:
        if term_lower == name.lower():
            return "historical"
    for name in SCRIPTURE_NAMES:
        if term_lower == name.lower():
            return "general"
    for concept in PHILOSOPHICAL_TERMS:
        if term_lower == concept.lower():
            return "philosophical"
    for place in PLACE_NAMES:
        if term_lower == place.lower():
            return "general"
    return "sanskrit"


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class GlossaryBuildInput(BaseModel):
    text: str = Field(..., description="Transcript text to build glossary from")


class GlossaryBuildTool(BaseTool):
    name: str = "build_glossary"
    description: str = (
        "Build a glossary of Sanskrit/Vaishnava terms from transcript text. "
        "Definitions are sourced from Prabhupada's book glossaries."
    )
    args_schema: type[BaseModel] = GlossaryBuildInput

    def _run(self, text: str) -> str:
        import json
        entries = build_glossary(text)
        return json.dumps(entries)
