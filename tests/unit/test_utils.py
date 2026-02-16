"""Unit tests for lecture_agents.utils — URL slug and run directory helpers."""

from __future__ import annotations

import pytest

from lecture_agents.utils import (
    LATEST_RUN_FILE,
    resolve_run_dir,
    title_to_slug,
    url_to_slug,
)


class TestUrlToSlug:

    def test_basic_url(self):
        slug = url_to_slug("https://example.com/my-lecture.mp3")
        assert slug.startswith("my-lecture_")
        assert len(slug) <= 80

    def test_long_filename_truncated(self):
        url = "https://example.com/" + "a" * 200 + ".mp3"
        slug = url_to_slug(url)
        assert len(slug) <= 80

    def test_hash_suffix_is_8_chars(self):
        slug = url_to_slug("https://example.com/test.mp3")
        # Last 8 chars are hex hash
        hash_part = slug.split("_")[-1]
        assert len(hash_part) == 8
        assert all(c in "0123456789abcdef" for c in hash_part)

    def test_different_urls_different_slugs(self):
        slug1 = url_to_slug("https://example.com/lecture1.mp3")
        slug2 = url_to_slug("https://example.com/lecture2.mp3")
        assert slug1 != slug2

    def test_same_url_same_slug(self):
        url = "https://example.com/lecture.mp3"
        assert url_to_slug(url) == url_to_slug(url)

    def test_special_characters_cleaned(self):
        slug = url_to_slug("https://example.com/My Lecture (2024).mp3")
        assert " " not in slug
        assert "(" not in slug
        assert ")" not in slug

    def test_real_iskcondesiretree_url(self):
        url = (
            "https://audio.iskcondesiretree.com/05_-_ISKCON_Chowpatty/"
            "22_-_2026/02_-_February/"
            "2026-02-11_SB_03-13-04_-_Importance_of_Association_of_"
            "Vaisnavas_-_Balaram_Shakti_Prabhu_ISKCON_Chowpatty.mp3"
        )
        slug = url_to_slug(url)
        assert "SB_03-13-04" in slug
        assert len(slug) <= 80

    def test_youtube_url(self):
        slug = url_to_slug("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert len(slug) <= 80
        # YouTube URLs have "watch" as the path component
        assert slug.startswith("watch_")

    def test_empty_path_uses_fallback(self):
        slug = url_to_slug("https://example.com/")
        assert len(slug) > 0
        assert len(slug) <= 80


class TestTitleToSlug:

    def test_custom_title(self):
        slug = title_to_slug("My Great Lecture Series", ["url1", "url2"])
        assert "My_Great_Lecture_Series" in slug

    def test_default_title_falls_back_to_url(self):
        slug = title_to_slug("Lecture Notes", ["https://example.com/lecture.mp3"])
        assert "lecture_" in slug

    def test_empty_title_falls_back(self):
        slug = title_to_slug("", ["https://example.com/lecture.mp3"])
        assert "lecture_" in slug


class TestResolveRunDir:

    def test_new_run_creates_subfolder(self, tmp_path):
        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            url="https://example.com/my-lecture.mp3",
            from_agent=1,
        )
        assert tmp_path.name not in run_dir.split("/")[-1]
        assert (tmp_path / LATEST_RUN_FILE).exists()
        # The run_dir should be a subfolder of tmp_path
        assert str(tmp_path) in run_dir
        assert run_dir != str(tmp_path)

    def test_resume_finds_existing_checkpoints(self, tmp_path):
        """When base_output/checkpoints/ exists, return base_output directly."""
        (tmp_path / "checkpoints").mkdir()
        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            url="https://example.com/my-lecture.mp3",
            from_agent=3,
        )
        assert run_dir == str(tmp_path)

    def test_resume_follows_latest_run(self, tmp_path):
        """When .latest_run marker exists, follow it."""
        slug = "my-lecture_abcd1234"
        (tmp_path / slug / "checkpoints").mkdir(parents=True)
        (tmp_path / LATEST_RUN_FILE).write_text(slug)

        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            url="https://example.com/my-lecture.mp3",
            from_agent=3,
        )
        assert run_dir == str(tmp_path / slug)

    def test_resume_scans_subfolders(self, tmp_path):
        """When no marker, scan for subfolder with checkpoints/."""
        slug = "some-lecture_12345678"
        (tmp_path / slug / "checkpoints").mkdir(parents=True)

        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            url="https://example.com/lecture.mp3",
            from_agent=3,
        )
        assert run_dir == str(tmp_path / slug)

    def test_latest_run_marker_written(self, tmp_path):
        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            url="https://example.com/test.mp3",
            from_agent=1,
        )
        marker = tmp_path / LATEST_RUN_FILE
        assert marker.exists()
        slug = marker.read_text().strip()
        assert run_dir == str(tmp_path / slug)

    def test_multi_url_with_title(self, tmp_path):
        run_dir = resolve_run_dir(
            base_output=str(tmp_path),
            urls=["url1", "url2"],
            title="Bhagavad-gita Series",
            from_agent=1,
        )
        assert "Bhagavad-gita_Series" in run_dir
