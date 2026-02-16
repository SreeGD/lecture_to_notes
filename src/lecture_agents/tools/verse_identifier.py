"""
Enrichment Tool: Identify scripture references in transcript text.

Uses regex patterns to detect verse citations like "BG 2.47", "SB 1.2.6",
"Caitanya-caritamrita Adi 1.1", "chapter 2, verse 47", etc.
Supports ordinal numbers ("3rd Canto 13th Chapter") and spoken forms
("fourth verse of Nectar of Instruction").
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Ordinal number normalization
# ---------------------------------------------------------------------------

# Word ordinals → digit strings
_WORD_ORDINALS: dict[str, str] = {
    "first": "1", "second": "2", "third": "3", "fourth": "4",
    "fifth": "5", "sixth": "6", "seventh": "7", "eighth": "8",
    "ninth": "9", "tenth": "10", "eleventh": "11", "twelfth": "12",
    "thirteenth": "13", "fourteenth": "14", "fifteenth": "15",
    "sixteenth": "16", "seventeenth": "17", "eighteenth": "18",
    "nineteenth": "19", "twentieth": "20",
}

# Regex for suffixed ordinals: "3rd", "13th", "1st", "2nd"
_SUFFIXED_ORDINAL_RE = re.compile(r"\b(\d{1,3})(?:st|nd|rd|th)\b", re.IGNORECASE)

# Regex for word ordinals
_WORD_ORDINAL_RE = re.compile(
    r"\b(" + "|".join(_WORD_ORDINALS.keys()) + r")\b",
    re.IGNORECASE,
)


def _normalize_ordinals(text: str) -> str:
    """Convert ordinal words and suffixed numbers to plain digits.

    '3rd' → '3', 'third' → '3', '13th' → '13', 'fourth' → '4'.
    """
    # Replace suffixed ordinals first: "3rd" → "3"
    result = _SUFFIXED_ORDINAL_RE.sub(lambda m: m.group(1), text)
    # Replace word ordinals: "third" → "3"
    result = _WORD_ORDINAL_RE.sub(
        lambda m: _WORD_ORDINALS[m.group(1).lower()], result,
    )
    return result


# ---------------------------------------------------------------------------
# Regex patterns for scripture references
# ---------------------------------------------------------------------------

# Each pattern returns groups that map to (scripture, chapter, verse)
# Order matters: more specific patterns first

VERSE_PATTERNS: list[tuple[str, re.Pattern]] = [
    # "BG 2.47", "Bg. 18.66", "BG 2:47"
    (
        "BG",
        re.compile(
            r"(?:Bhagavad[- ]?(?:g[iī]t[aā])|BG|Bg\.?)\s*"
            r"(\d{1,2})[.:\s]+(\d{1,3}(?:\s*-\s*\d{1,3})?)",
            re.IGNORECASE,
        ),
    ),
    # "Bhagavad-gita chapter 2, verse 47" (verbose form)
    (
        "BG",
        re.compile(
            r"(?:Bhagavad[- ]?(?:g[iī]t[aā])|BG|Bg\.?)[,\s]*"
            r"chapter\s+(\d{1,2})[,\s]*verse\s+(\d{1,3})",
            re.IGNORECASE,
        ),
    ),
    # "SB 1.2.6", "Srimad-Bhagavatam 1.2.6"
    (
        "SB",
        re.compile(
            r"(?:(?:[SŚ]r[iī]mad[- ]?)?[Bb]h[aā]gavatam|SB)\s*"
            r"(\d{1,2})[.](\d{1,2})[.](\d{1,3}(?:\s*-\s*\d{1,3})?)",
            re.IGNORECASE,
        ),
    ),
    # "SB canto 1, chapter 2, verse 6" (verbose form)
    (
        "SB",
        re.compile(
            r"(?:(?:[SŚ]r[iī]mad[- ]?)?[Bb]h[aā]gavatam|SB)[,\s]*"
            r"canto\s+(\d{1,2})[,\s]*chapter\s+(\d{1,2})[,\s]*verse\s+(\d{1,3})",
            re.IGNORECASE,
        ),
    ),
    # "3rd Canto 13th Chapter text no. 4" / "Canto 3 Chapter 13 verse 4"
    # (standalone canto/chapter/verse — implies SB)
    (
        "SB_CANTO",
        re.compile(
            r"(\d{1,2})\s*canto\s+(\d{1,2})\s*chapter"
            r"(?:[.\s]*(?:text|verse)\s+(?:no\.?\s*)?(\d{1,3}))?",
            re.IGNORECASE,
        ),
    ),
    # "canto 3, chapter 13" (reverse word order: "canto X chapter Y")
    (
        "SB_CANTO",
        re.compile(
            r"canto\s+(\d{1,2})[,\s]+chapter\s+(\d{1,2})"
            r"(?:[,.\s]*(?:text|verse)\s+(?:no\.?\s*)?(\d{1,3}))?",
            re.IGNORECASE,
        ),
    ),
    # "Text No. 4" or "Text number 4" — standalone, captures verse only
    # (canto/chapter inferred from nearby context via _resolve_standalone_text_no)
    (
        "TEXT_NO",
        re.compile(
            r"(?:Text|Verse)\s+(?:No\.?\s*|Number\s+)(\d{1,3})",
            re.IGNORECASE,
        ),
    ),
    # "CC Adi 1.1", "Caitanya-caritamrita Madhya 22.93"
    (
        "CC",
        re.compile(
            r"(?:Caitanya[- ]?carit[aā]m[rṛ]ta|CC)\s*"
            r"([AaĀā]di|[Mm]adhya|[Aa]ntya)\s*"
            r"(\d{1,2})[.](\d{1,3}(?:\s*-\s*\d{1,3})?)",
            re.IGNORECASE,
        ),
    ),
    # "NOI 1", "Nectar of Instruction text 1"
    (
        "NOI",
        re.compile(
            r"(?:Nectar\s+of\s+Instruction|NOI|Upadeshamrita|Upadeśāmṛta)\s*"
            r"(?:text\s+)?(\d{1,2})",
            re.IGNORECASE,
        ),
    ),
    # "fourth verse of Nectar of Instruction" / "verse 4 of Nectar of Instruction"
    # After ordinal normalization: "4 verse of ..." or "verse 4 of ..."
    (
        "NOI",
        re.compile(
            r"(?:(?:verse|text)\s+(\d{1,2})|(\d{1,2})\s+(?:verse|text))\s+of\s+"
            r"(?:Nectar\s+of\s+Instruction|Upadeshamrita|Upadeśāmṛta)",
            re.IGNORECASE,
        ),
    ),
    # "ISO 1", "Sri Isopanisad mantra 1"
    (
        "ISO",
        re.compile(
            r"(?:[SŚ]r[iī]\s+[IĪ][sś]opani[sṣ]ad|ISO|Isopanisad)\s*"
            r"(?:mantra\s+)?(\d{1,2})",
            re.IGNORECASE,
        ),
    ),
    # "Brahma-samhita 5.1", "BS 5.1"
    (
        "BS",
        re.compile(
            r"(?:Brahma[- ]?sa[mṁ]hit[aā]|BS)\s*"
            r"(\d{1,2})[.](\d{1,3})",
            re.IGNORECASE,
        ),
    ),
]


def _find_nearby_canto_chapter(text: str, match_pos: int) -> tuple[str, str] | None:
    """Search backwards from a 'Text No. X' match to find canto/chapter context.

    Looks within the preceding 300 characters for canto and chapter numbers.
    Returns (canto, chapter) or None.
    """
    window_start = max(0, match_pos - 300)
    window = text[window_start:match_pos]
    # Normalize ordinals in the window
    window = _normalize_ordinals(window)

    # Look for "N canto" or "canto N"
    canto_m = re.search(r"(\d{1,2})\s*canto|canto\s+(\d{1,2})", window, re.IGNORECASE)
    chapter_m = re.search(r"(\d{1,2})\s*chapter|chapter\s+(\d{1,2})", window, re.IGNORECASE)

    if canto_m and chapter_m:
        canto = canto_m.group(1) or canto_m.group(2)
        chapter = chapter_m.group(1) or chapter_m.group(2)
        return (canto, chapter)
    return None


def identify_references(
    text: str,
    segments: Optional[list[dict]] = None,
) -> list[dict]:
    """
    Identify scripture references in transcript text using regex patterns.

    Runs patterns on both original text and ordinal-normalized text to
    catch forms like "3rd Canto 13th Chapter" and "fourth verse".

    Args:
        text: Full transcript text to search.
        segments: Optional timestamped segments for locating references.

    Returns:
        list of dicts with keys: scripture, chapter, verse, canonical_ref,
        segment_index, context_text.
    """
    references: list[dict] = []
    seen_refs: set[str] = set()

    # Run on both original and ordinal-normalized text
    normalized = _normalize_ordinals(text)
    text_variants = [(text, text), (normalized, text)]  # (search_text, context_text)

    for search_text, ctx_text in text_variants:
        for scripture_abbrev, pattern in VERSE_PATTERNS:
            for match in pattern.finditer(search_text):
                groups = match.groups()

                # Build chapter and verse from captured groups
                if scripture_abbrev == "BG":
                    chapter, verse = groups[0], groups[1]
                    canonical = f"BG {chapter}.{verse}"
                    scripture_out = "BG"
                elif scripture_abbrev == "SB":
                    if len(groups) == 3:
                        chapter = f"{groups[0]}.{groups[1]}"
                        verse = groups[2]
                    else:
                        chapter = groups[0]
                        verse = groups[1]
                    canonical = f"SB {chapter}.{verse}"
                    scripture_out = "SB"
                elif scripture_abbrev == "SB_CANTO":
                    canto = groups[0]
                    chap = groups[1]
                    verse = groups[2] if groups[2] else None
                    if not verse:
                        continue  # Need at least canto.chapter.verse
                    chapter = f"{canto}.{chap}"
                    canonical = f"SB {canto}.{chap}.{verse}"
                    scripture_out = "SB"
                elif scripture_abbrev == "TEXT_NO":
                    verse = groups[0]
                    # Try to resolve canto/chapter from nearby context
                    context_info = _find_nearby_canto_chapter(
                        search_text, match.start(),
                    )
                    if not context_info:
                        continue  # Can't determine canto/chapter
                    canto, chap = context_info
                    chapter = f"{canto}.{chap}"
                    canonical = f"SB {canto}.{chap}.{verse}"
                    scripture_out = "SB"
                elif scripture_abbrev == "CC":
                    division = groups[0].title()
                    chapter_num = groups[1]
                    verse = groups[2]
                    chapter = f"{division}.{chapter_num}"
                    canonical = f"CC {division} {chapter_num}.{verse}"
                    scripture_out = "CC"
                elif scripture_abbrev in ("NOI", "ISO"):
                    chapter = ""
                    # Handle alternation groups (e.g. NOI "verse N of" / "N verse of")
                    verse = next((g for g in groups if g is not None), None)
                    if not verse:
                        continue
                    canonical = f"{scripture_abbrev} {verse}"
                    scripture_out = scripture_abbrev
                elif scripture_abbrev == "BS":
                    chapter, verse = groups[0], groups[1]
                    canonical = f"BS {chapter}.{verse}"
                    scripture_out = "BS"
                else:
                    continue

                # Normalize whitespace in verse (remove spaces around hyphens)
                verse = re.sub(r"\s*-\s*", "-", verse.strip())
                canonical = re.sub(r"\s+", " ", canonical.strip())

                # Deduplicate
                if canonical in seen_refs:
                    continue
                seen_refs.add(canonical)

                # Find segment index if segments provided
                segment_index = 0
                if segments:
                    match_pos = match.start()
                    char_pos = 0
                    for i, seg in enumerate(segments):
                        seg_text = seg.get("text", "")
                        char_pos += len(seg_text) + 1  # +1 for space
                        if char_pos > match_pos:
                            segment_index = i
                            break

                # Extract context from original text
                start = max(0, match.start() - 50)
                end = min(len(ctx_text), match.end() + 50)
                context = ctx_text[start:end].strip()

                references.append({
                    "scripture": scripture_out,
                    "chapter": chapter,
                    "verse": verse,
                    "canonical_ref": canonical,
                    "segment_index": segment_index,
                    "context_text": context,
                })

    # Sort by position in text
    references.sort(key=lambda r: r["segment_index"])

    logger.info("Identified %d scripture references", len(references))
    return references


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class VerseIdentifyInput(BaseModel):
    text: str = Field(..., description="Transcript text to search for references")


class VerseIdentifyTool(BaseTool):
    name: str = "identify_verse_references"
    description: str = (
        "Identify scripture references (BG, SB, CC, etc.) in transcript text "
        "using regex patterns. Returns canonical references for verification."
    )
    args_schema: type[BaseModel] = VerseIdentifyInput

    def _run(self, text: str) -> str:
        import json
        refs = identify_references(text)
        return json.dumps(refs)
