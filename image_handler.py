import json
import logging
import zipfile
from pathlib import Path

import pillow_heif
from PIL import Image

from error_handler import with_retry

logger = logging.getLogger(__name__)

PROCESSED_FILES_PATH = Path("processed_files.json")
IMAGE_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png"}
PAGES_PER_ZIP = 100


def file_key(path: Path) -> str:
    """Key used in processed_files.json. Forward slashes so keys match on Windows and Linux."""
    return Path(path).as_posix()


def load_processed_files() -> set:
    if PROCESSED_FILES_PATH.exists():
        paths = json.loads(PROCESSED_FILES_PATH.read_text(encoding="utf-8"))
        # Older entries were saved with Windows backslashes
        return {p.replace("\\", "/") for p in paths}
    return set()


def save_processed_files(processed: set):
    data = json.dumps(sorted(processed), indent=2)
    tmp = PROCESSED_FILES_PATH.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(PROCESSED_FILES_PATH)


def mark_processed(paths: list[Path], processed: set):
    for path in paths:
        processed.add(file_key(path))
    save_processed_files(processed)


def has_heic_original(path: Path) -> bool:
    """True if this JPG sits next to a HEIC of the same name, i.e. it is our own
    conversion of a HEIC that has not finished processing yet."""
    if path.suffix.lower() not in {".jpg", ".jpeg"}:
        return False
    return path.with_suffix(".heic").exists() or path.with_suffix(".HEIC").exists()


@with_retry
def convert_heic_to_jpg(heic_path: Path) -> Path:
    jpg_path = heic_path.with_suffix(".jpg")
    pillow_heif.register_heif_opener()
    image = Image.open(heic_path)
    image = image.convert("RGB")
    image.save(jpg_path, "JPEG", quality=95)
    logger.info(f"Converted {heic_path.name} to {jpg_path.name}")
    return jpg_path


def process_image(file_path: Path) -> Path:
    """Convert HEIC to JPG if needed. The original HEIC is kept until the page has
    been fully processed (see delete_original_heic)."""
    if file_path.suffix.lower() == ".heic":
        return convert_heic_to_jpg(file_path)
    return file_path


def delete_original_heic(file_path: Path):
    """Delete the original HEIC once its page has been processed successfully."""
    if file_path.suffix.lower() == ".heic":
        file_path.unlink()
        logger.info(f"Deleted original HEIC: {file_path.name}")


def maybe_compress(notebook_dir: Path, processed: set):
    """Zip the notebook's processed JPGs once there are PAGES_PER_ZIP of them, then delete them.
    JPGs still waiting to be processed are left alone.
    Batch number is derived from existing zip count so there are no collisions
    after previous batches have been zipped and their JPGs deleted."""
    jpgs = sorted(
        path
        for path in list(notebook_dir.glob("*.jpg")) + list(notebook_dir.glob("*.jpeg"))
        if file_key(path) in processed
    )
    count = len(jpgs)
    if count >= PAGES_PER_ZIP:
        existing_zips = len(list(notebook_dir.glob("*.zip")))
        batch_num = existing_zips + 1
        zip_path = notebook_dir / f"{notebook_dir.name}_pages_{batch_num:03d}.zip"
        logger.info(f"Compressing {count} images into {zip_path.name}")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for jpg in jpgs:
                zf.write(jpg, jpg.name)
        for jpg in jpgs:
            jpg.unlink()
        logger.info("Compression complete, JPGs deleted.")
