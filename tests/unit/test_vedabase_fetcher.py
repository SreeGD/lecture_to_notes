"""
Tool tests for vedabase_fetcher.py and verse_identifier.py.

Tests URL building, cache behavior, HTML parsing, and reference identification.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from lecture_agents.tools.vedabase_fetcher import (
    _cache_key,
    _parse_vedabase_page,
    build_vedabase_url,
    fetch_verse,
)
from lecture_agents.tools.verse_identifier import identify_references


# ---------------------------------------------------------------------------
# URL building tests
# ---------------------------------------------------------------------------


@pytest.mark.tool
class TestBuildVedabaseUrl:

    def test_bg_url(self):
        url = build_vedabase_url("BG", "2", "47")
        assert url == "https://vedabase.io/en/library/bg/2/47/"

    def test_bg_url_case_insensitive(self):
        url = build_vedabase_url("bg", "18", "66")
        assert url == "https://vedabase.io/en/library/bg/18/66/"

    def test_sb_url(self):
        url = build_vedabase_url("SB", "1.2", "6")
        assert url == "https://vedabase.io/en/library/sb/1/2/6/"

    def test_cc_url_with_division(self):
        url = build_vedabase_url("CC", "Adi.1", "1")
        assert url == "https://vedabase.io/en/library/cc/adi/1/1/"

    def test_cc_madhya(self):
        url = build_vedabase_url("CC", "Madhya.22", "93")
        assert url == "https://vedabase.io/en/library/cc/madhya/22/93/"

    def test_noi_url(self):
        url = build_vedabase_url("NOI", "", "1")
        assert url == "https://vedabase.io/en/library/noi/1/"

    def test_iso_url(self):
        url = build_vedabase_url("ISO", "", "12")
        assert url == "https://vedabase.io/en/library/iso/12/"

    def test_unknown_scripture(self):
        url = build_vedabase_url("UNKNOWN", "1", "1")
        assert url is None

    def test_verse_range_takes_first(self):
        url = build_vedabase_url("BG", "2", "62-63")
        assert url == "https://vedabase.io/en/library/bg/2/62/"


# ---------------------------------------------------------------------------
# Cache tests
# ---------------------------------------------------------------------------


@pytest.mark.tool
class TestCache:

    def test_cache_key_format(self):
        assert _cache_key("BG", "2", "47") == "BG_2_47"
        assert _cache_key("sb", "1.2", "6") == "SB_1.2_6"

    def test_fetch_from_cache(self, tmp_path):
        cache_path = str(tmp_path / "cache.json")
        cache_data = {
            "BG_2_47": {
                "url": "https://vedabase.io/en/library/bg/2/47/",
                "verified": True,
                "translation": "You have a right to perform...",
                "verse_text": "karmany evadhikaras te",
            },
        }
        Path(cache_path).write_text(json.dumps(cache_data))

        result = fetch_verse("BG", "2", "47", cache_path=cache_path)
        assert result["fetch_source"] == "cache"
        assert result["verified"] is True
        assert "translation" in result

    def test_cache_miss_returns_not_cached(self, tmp_path):
        cache_path = str(tmp_path / "cache.json")
        Path(cache_path).write_text("{}")

        with patch("lecture_agents.tools.vedabase_fetcher.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 404
            mock_httpx.get.return_value = mock_response

            result = fetch_verse("BG", "99", "99", cache_path=cache_path)
            assert result["fetch_source"] == "not_found"

    def test_successful_fetch_is_cached(self, tmp_path):
        cache_path = str(tmp_path / "cache.json")

        mock_html = """
        <html><body>
        <div class="r-translation">Test translation text here</div>
        <div class="r-verse-text">test verse text</div>
        </body></html>
        """

        with patch("lecture_agents.tools.vedabase_fetcher.httpx") as mock_httpx:
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.text = mock_html
            mock_httpx.get.return_value = mock_response

            with patch("lecture_agents.tools.vedabase_fetcher.time.sleep"):
                result = fetch_verse("BG", "2", "47", cache_path=cache_path)

        assert result["verified"] is True
        assert result["fetch_source"] == "live"

        # Verify it was cached
        cache = json.loads(Path(cache_path).read_text())
        assert "BG_2_47" in cache


# ---------------------------------------------------------------------------
# HTML parsing tests
# ---------------------------------------------------------------------------


@pytest.mark.tool
class TestParseVedabasePage:

    def test_parse_with_standard_classes(self):
        html = """
        <html><body>
        <div class="r-devanagari">कर्मण्येवाधिकारस्ते</div>
        <div class="r-verse-text">karmany evadhikaras te</div>
        <div class="r-synonyms">karmani — in prescribed duties</div>
        <div class="r-translation">You have a right to perform your prescribed duty.</div>
        <div class="r-purport">There are three considerations here. Bg. 3.30 and SB 1.2.6 are also relevant.</div>
        </body></html>
        """
        result = _parse_vedabase_page(html)
        assert result["devanagari"] == "कर्मण्येवाधिकारस्ते"
        assert "karmany" in result["verse_text"]
        assert "prescribed duty" in result["translation"]
        assert result["purport_excerpt"].startswith("There are three")
        assert "BG 3.30" in result["cross_refs_in_purport"]
        assert "SB 1.2.6" in result["cross_refs_in_purport"]

    def test_parse_empty_page(self):
        html = "<html><body><p>Page not found</p></body></html>"
        result = _parse_vedabase_page(html)
        assert not result.get("translation")


# ---------------------------------------------------------------------------
# Verse identifier tests
# ---------------------------------------------------------------------------


@pytest.mark.tool
class TestIdentifyReferences:

    def test_bg_reference(self):
        refs = identify_references("In BG 2.47 Krishna says about duty")
        assert len(refs) == 1
        assert refs[0]["canonical_ref"] == "BG 2.47"

    def test_bg_full_name(self):
        refs = identify_references("In the Bhagavad-gita 18.66 Lord Krishna says")
        assert len(refs) == 1
        assert refs[0]["canonical_ref"] == "BG 18.66"

    def test_sb_reference(self):
        refs = identify_references("SB 1.2.6 says sa vai pumsam paro dharmo")
        assert len(refs) == 1
        assert refs[0]["canonical_ref"] == "SB 1.2.6"

    def test_sb_verbose_form(self):
        refs = identify_references(
            "In the Srimad-Bhagavatam canto 1, chapter 2, verse 6"
        )
        assert len(refs) >= 1
        assert any("1" in r["chapter"] for r in refs)

    def test_cc_reference(self):
        refs = identify_references("CC Adi 1.1 is the invocation verse")
        assert len(refs) == 1
        assert refs[0]["scripture"] == "CC"

    def test_noi_reference(self):
        refs = identify_references("Nectar of Instruction text 5 explains")
        assert len(refs) == 1
        assert refs[0]["scripture"] == "NOI"

    def test_multiple_references(self):
        text = "BG 2.47 and SB 1.2.6 and CC Madhya 22.93 are all important"
        refs = identify_references(text)
        assert len(refs) == 3

    def test_no_references(self):
        refs = identify_references("There are no scripture references here.")
        assert len(refs) == 0

    def test_deduplication(self):
        text = "BG 2.47 is important. As we said, BG 2.47 is the key verse."
        refs = identify_references(text)
        assert len(refs) == 1


@pytest.mark.tool
class TestIdentifyOrdinalReferences:
    """Tests for ordinal number patterns (3rd, 13th, fourth, etc.)."""

    def test_sb_suffixed_ordinals_with_text_no(self):
        text = (
            "Today we discuss from the 3rd Canto 13th Chapter. "
            "The chapter is titled The Appearance of Lord Varaha. Text No. 4"
        )
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "SB 3.13.4" in canonicals

    def test_sb_word_ordinals(self):
        text = (
            "In the third canto, twelfth chapter, we discuss "
            "the creation. Text No. 5"
        )
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "SB 3.12.5" in canonicals

    def test_noi_word_ordinal(self):
        text = "the fourth verse of Nectar of Instruction"
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "NOI 4" in canonicals

    def test_noi_verse_of_form(self):
        text = "verse 4 of Nectar of Instruction"
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "NOI 4" in canonicals

    def test_canto_chapter_verbose(self):
        text = "canto 3 chapter 13 text no. 4"
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "SB 3.13.4" in canonicals

    def test_ordinals_do_not_break_existing(self):
        """Ordinal normalization should not break explicit numeric patterns."""
        text = "BG 2.47 and SB 1.2.6 are key verses"
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "BG 2.47" in canonicals
        assert "SB 1.2.6" in canonicals

    def test_mixed_ordinal_and_explicit(self):
        text = (
            "In the 3rd Canto 13th Chapter Text No. 4 "
            "and also Srimad-Bhagavatam 1.2.6"
        )
        refs = identify_references(text)
        canonicals = {r["canonical_ref"] for r in refs}
        assert "SB 3.13.4" in canonicals
        assert "SB 1.2.6" in canonicals
