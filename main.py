import logging
import os
import signal
import sys
import time
from datetime import date
from logging.handlers import RotatingFileHandler
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from image_handler import load_processed_files, mark_processed, maybe_compress, process_image
from index_manager import (
    add_entry,
    extend_page_range,
    find_entry_by_author_year,
    find_entry_by_notebook_page,
    load_index,
)
from ocr import ocr_image
from output_writer import OBSIDIAN_NOTES_DIR, append_continuation, write_source
from watcher import start_watcher

NOTEBOOKS_DIR = Path("notebooks")
LOG_FILE = "ocr_pipeline.log"


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

    logger.info(f"Processing: {image_path.name} (notebook: {notebook})")

    # Convert HEIC → JPG, delete original
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
                    logger.warning(
                        f"Continuation target .md not found on disk: {md_path.name}"
                    )
            else:
                logger.warning(
                    f"Could not resolve continuation source for page "
                    f"{source.get('continuation_page')} in {source.get('continuation_notebook', notebook)}"
                )
        else:
            md_path = write_source(source, notebook, today)
            index = add_entry(index, source, notebook, md_path.name)

    maybe_compress(image_path.parent)
    mark_processed(str(image_path), processed_files)
    logger.info(f"Done: {image_path.name}")


def main():
    setup_logging()
    logger.info("=== Notebook OCR pipeline starting ===")

    # Ensure output directories/files exist
    OBSIDIAN_NOTES_DIR.mkdir(exist_ok=True)
    if not Path("index.json").exists():
        Path("index.json").write_text("[]", encoding="utf-8")
    if not Path("library.bib").exists():
        Path("library.bib").touch()
    if not Path("incomplete_bib.txt").exists():
        Path("incomplete_bib.txt").touch()

    processed_files = load_processed_files()

    def safe_process(path: Path):
        """Wrap process_file so that a fatal (post-retry) exception kills the process
        rather than being silently swallowed by the watchdog event thread."""
        try:
            process_file(path, processed_files)
        except Exception:
            logger.critical(
                "Unrecoverable error — alert email sent. Terminating process.",
                exc_info=True,
            )
            # Send SIGTERM to ourselves so the SIGTERM handler runs cleanly.
            os.kill(os.getpid(), signal.SIGTERM)

    observer = start_watcher(
        NOTEBOOKS_DIR,
        safe_process,
        processed_files,
    )

    def handle_sigterm(sig, frame):
        logger.info("SIGTERM received — shutting down gracefully.")
        observer.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, handle_sigterm)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down.")
        observer.stop()

    observer.join()
    logger.info("Pipeline stopped.")


if __name__ == "__main__":
    main()
