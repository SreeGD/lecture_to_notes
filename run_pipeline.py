#!/usr/bin/env python3
"""
CLI entry point for the Lecture-to-Notes Pipeline.

Usage:
    # Single URL
    python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE" \
        --title "Lecture Notes" --output output/ -v

    # Multiple URLs
    python run_pipeline.py \
        "https://youtube.com/watch?v=A" \
        "https://youtube.com/watch?v=B" \
        --title "Collected Lectures" --output output/ -v

    # With diarization and LLM post-processing
    python run_pipeline.py "https://youtube.com/watch?v=EXAMPLE" \
        --title "Study Notes" --speaker "Srila Prabhupada" \
        --diarize --llm -v
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Load .env file if present (for ANTHROPIC_API_KEY, HF_TOKEN, etc.)
_env_path = Path(__file__).parent / ".env"
if _env_path.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_path)
    except ImportError:
        # Fallback: parse KEY=VALUE lines manually
        with open(_env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip())

from lecture_agents.orchestrator import (
    run_multi_url_pipeline,
    run_single_url_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Lecture-to-Notes Pipeline: Transform audio lectures into structured Markdown notes.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            '  python run_pipeline.py "https://youtube.com/watch?v=XYZ"\n'
            '  python run_pipeline.py URL1 URL2 --title "Collected Lectures"\n'
            '  python run_pipeline.py URL --speaker "Speaker Name" --diarize -v\n'
            '  python run_pipeline.py URL --from-agent 3   # Re-enrich from saved transcript\n'
        ),
    )

    parser.add_argument(
        "urls",
        nargs="+",
        help="One or more audio URLs (YouTube, HTTP, or local file paths)",
    )
    parser.add_argument(
        "--title", "-t",
        default="Lecture Notes",
        help="Book title (default: 'Lecture Notes')",
    )
    parser.add_argument(
        "--output", "-o",
        default="output",
        help="Output directory (default: 'output')",
    )
    parser.add_argument(
        "--speaker", "-s",
        default=None,
        help="Speaker name (optional)",
    )
    parser.add_argument(
        "--whisper-model", "-m",
        default="large-v3",
        help="Whisper model size (default: 'large-v3')",
    )
    parser.add_argument(
        "--no-vad",
        action="store_true",
        help="Disable Voice Activity Detection filter (useful for noisy recordings)",
    )
    parser.add_argument(
        "--diarize",
        action="store_true",
        help="Enable speaker diarization (requires pyannote.audio)",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        default=True,
        help="Enable LLM post-processing (on by default)",
    )
    parser.add_argument(
        "--no-llm",
        action="store_false",
        dest="llm",
        help="Disable LLM post-processing",
    )
    parser.add_argument(
        "--pdf",
        action="store_true",
        help="Generate a styled PDF from the compiled book (requires fpdf2)",
    )
    parser.add_argument(
        "--cache",
        default="cache/vedabase_cache.json",
        help="Path to vedabase.io cache file",
    )
    parser.add_argument(
        "--from-agent",
        type=int,
        default=1,
        choices=[1, 2, 3, 4, 5],
        metavar="N",
        help=(
            "Start pipeline from agent N, loading earlier outputs from checkpoints. "
            "1=Download (default), 2=Transcribe, 3=Enrich, 4=Compile, 5=PDF only."
        ),
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    try:
        if len(args.urls) == 1:
            book, pdf_output = run_single_url_pipeline(
                url=args.urls[0],
                title=args.title,
                output_dir=args.output,
                speaker=args.speaker,
                whisper_model=args.whisper_model,
                enable_diarization=args.diarize,
                enable_llm=args.llm,
                generate_pdf=args.pdf,
                cache_path=args.cache,
                vad_filter=not args.no_vad,
                from_agent=args.from_agent,
            )
        else:
            book, pdf_output = run_multi_url_pipeline(
                urls=args.urls,
                title=args.title,
                output_dir=args.output,
                speaker=args.speaker,
                whisper_model=args.whisper_model,
                enable_diarization=args.diarize,
                enable_llm=args.llm,
                generate_pdf=args.pdf,
                cache_path=args.cache,
                vad_filter=not args.no_vad,
                from_agent=args.from_agent,
            )

        # Show the run directory (parent of final_book.md)
        from pathlib import Path as _Path
        run_dir = str(_Path(book.output_path).parent)

        print(f"\nBook compiled successfully!")
        print(f"  Title:    {book.title}")
        print(f"  Chapters: {book.report.total_chapters}")
        print(f"  Words:    {book.report.total_words}")
        print(f"  Verses:   {book.report.total_verses_referenced} ({book.report.verified_verse_count} verified)")
        print(f"  Glossary: {book.report.total_glossary_entries} entries")
        print(f"  Run dir:  {run_dir}")
        print(f"  Output:   {book.output_path}")

        if pdf_output:
            print(f"  PDF:      {pdf_output.pdf_path}")
            print(f"  Pages:    {pdf_output.total_pages}")

        if book.report.warnings:
            print(f"\n  Warnings:")
            for w in book.report.warnings:
                print(f"    - {w}")

        return 0

    except Exception as e:
        logging.getLogger(__name__).error("Pipeline failed: %s", e, exc_info=args.verbose)
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
