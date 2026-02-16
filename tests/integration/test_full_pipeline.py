"""
Integration test: Full pipeline end-to-end.

Marked 'slow' — requires ffmpeg, faster-whisper model, and internet.
Run with: pytest -m slow
"""

from __future__ import annotations

import pytest


@pytest.mark.slow
@pytest.mark.integration
class TestFullPipeline:
    """Integration tests that require real dependencies.

    These tests are skipped by default. Run with:
        pytest -m slow tests/integration/
    """

    def test_single_url_placeholder(self):
        """Placeholder for real end-to-end test with a live URL.

        To run manually:
            python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE" \
                --title "Test" --output output/ -v
        """
        pytest.skip("Requires live audio URL, ffmpeg, and internet access")

    def test_multi_url_placeholder(self):
        """Placeholder for multi-URL end-to-end test."""
        pytest.skip("Requires live audio URLs, ffmpeg, and internet access")
