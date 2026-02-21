"""
Orchestrator: Coordinates all five agents in the Lecture-to-Notes pipeline.

Provides two modes:
- Single URL: Linear Download -> Transcribe -> Enrich -> Compile -> (optional) PDF
- Multi URL: Fan-out (Download+Transcribe+Enrich each URL), Fan-in (Compile all)

Supports --from-agent N to resume from any agent, loading earlier outputs
from JSON checkpoints saved in output_dir/checkpoints/.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from lecture_agents.agents.compiler_agent import run_compiler_pipeline
from lecture_agents.agents.downloader_agent import run_download_pipeline
from lecture_agents.agents.enrichment_agent import run_enrichment_pipeline
from lecture_agents.agents.pdf_agent import run_pdf_pipeline
from lecture_agents.agents.transcriber_agent import run_transcription_pipeline
from lecture_agents.agents.validation_agent import run_validation_pipeline
from lecture_agents.checkpoint import (
    load_book_checkpoint,
    load_enriched_checkpoint,
    load_manifest_checkpoint,
    load_transcript_checkpoint,
    save_book_checkpoint,
    save_enriched_checkpoint,
    save_manifest_checkpoint,
    save_transcript_checkpoint,
    save_validation_checkpoint,
    validate_checkpoints_for_from_agent,
)
from lecture_agents.config.constants import (
    PIPELINE_CACHE_DIR,
    PIPELINE_OUTPUT_DIR,
    VEDABASE_CACHE_FILE,
    WHISPER_MODEL_SIZE,
    WHISPER_VAD_FILTER,
)
from lecture_agents.exceptions import PipelineError
from lecture_agents.schemas.compiler_output import BookOutput
from lecture_agents.schemas.pdf_output import PDFOutput
from lecture_agents.schemas.pipeline_state import (
    PipelineState,
    PerURLState,
    URLStatus,
)
from lecture_agents.utils import resolve_run_dir

logger = logging.getLogger(__name__)


def run_single_url_pipeline(
    url: str,
    title: str = "Lecture Notes",
    output_dir: str = PIPELINE_OUTPUT_DIR,
    speaker: Optional[str] = None,
    whisper_model: str = WHISPER_MODEL_SIZE,
    enable_diarization: bool = False,
    enable_llm: bool = False,
    generate_pdf: bool = False,
    cache_path: str = VEDABASE_CACHE_FILE,
    vad_filter: bool = WHISPER_VAD_FILTER,
    from_agent: int = 1,
    progress_callback: Optional[callable] = None,
    whisper_backend: str = "faster-whisper",
    prompt: Optional[str] = None,
    enrichment_mode: str = "auto",
) -> tuple[BookOutput, Optional[PDFOutput]]:
    """
    Run the full pipeline for a single URL.

    Download -> Transcribe -> Enrich -> Compile -> (optional) PDF

    Args:
        url: Audio source URL (YouTube, HTTP, or local file path).
        title: Book title.
        output_dir: Output directory for the final book.
        speaker: Speaker name (optional).
        whisper_model: Whisper model size.
        enable_diarization: Enable speaker diarization.
        enable_llm: Enable LLM post-processing.
        generate_pdf: Generate a styled PDF from the compiled book.
        cache_path: Path to vedabase.io cache file.
        vad_filter: Enable voice activity detection filter.
        from_agent: Start from this agent (1-5), loading earlier outputs
            from checkpoints. Default 1 runs the full pipeline.
        prompt: Custom user instructions for LLM enrichment.
        enrichment_mode: "auto", "verse-centric", or "lecture-centric".

    Returns:
        Tuple of (BookOutput, PDFOutput or None).
    """
    if from_agent < 1 or from_agent > 5:
        raise PipelineError(f"--from-agent must be between 1 and 5, got {from_agent}")

    # Resolve per-URL run directory
    output_dir = resolve_run_dir(
        base_output=output_dir,
        url=url,
        from_agent=from_agent,
    )
    logger.info("Run directory: %s", output_dir)

    if from_agent > 1:
        validate_checkpoints_for_from_agent(from_agent, output_dir, url_count=1)

    state = PipelineState(
        run_id=str(uuid.uuid4())[:8],
        mode="single",
        output_dir=Path(output_dir),
        started_at=datetime.now(),
        book_title=title,
        speaker=speaker or "",
    )
    url_state = state.add_url(url, order=1)

    total_steps = 5 if generate_pdf else 4

    try:
        # Step 1: Download
        if from_agent <= 1:
            logger.info("[%s] Step 1/%d: Downloading %s", state.run_id, total_steps, url)
            if progress_callback:
                progress_callback("downloading", f"Downloading audio from {url}")
            url_state.status = URLStatus.DOWNLOADING
            manifest = run_download_pipeline(
                urls=[url],
                output_dir=str(Path(output_dir) / "audio"),
            )

            if not manifest.results or not manifest.results[0].success:
                error = manifest.results[0].error if manifest.results else "Download failed"
                url_state.status = URLStatus.FAILED
                url_state.error = error
                raise PipelineError(f"Download failed for {url}: {error}")

            audio_path = manifest.results[0].audio_path
            url_state.audio_path = Path(audio_path)
            url_state.status = URLStatus.DOWNLOADED
            save_manifest_checkpoint(manifest, output_dir)
            if progress_callback:
                duration = manifest.results[0].metadata.duration_seconds if manifest.results[0].metadata else 0
                progress_callback("downloading", f"Downloaded: {Path(audio_path).name} ({duration:.0f}s)")
            logger.info("[%s] Downloaded: %s", state.run_id, audio_path)
        else:
            logger.info("[%s] Skipping download (--from-agent %d)", state.run_id, from_agent)
            manifest = load_manifest_checkpoint(output_dir)
            audio_path = manifest.results[0].audio_path
            url_state.audio_path = Path(audio_path)
            url_state.status = URLStatus.DOWNLOADED

        # Auto-derive title from source filename if user didn't provide one
        if title == "Lecture Notes" and manifest.results and manifest.results[0].original_path:
            title = Path(manifest.results[0].original_path).stem

        # Step 2: Transcribe
        if from_agent <= 2:
            logger.info("[%s] Step 2/%d: Transcribing", state.run_id, total_steps)
            if progress_callback:
                backend_label = "whisper.cpp" if whisper_backend == "whisper.cpp" else f"Whisper {whisper_model}"
                progress_callback("transcribing", f"Transcribing with {backend_label}")
            url_state.status = URLStatus.TRANSCRIBING
            transcript = run_transcription_pipeline(
                audio_path=audio_path,
                model_size=whisper_model,
                enable_diarization=enable_diarization,
                enable_llm_postprocess=enable_llm,
                speaker_name=speaker,
                vad_filter=vad_filter,
                whisper_backend=whisper_backend,
            )
            url_state.transcript_output = transcript
            url_state.status = URLStatus.TRANSCRIBED
            save_transcript_checkpoint(transcript, output_dir, order=1)
            if progress_callback:
                progress_callback(
                    "transcribing",
                    f"Transcribed: {len(transcript.segments)} segments, "
                    f"{transcript.duration_seconds:.0f}s audio",
                )
            logger.info(
                "[%s] Transcribed: %d segments, %.0fs",
                state.run_id, len(transcript.segments), transcript.duration_seconds,
            )
        else:
            logger.info("[%s] Skipping transcription (--from-agent %d)", state.run_id, from_agent)
            transcript = load_transcript_checkpoint(output_dir, order=1)
            url_state.transcript_output = transcript
            url_state.status = URLStatus.TRANSCRIBED

        # Step 3: Enrich
        if from_agent <= 3:
            logger.info("[%s] Step 3/%d: Enriching", state.run_id, total_steps)
            if progress_callback:
                progress_callback("enriching", "Identifying and verifying scripture references via vedabase.io")
            url_state.status = URLStatus.ENRICHING
            enriched = run_enrichment_pipeline(
                transcript=transcript,
                cache_path=cache_path,
                enable_llm=enable_llm,
                user_prompt=prompt,
                enrichment_mode=enrichment_mode,
            )
            url_state.enriched_output = enriched
            url_state.status = URLStatus.ENRICHED
            save_enriched_checkpoint(enriched, output_dir, order=1)
            if progress_callback:
                progress_callback(
                    "enriching",
                    f"Enriched: {len(enriched.references_found)} references found, "
                    f"{len(enriched.verifications)} verified",
                )
            logger.info(
                "[%s] Enriched: %d refs, %d verified",
                state.run_id, len(enriched.references_found), len(enriched.verifications),
            )
        else:
            logger.info("[%s] Skipping enrichment (--from-agent %d)", state.run_id, from_agent)
            enriched = load_enriched_checkpoint(output_dir, order=1)
            url_state.enriched_output = enriched
            url_state.status = URLStatus.ENRICHED

        # Step 3.5: Validate
        logger.info("[%s] Validating transcription and enrichment quality", state.run_id)
        if progress_callback:
            progress_callback("validating", "Validating transcription and enrichment quality")
        url_state.status = URLStatus.VALIDATING
        validation_report = run_validation_pipeline(
            transcript=transcript,
            enriched=enriched,
        )
        url_state.status = URLStatus.VALIDATED
        save_validation_checkpoint(validation_report, output_dir, order=1)
        if progress_callback:
            progress_callback(
                "validating",
                f"Validated: {validation_report.critical_failures} critical, "
                f"{validation_report.warnings} warnings",
            )
        logger.info(
            "[%s] Validation: %d critical, %d warnings",
            state.run_id, validation_report.critical_failures, validation_report.warnings,
        )

        # Step 4: Compile
        if from_agent <= 4:
            logger.info("[%s] Step 4/%d: Compiling", state.run_id, total_steps)
            if progress_callback:
                progress_callback("compiling", "Compiling enriched notes into structured Markdown book")
            url_state.status = URLStatus.COMPILING
            # Extract original URL from manifest for source references
            orig_urls = [r.url for r in manifest.results if r.success]
            book = run_compiler_pipeline(
                enriched_notes_list=[enriched],
                transcript_outputs=[transcript],
                title=title,
                output_dir=output_dir,
                mode="single",
                speaker=speaker,
                original_urls=orig_urls,
            )
            url_state.status = URLStatus.COMPILED
            save_book_checkpoint(book, output_dir)
            if progress_callback:
                progress_callback(
                    "compiling",
                    f"Compiled: {book.report.total_chapters} chapters, "
                    f"{book.report.total_words} words",
                )
            logger.info("[%s] Compiled: %s", state.run_id, book.output_path)
        else:
            logger.info("[%s] Skipping compilation (--from-agent %d)", state.run_id, from_agent)
            book = load_book_checkpoint(output_dir)
            url_state.status = URLStatus.COMPILED

        # Step 5: PDF (optional)
        pdf_output: Optional[PDFOutput] = None
        if generate_pdf:
            logger.info("[%s] Step 5/%d: Generating PDF", state.run_id, total_steps)
            if progress_callback:
                progress_callback("pdf_generating", "Generating styled PDF from Markdown")
            url_state.status = URLStatus.PDF_GENERATING
            pdf_output = run_pdf_pipeline(
                book_output=book,
                output_dir=output_dir,
            )
            url_state.pdf_path = Path(pdf_output.pdf_path)
            url_state.status = URLStatus.PDF_GENERATED
            if progress_callback:
                progress_callback(
                    "pdf_generating",
                    f"PDF generated: {pdf_output.total_pages} pages, "
                    f"{pdf_output.file_size_kb:.0f} KB",
                )
            logger.info("[%s] PDF generated: %s", state.run_id, pdf_output.pdf_path)

        state.completed_at = datetime.now()
        logger.info("[%s] Complete: %s", state.run_id, book.output_path)

        return book, pdf_output

    except PipelineError:
        raise
    except Exception as e:
        url_state.status = URLStatus.FAILED
        url_state.error = str(e)
        state.errors.append({"url": url, "error": str(e)})
        raise PipelineError(f"Pipeline failed for {url}: {e}") from e


def run_multi_url_pipeline(
    urls: list[str],
    title: str = "Lecture Notes",
    output_dir: str = PIPELINE_OUTPUT_DIR,
    speaker: Optional[str] = None,
    whisper_model: str = WHISPER_MODEL_SIZE,
    enable_diarization: bool = False,
    enable_llm: bool = False,
    generate_pdf: bool = False,
    cache_path: str = VEDABASE_CACHE_FILE,
    vad_filter: bool = WHISPER_VAD_FILTER,
    from_agent: int = 1,
    progress_callback: Optional[callable] = None,
    whisper_backend: str = "faster-whisper",
    prompt: Optional[str] = None,
    enrichment_mode: str = "auto",
) -> tuple[BookOutput, Optional[PDFOutput]]:
    """
    Run the pipeline for multiple URLs (fan-out/fan-in).

    Each URL is independently downloaded, transcribed, and enriched.
    All enriched notes are then compiled into a single book.

    Args:
        urls: List of audio source URLs.
        title: Book title.
        output_dir: Output directory.
        speaker: Speaker name (optional).
        whisper_model: Whisper model size.
        enable_diarization: Enable speaker diarization.
        enable_llm: Enable LLM post-processing.
        generate_pdf: Generate a styled PDF from the compiled book.
        cache_path: Path to vedabase.io cache file.
        vad_filter: Enable voice activity detection filter.
        from_agent: Start from this agent (1-5), loading earlier outputs
            from checkpoints. Default 1 runs the full pipeline.
        prompt: Custom user instructions for LLM enrichment.
        enrichment_mode: "auto", "verse-centric", or "lecture-centric".

    Returns:
        Tuple of (BookOutput, PDFOutput or None).
    """
    if not urls:
        raise PipelineError("No URLs provided")

    if from_agent < 1 or from_agent > 5:
        raise PipelineError(f"--from-agent must be between 1 and 5, got {from_agent}")

    # Resolve per-run directory
    output_dir = resolve_run_dir(
        base_output=output_dir,
        urls=urls,
        title=title,
        from_agent=from_agent,
    )
    logger.info("Run directory: %s", output_dir)

    if from_agent > 1:
        validate_checkpoints_for_from_agent(from_agent, output_dir, url_count=len(urls))

    state = PipelineState(
        run_id=str(uuid.uuid4())[:8],
        mode="multi",
        output_dir=Path(output_dir),
        started_at=datetime.now(),
        book_title=title,
        speaker=speaker or "",
    )

    for i, url in enumerate(urls, 1):
        state.add_url(url, order=i)

    # Phase 1: Download all
    if from_agent <= 1:
        logger.info("[%s] Phase 1: Downloading %d URLs", state.run_id, len(urls))
        if progress_callback:
            progress_callback("downloading", f"Downloading {len(urls)} audio files")
        manifest = run_download_pipeline(
            urls=urls,
            output_dir=str(Path(output_dir) / "audio"),
        )
        save_manifest_checkpoint(manifest, output_dir)

        for url_state in state.url_states:
            matching = [r for r in manifest.results if r.url == url_state.url]
            if matching and matching[0].success:
                url_state.audio_path = Path(matching[0].audio_path)
                url_state.status = URLStatus.DOWNLOADED
            else:
                error = matching[0].error if matching else "Not in download results"
                url_state.status = URLStatus.FAILED
                url_state.error = error
                state.errors.append({"url": url_state.url, "error": error})
                logger.warning("[%s] Download failed: %s — %s", state.run_id, url_state.url, error)
    else:
        logger.info("[%s] Skipping downloads (--from-agent %d)", state.run_id, from_agent)
        manifest = load_manifest_checkpoint(output_dir)
        for url_state in state.url_states:
            matching = [r for r in manifest.results if r.url == url_state.url]
            if matching and matching[0].success:
                url_state.audio_path = Path(matching[0].audio_path)
                url_state.status = URLStatus.DOWNLOADED
            else:
                url_state.status = URLStatus.FAILED

    successful = [u for u in state.url_states if u.status == URLStatus.DOWNLOADED]
    if not successful:
        raise PipelineError("All downloads failed")

    # Auto-derive title from first source filename if user didn't provide one
    if title == "Lecture Notes":
        first_ok = next((r for r in manifest.results if r.success and r.original_path), None)
        if first_ok:
            title = Path(first_ok.original_path).stem

    # Phase 2: Transcribe all successful downloads
    transcripts = []
    if from_agent <= 2:
        logger.info("[%s] Phase 2: Transcribing %d files", state.run_id, len(successful))
        if progress_callback:
            backend_label = "whisper.cpp" if whisper_backend == "whisper.cpp" else f"Whisper {whisper_model}"
            progress_callback("transcribing", f"Transcribing {len(successful)} files with {backend_label}")
        for url_state in successful:
            try:
                url_state.status = URLStatus.TRANSCRIBING
                transcript = run_transcription_pipeline(
                    audio_path=str(url_state.audio_path),
                    model_size=whisper_model,
                    enable_diarization=enable_diarization,
                    enable_llm_postprocess=enable_llm,
                    speaker_name=speaker,
                    vad_filter=vad_filter,
                    whisper_backend=whisper_backend,
                )
                url_state.transcript_output = transcript
                url_state.status = URLStatus.TRANSCRIBED
                save_transcript_checkpoint(transcript, output_dir, order=url_state.order)
                transcripts.append((url_state, transcript))
            except Exception as e:
                url_state.status = URLStatus.FAILED
                url_state.error = str(e)
                state.errors.append({"url": url_state.url, "error": str(e)})
                logger.warning("[%s] Transcription failed: %s — %s", state.run_id, url_state.url, e)
    else:
        logger.info("[%s] Skipping transcription (--from-agent %d)", state.run_id, from_agent)
        for url_state in successful:
            transcript = load_transcript_checkpoint(output_dir, order=url_state.order)
            url_state.transcript_output = transcript
            url_state.status = URLStatus.TRANSCRIBED
            transcripts.append((url_state, transcript))

    if not transcripts:
        raise PipelineError("All transcriptions failed")

    # Phase 3: Enrich all transcripts
    enriched_list = []
    transcript_list = []
    if from_agent <= 3:
        logger.info("[%s] Phase 3: Enriching %d transcripts", state.run_id, len(transcripts))
        if progress_callback:
            progress_callback("enriching", f"Enriching {len(transcripts)} transcripts with vedabase.io references")
        for url_state, transcript in transcripts:
            try:
                url_state.status = URLStatus.ENRICHING
                enriched = run_enrichment_pipeline(
                    transcript=transcript,
                    cache_path=cache_path,
                    enable_llm=enable_llm,
                    user_prompt=prompt,
                    enrichment_mode=enrichment_mode,
                )
                url_state.enriched_output = enriched
                url_state.status = URLStatus.ENRICHED
                save_enriched_checkpoint(enriched, output_dir, order=url_state.order)
                enriched_list.append(enriched)
                transcript_list.append(transcript)
            except Exception as e:
                url_state.status = URLStatus.FAILED
                url_state.error = str(e)
                state.errors.append({"url": url_state.url, "error": str(e)})
                logger.warning("[%s] Enrichment failed: %s — %s", state.run_id, url_state.url, e)
    else:
        logger.info("[%s] Skipping enrichment (--from-agent %d)", state.run_id, from_agent)
        for url_state, transcript in transcripts:
            enriched = load_enriched_checkpoint(output_dir, order=url_state.order)
            url_state.enriched_output = enriched
            url_state.status = URLStatus.ENRICHED
            enriched_list.append(enriched)
            transcript_list.append(transcript)

    if not enriched_list:
        raise PipelineError("All enrichments failed")

    # Phase 3.5: Validate each enriched output
    logger.info("[%s] Validating %d transcription/enrichment outputs", state.run_id, len(enriched_list))
    if progress_callback:
        progress_callback("validating", f"Validating {len(enriched_list)} outputs")
    validated_enriched: list = []
    validated_transcripts: list = []
    for i, (enriched, transcript) in enumerate(zip(enriched_list, transcript_list)):
        try:
            validation_report = run_validation_pipeline(
                transcript=transcript,
                enriched=enriched,
            )
            save_validation_checkpoint(validation_report, output_dir, order=i + 1)
            validated_enriched.append(enriched)
            validated_transcripts.append(transcript)
        except Exception as e:
            logger.warning("[%s] Validation failed for source %d: %s", state.run_id, i + 1, e)
            state.errors.append({"phase": "validation", "error": str(e)})

    if not validated_enriched:
        raise PipelineError(
            f"All {len(enriched_list)} outputs failed validation. "
            f"Errors: {[e.get('error', '') for e in state.errors[-len(enriched_list):]]}"
        )

    if len(validated_enriched) < len(enriched_list):
        logger.warning(
            "[%s] Partial recovery: %d/%d sources passed validation, "
            "continuing with passing sources",
            state.run_id, len(validated_enriched), len(enriched_list),
        )

    if progress_callback:
        progress_callback(
            "validating",
            f"Validated: {len(validated_enriched)}/{len(enriched_list)} passed",
        )

    enriched_list = validated_enriched
    transcript_list = validated_transcripts

    # Phase 4: Compile all into one book
    if from_agent <= 4:
        logger.info("[%s] Phase 4: Compiling %d sources into book", state.run_id, len(enriched_list))
        if progress_callback:
            progress_callback("compiling", f"Compiling {len(enriched_list)} sources into structured book")
        orig_urls = [r.url for r in manifest.results if r.success]
        book = run_compiler_pipeline(
            enriched_notes_list=enriched_list,
            transcript_outputs=transcript_list,
            title=title,
            output_dir=output_dir,
            mode="multi",
            speaker=speaker,
            original_urls=orig_urls,
        )
        save_book_checkpoint(book, output_dir)
    else:
        logger.info("[%s] Skipping compilation (--from-agent %d)", state.run_id, from_agent)
        book = load_book_checkpoint(output_dir)

    for url_state in state.url_states:
        if url_state.status in (URLStatus.ENRICHED, URLStatus.VALIDATED):
            url_state.status = URLStatus.COMPILED

    # Phase 5: PDF (optional)
    pdf_output: Optional[PDFOutput] = None
    if generate_pdf:
        logger.info("[%s] Phase 5: Generating PDF", state.run_id)
        if progress_callback:
            progress_callback("pdf_generating", "Generating styled PDF from Markdown")
        pdf_output = run_pdf_pipeline(
            book_output=book,
            output_dir=output_dir,
        )
        for url_state in state.url_states:
            if url_state.status == URLStatus.COMPILED:
                url_state.pdf_path = Path(pdf_output.pdf_path)
                url_state.status = URLStatus.PDF_GENERATED
        if progress_callback:
            progress_callback(
                "pdf_generating",
                f"PDF generated: {pdf_output.total_pages} pages, {pdf_output.file_size_kb:.0f} KB",
            )
        logger.info("[%s] PDF generated: %s", state.run_id, pdf_output.pdf_path)

    state.completed_at = datetime.now()
    logger.info("[%s] Multi-URL pipeline complete: %s", state.run_id, book.output_path)

    return book, pdf_output
