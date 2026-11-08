import logging
import threading
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from image_handler import IMAGE_EXTENSIONS, file_key, has_heic_original

logger = logging.getLogger(__name__)

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


def is_notebook_image(path: Path, notebooks_dir: Path) -> bool:
    """Images inside a notebook subfolder count; images in the notebooks/ root do not."""
    return path.suffix.lower() in IMAGE_EXTENSIONS and path.parent != notebooks_dir


def find_unprocessed(notebooks_dir: Path, processed_files: set) -> list[Path]:
    """All notebook images not yet in processed_files, in filename order
    (so pages are processed in the order they were photographed)."""
    return [
        path
        for path in sorted(notebooks_dir.rglob("*"))
        if path.is_file()
        and is_notebook_image(path, notebooks_dir)
        and file_key(path) not in processed_files
    ]


class ArrivalSignal:
    """Shared by the watcher thread and the main thread: records when an image last
    arrived, and wakes the main thread when one does."""

    def __init__(self):
        # Startup counts as an arrival, so Drive has time to start syncing after login
        self.last_arrival = time.monotonic()
        self._event = threading.Event()

    def notify(self):
        self.last_arrival = time.monotonic()
        self._event.set()

    def seconds_since_arrival(self) -> float:
        return time.monotonic() - self.last_arrival

    def wait(self, timeout: float):
        """Sleep until an image arrives or `timeout` seconds pass."""
        deadline = time.monotonic() + timeout
        # Short slices keep Ctrl+C responsive on Windows
        while not self._event.is_set() and time.monotonic() < deadline:
            self._event.wait(min(1.0, deadline - time.monotonic()))
        self._event.clear()


class NotebookEventHandler(FileSystemEventHandler):
    """Tells the main thread when a new image arrives. The main thread decides what to process."""

    def __init__(self, notebooks_dir: Path, arrivals: ArrivalSignal):
        self.notebooks_dir = notebooks_dir
        self.arrivals = arrivals

    def on_created(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_moved(self, event):
        # Some sync clients download to a temporary name, then rename the file
        if not event.is_directory:
            self._handle(Path(event.dest_path))

    def _handle(self, path: Path):
        if not is_notebook_image(path, self.notebooks_dir):
            return
        if has_heic_original(path):
            return  # our own HEIC→JPG conversion, not a new page
        logger.info(f"New image detected: {path.name}")
        self.arrivals.notify()


def start_watcher(notebooks_dir: Path, arrivals: ArrivalSignal) -> Observer:
    observer = Observer()
    handler = NotebookEventHandler(notebooks_dir, arrivals)
    observer.schedule(handler, str(notebooks_dir), recursive=True)
    logger.info(f"Watching: {notebooks_dir} (recursive, including new subfolders)")
    observer.start()
    return observer
