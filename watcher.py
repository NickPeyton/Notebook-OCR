import logging
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png"}
STABILITY_WAIT = 3.0  # seconds


def is_stable(path: Path, wait: float = STABILITY_WAIT) -> bool:
    """Return True if the file size is unchanged after `wait` seconds (i.e. write is complete)."""
    try:
        size_before = path.stat().st_size
        time.sleep(wait)
        size_after = path.stat().st_size
        return size_before == size_after and size_after > 0
    except FileNotFoundError:
        return False


class NotebookEventHandler(FileSystemEventHandler):
    def __init__(self, process_callback, processed_files: set):
        self.process_callback = process_callback
        self.processed_files = processed_files

    def on_created(self, event):
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            return
        if str(path) in self.processed_files:
            logger.debug(f"Already processed, skipping: {path.name}")
            return
        logger.info(f"New image detected: {path.name}")
        if not is_stable(path):
            logger.warning(f"File not stable after {STABILITY_WAIT}s, skipping: {path.name}")
            return
        self.process_callback(path)


def start_watcher(
    notebooks_dir: Path, process_callback, processed_files: set
) -> Observer:
    observer = Observer()
    handler = NotebookEventHandler(process_callback, processed_files)

    watched = 0
    for notebook_dir in sorted(notebooks_dir.iterdir()):
        if notebook_dir.is_dir():
            observer.schedule(handler, str(notebook_dir), recursive=False)
            logger.info(f"Watching: {notebook_dir}")
            watched += 1

    if watched == 0:
        logger.warning(f"No notebook subdirectories found under {notebooks_dir}")

    observer.start()
    return observer
