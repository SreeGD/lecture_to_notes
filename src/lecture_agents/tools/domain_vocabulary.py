"""
Transcriber Tool: Domain vocabulary management and correction.

Builds Whisper initial prompts from Gaudiya Vaishnava vocabulary and
applies fuzzy-matching corrections to common transcription errors.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

from lecture_agents.config.constants import DOMAIN_VOCABULARY

logger = logging.getLogger(__name__)

# Common Whisper misrecognitions of Sanskrit/Vaishnava terms
# Maps (lowercased) misrecognition -> correct IAST form
CORRECTION_MAP: dict[str, str] = {
    # Deities
    "krishna": "Krsna",
    "krisna": "Krsna",
    "christna": "Krsna",
    "arjun": "Arjuna",
    "rada": "Radha",
    "radha ronnie": "Radharani",
    "chetanya": "Caitanya",
    "chaitanya": "Caitanya",
    "nityanand": "Nityananda",
    "vishnu": "Visnu",
    # Acaryas
    "probe upon": "Prabhupada",
    "prabhupad": "Prabhupada",
    "prabhupada": "Prabhupada",
    "prob who pod": "Prabhupada",
    "prob upon": "Prabhupada",
    "rupa goswami": "Rupa Gosvami",
    "bhakti vinod": "Bhaktivinoda",
    # Scriptures
    "bhagavad gita": "Bhagavad-gita",
    "bhagavad-geeta": "Bhagavad-gita",
    "bhagavatam": "Bhagavatam",
    "shrimad bhagavatam": "Srimad-Bhagavatam",
    "chaitanya charitamrita": "Caitanya-caritamrita",
    # Concepts
    "bhakti": "bhakti",
    "karma": "karma",
    "dharma": "dharma",
    "moksha": "moksa",
    "samsara": "samsara",
    "parampara": "parampara",
    "diksha": "diksa",
    "sankirtan": "sankirtana",
    "kirtan": "kirtana",
    "japa": "japa",
    "mantra": "mantra",
    # Places
    "vrindavan": "Vrndavana",
    "vrindavana": "Vrndavana",
    "mayapur": "Mayapur",
    "navadwip": "Navadvipa",
}


def build_whisper_prompt(
    vocabulary: Optional[list[str]] = None,
    speaker_name: Optional[str] = None,
    context: Optional[str] = None,
) -> str:
    """
    Build an initial prompt string for Whisper from domain vocabulary.

    The prompt biases Whisper's decoder toward correctly recognizing
    domain-specific terms (Sanskrit names, scriptures, concepts).

    Args:
        vocabulary: List of domain terms. Defaults to DOMAIN_VOCABULARY.
        speaker_name: Speaker's name to include in prompt.
        context: Additional context (e.g., "lecture on Bhagavad-gita").

    Returns:
        A prompt string suitable for Whisper's initial_prompt parameter.
    """
    vocab = vocabulary or DOMAIN_VOCABULARY

    # Select a representative subset (Whisper prompt shouldn't be too long)
    # Prioritize unique, commonly misrecognized terms
    priority_terms = [
        "Krsna", "Prabhupada", "Bhagavad-gita", "Srimad-Bhagavatam",
        "Caitanya-caritamrita", "bhakti", "karma", "dharma", "prema",
        "Vrndavana", "Mayapur", "parampara", "diksa", "sankirtana",
        "Arjuna", "Radha", "Caitanya", "Nityananda", "Visnu",
        "Rupa Gosvami", "Bhaktivinoda", "Bhaktisiddhanta",
    ]

    # Add any from the full vocabulary not already in priority
    priority_set = set(priority_terms)
    additional = [t for t in vocab if t not in priority_set][:30]
    all_terms = priority_terms + additional

    parts = []
    if speaker_name:
        parts.append(f"A lecture by {speaker_name}.")
    if context:
        parts.append(context)
    parts.append(
        "Key terms: " + ", ".join(all_terms[:50]) + "."
    )

    return " ".join(parts)


def apply_vocabulary_corrections(
    text: str,
    correction_map: Optional[dict[str, str]] = None,
    fuzzy_threshold: float = 0.85,
) -> tuple[str, list[dict]]:
    """
    Apply domain vocabulary corrections to transcribed text.

    Uses exact match first, then fuzzy matching for close misrecognitions.

    Args:
        text: Transcribed text to correct.
        correction_map: Mapping of misrecognitions to corrections.
            Defaults to CORRECTION_MAP.
        fuzzy_threshold: Minimum similarity ratio for fuzzy matches (0-1).

    Returns:
        Tuple of (corrected_text, list of correction records).
    """
    corrections_map = correction_map or CORRECTION_MAP
    corrections: list[dict] = []
    result = text

    # Phase 1: Exact replacements (case-insensitive, word boundary)
    for wrong, correct in corrections_map.items():
        pattern = re.compile(r"\b" + re.escape(wrong) + r"\b", re.IGNORECASE)
        matches = pattern.findall(result)
        if matches:
            result = pattern.sub(correct, result)
            for match in matches:
                corrections.append({
                    "original": match,
                    "corrected": correct,
                    "category": _categorize_term(correct),
                })

    # Phase 2: Fuzzy matching for remaining potential misrecognitions
    words = result.split()
    for i, word in enumerate(words):
        clean_word = word.strip(".,;:!?\"'()[]")
        if len(clean_word) < 4:
            continue
        # Check against domain vocabulary
        for domain_term in DOMAIN_VOCABULARY:
            if clean_word.lower() == domain_term.lower():
                break  # Already correct
            ratio = SequenceMatcher(None, clean_word.lower(), domain_term.lower()).ratio()
            if ratio >= fuzzy_threshold and ratio < 1.0:
                corrections.append({
                    "original": clean_word,
                    "corrected": domain_term,
                    "category": _categorize_term(domain_term),
                })
                # Replace in the word list, preserving surrounding punctuation
                words[i] = word.replace(clean_word, domain_term)
                break

    corrected_text = " ".join(words) if words != text.split() else result

    return corrected_text, corrections


def _categorize_term(term: str) -> str:
    """Categorize a domain term for correction logging."""
    from lecture_agents.config.constants import (
        ACARYA_NAMES,
        DEITY_NAMES,
        PHILOSOPHICAL_TERMS,
        SCRIPTURE_NAMES,
    )

    term_lower = term.lower()
    for name in DEITY_NAMES + ACARYA_NAMES:
        if term_lower == name.lower():
            return "name"
    for name in SCRIPTURE_NAMES:
        if term_lower == name.lower():
            return "scripture"
    for concept in PHILOSOPHICAL_TERMS:
        if term_lower == concept.lower():
            return "sanskrit"
    return "sanskrit"  # default for domain terms


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class VocabCorrectionInput(BaseModel):
    text: str = Field(..., description="Text to apply vocabulary corrections to")


class VocabCorrectionTool(BaseTool):
    name: str = "apply_vocabulary_corrections"
    description: str = (
        "Apply Gaudiya Vaishnava domain vocabulary corrections to "
        "transcribed text. Fixes common Whisper misrecognitions of "
        "Sanskrit/Bengali terms."
    )
    args_schema: type[BaseModel] = VocabCorrectionInput

    def _run(self, text: str) -> str:
        import json
        corrected, corrections = apply_vocabulary_corrections(text)
        return json.dumps({"corrected_text": corrected, "corrections": corrections})
