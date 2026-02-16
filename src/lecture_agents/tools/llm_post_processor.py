"""
Transcriber Tool: LLM-based post-processing of transcripts.

Uses Claude to fix Sanskrit transliterations, correct scripture references,
clean up filler words, and detect śloka quotations.
Optional — falls back gracefully if no LLM is available.
Pure function + BaseTool wrapper pattern.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Optional

try:
    from crewai.tools import BaseTool
except ImportError:
    from pydantic import BaseModel as BaseTool  # type: ignore[assignment]

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Check for anthropic SDK
try:
    import anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False


TRANSCRIPT_CLEANUP_PROMPT = """\
You are a transcription post-processor specializing in Gaudiya Vaishnava lectures.

Given the following raw transcript segment, clean it up by:
1. Fixing Sanskrit/Bengali term transliterations (use standard Romanized forms, not IAST diacritics at this stage)
2. Correcting scripture reference formatting (e.g., "BG 2.47", "SB 1.2.6", "CC Adi 1.1")
3. Fixing proper nouns: Prabhupada, Krsna, Arjuna, Caitanya, etc.
4. Removing filler words (um, uh, you know) while preserving the speaker's natural voice
5. Restoring sentence structure and punctuation

CRITICAL RULES:
- Do NOT change the meaning of what the speaker said
- Do NOT paraphrase or rephrase — only fix errors and clean up
- Do NOT add any content that the speaker did not say
- Preserve the speaker's personality and teaching style
- Mark any Sanskrit verse quotations with [SLOKA] tags

Return ONLY the cleaned transcript text. No explanations or commentary.

Raw transcript:
{text}
"""

SLOKA_DETECTION_PROMPT = """\
Analyze this transcript segment for Sanskrit verse (śloka) quotations.

For each śloka found, return a JSON array of objects with:
- "text": the Sanskrit text as spoken
- "probable_reference": best guess of the verse reference (e.g., "BG 2.47")
- "confidence": 0.0-1.0 confidence in the reference identification

Only include actual Sanskrit verse quotations, not English translations or
paraphrased references. If no ślokas are found, return an empty array.

Transcript:
{text}
"""


def post_process_transcript_llm(
    text: str,
    segments: list[dict],
    model: str = "claude-sonnet-4-5-20250929",
) -> tuple[str, list[dict], list[dict]]:
    """
    LLM-based post-processing of transcript.

    Uses Claude to:
    1. Fix Sanskrit/Bengali transliterations
    2. Correct scripture reference formatting
    3. Clean up filler words and false starts
    4. Detect Sanskrit verse (śloka) quotations

    Falls back to returning input unchanged if LLM unavailable.

    Args:
        text: Full transcript text.
        segments: Timestamped segments from Whisper.
        model: Claude model to use.

    Returns:
        Tuple of (cleaned_text, updated_segments, detected_slokas).
    """
    if not HAS_ANTHROPIC:
        logger.warning("anthropic SDK not available; skipping LLM post-processing")
        return text, segments, []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set; skipping LLM post-processing")
        return text, segments, []

    client = anthropic.Anthropic(api_key=api_key)

    # Step 1: Clean up transcript text
    try:
        cleanup_response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{
                "role": "user",
                "content": TRANSCRIPT_CLEANUP_PROMPT.format(text=text[:8000]),
            }],
        )
        cleaned_text = cleanup_response.content[0].text.strip()
    except Exception as e:
        logger.error("LLM cleanup failed: %s", e)
        cleaned_text = text

    # Step 2: Detect ślokas
    detected_slokas: list[dict] = []
    try:
        sloka_response = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{
                "role": "user",
                "content": SLOKA_DETECTION_PROMPT.format(text=text[:8000]),
            }],
        )
        sloka_text = sloka_response.content[0].text.strip()
        # Parse JSON array from response
        json_match = re.search(r"\[.*\]", sloka_text, re.DOTALL)
        if json_match:
            detected_slokas = json.loads(json_match.group())
    except Exception as e:
        logger.error("LLM śloka detection failed: %s", e)

    # Update segments with cleaned text (best-effort alignment)
    updated_segments = _realign_segments(segments, text, cleaned_text)

    return cleaned_text, updated_segments, detected_slokas


def _realign_segments(
    segments: list[dict],
    original_text: str,
    cleaned_text: str,
) -> list[dict]:
    """
    Best-effort realignment of segments after text cleanup.

    Since LLM cleanup may change word count, we preserve original
    segment boundaries but update segment text proportionally.
    """
    if not segments:
        return segments

    # Simple approach: split cleaned text proportionally based on original word counts
    original_words_per_seg = [len(s.get("text", "").split()) for s in segments]
    total_original_words = sum(original_words_per_seg)

    if total_original_words == 0:
        return segments

    cleaned_words = cleaned_text.split()
    total_cleaned_words = len(cleaned_words)

    updated = []
    word_pos = 0
    for i, seg in enumerate(segments):
        new_seg = dict(seg)
        # Proportional word allocation
        if i < len(segments) - 1:
            word_count = max(
                1,
                round(original_words_per_seg[i] / total_original_words * total_cleaned_words),
            )
        else:
            word_count = total_cleaned_words - word_pos

        end_pos = min(word_pos + word_count, total_cleaned_words)
        new_seg["text"] = " ".join(cleaned_words[word_pos:end_pos])
        word_pos = end_pos
        updated.append(new_seg)

    return updated


# ---------------------------------------------------------------------------
# CrewAI BaseTool wrapper
# ---------------------------------------------------------------------------


class LlmPostProcessInput(BaseModel):
    text: str = Field(..., description="Transcript text to post-process")


class LlmPostProcessTool(BaseTool):
    name: str = "post_process_transcript"
    description: str = (
        "Use Claude LLM to clean up transcribed text: fix Sanskrit terms, "
        "correct scripture references, detect verse quotations."
    )
    args_schema: type[BaseModel] = LlmPostProcessInput

    def _run(self, text: str) -> str:
        cleaned, _, slokas = post_process_transcript_llm(text, [])
        return json.dumps({"cleaned_text": cleaned, "detected_slokas": slokas})
