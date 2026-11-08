import logging
import signal
import sys
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from error_handler import send_failure_alert
from image_handler import (
    delete_original_heic,
    has_heic_original,
    load_processed_files,
    mark_processed,
    maybe_compress,
    process_image,
)
from index_manager import (
    add_entry,
    extend_page_range,
    find_entry_by_author_year,
    find_entry_by_notebook_page,
    find_entry_by_title_year,
    load_index,
)
from bib_manager import process_bib_result
from ocr import ocr_image
from output_writer import OBSIDIAN_NOTES_DIR, append_continuation, write_source, write_unmatched
from watcher import ArrivalSignal, find_unprocessed, is_stable, start_watcher

NOTEBOOKS_DIR = Path("notebooks")
LOG_FILE = "ocr_pipeline.log"
QUIET_PERIOD = 60  # seconds with no new image arriving before processing starts
SCAN_INTERVAL = 300  # seconds between safety-net scans when idle


def setup_logging():
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)


logger = logging.getLogger(__name__)


def resolve_continuation(source: dict, notebook: str, index: list) -> dict | None:
    """Find the index entry that a continuation page belongs to."""
    cont_notebook = source.get("continuation_notebook") or notebook
    cont_page = source.get("continuation_page")

    if cont_page:
        entry = find_entry_by_notebook_page(index, cont_notebook, str(cont_page))
        if entry:
            return entry

    # Fallback: match by author surname + year from the continuation source
    author = source.get("author") or ""
    year = source.get("year") or ""
    if author or year:
        entry = find_entry_by_author_year(index, author, year)
        if entry:
            return entry

    return None


def process_file(image_path: Path, processed_files: set):
    notebook = image_path.parent.name
    today = date.today().isoformat()
    original_path = image_path

    logger.info(f"Processing: {image_path.name} (notebook: {notebook})")

    # Convert HEIC → JPG (the original is only deleted once the page is fully processed)
    image_path = process_image(image_path)

    # OCR via Gemini (retry logic is inside ocr_image)
    index = load_index()
    result = ocr_image(image_path, notebook, index)

    for source in result.get("sources", []):
        if source.get("is_continuation"):
            entry = resolve_continuation(source, notebook, index)
            if entry:
                md_path = OBSIDIAN_NOTES_DIR / entry["md_file"]
                if md_path.exists():
                    append_continuation(source, md_path)
                    if source.get("page"):
                        index = extend_page_range(index, entry, str(source["page"]))
                else:
                    write_unmatched(
                        source, notebook, image_path.name,
                        f"index points to {md_path.name}, which is not on disk",
                    )
            else:
                write_unmatched(
                    source, notebook, image_path.name, "no matching source in index.json"
                )
        else:
            # Source already has a note (page re-processed, missed continuation, or a book
            # carried on into a new notebook): add to that note, whatever its filename
            existing = find_entry_by_title_year(
                index, source.get("title"), source.get("year"), notebook
            )
            existing_md = OBSIDIAN_NOTES_DIR / existing["md_file"] if existing else None
            if existing_md and existing_md.exists():
                logger.info(f"Source already has a note, adding to it: {existing_md.name}")
                append_continuation(source, existing_md)
                if existing["notebook"] == notebook:
                    if source.get("page"):
                        index = extend_page_range(index, existing, str(source["page"]))
                else:
                    index = add_entry(index, source, notebook, existing_md.name)
            else:
                md_path = write_source(source, notebook, today)
                index = add_entry(index, source, notebook, md_path.name)
            process_bib_result(source, notebook)

    # Mark the original too, so a HEIC whose deletion fails is not processed twice
    mark_processed([original_path, image_path], processed_files)
    delete_original_heic(original_path)
    maybe_compress(image_path.parent, processed_files)
    logger.info(f"Done: {image_path.name}")


def next_page(processed_files: set) -> Path | None:
    """The earliest (by filename) unprocessed image that is ready to process, or None."""
    pending = find_unprocessed(NOTEBOOKS_DIR, processed_files)
    for path in pending:
        if has_heic_original(path):
            continue  # our own conversion of a HEIC; the HEIC itself is processed instead
        if not is_stable(path):
            logger.info(f"{path.name} is still being written — will try again shortly.")
            continue
        if len(pending) > 1:
            logger.info(f"{len(pending)} image(s) waiting to be processed.")
        return path
    return None


def fail(context: str, exc: Exception):
    """Log, send the alert email and terminate. Used for every error that reaches the top."""
    logger.critical(f"Unrecoverable error while {context} — terminating.", exc_info=exc)
    send_failure_alert(context, exc)
    sys.exit(1)


def run_worker(arrivals: ArrivalSignal, processed_files: set):
    """Process unprocessed images one at a time, earliest filename first.

    Waits until no new image has arrived for QUIET_PERIOD seconds before processing,
    so that when Drive delivers a backlog (e.g. pages added while the computer was off)
    in random order, all of it is present and pages are still processed in order.
    The folders are rescanned before every page, and at least every SCAN_INTERVAL
    when idle, so nothing depends on the watcher having seen a file arrive."""
    while True:
        quiet_for = arrivals.seconds_since_arrival()
        if quiet_for < QUIET_PERIOD:
            arrivals.wait(QUIET_PERIOD - quiet_for)
            continue

        path = next_page(processed_files)
        if path is None:
            arrivals.wait(SCAN_INTERVAL)
            continue

        try:
            process_file(path, processed_files)
        except Exception as e:
            fail(f"processing {path}", e)


def main():
    setup_logging()
    logger.info("=== Notebook OCR pipeline starting ===")

    def handle_sigterm(sig, frame):
        logger.info("SIGTERM received — shutting down gracefully.")
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    observer = None
    try:
        # Ensure output directories/files exist
        OBSIDIAN_NOTES_DIR.mkdir(exist_ok=True)
        if not Path("index.json").exists():
            Path("index.json").write_text("[]", encoding="utf-8")
        if not Path("library.bib").exists():
            Path("library.bib").touch()
        if not Path("incomplete_bib.txt").exists():
            Path("incomplete_bib.txt").touch()

        processed_files = load_processed_files()

        # The watcher thread only signals arrivals; all processing happens in this (main) thread
        arrivals = ArrivalSignal()
        observer = start_watcher(NOTEBOOKS_DIR, arrivals)

        run_worker(arrivals, processed_files)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down.")
    except Exception as e:
        fail("starting up or scanning the notebook folders", e)
    finally:
        if observer is not None:
            observer.stop()
            observer.join()
        logger.info("Pipeline stopped.")


if __name__ == "__main__":
    main()
