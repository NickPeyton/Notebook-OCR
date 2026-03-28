import json
import logging
import zipfile
from pathlib import Path

import pillow_heif
from PIL import Image

logger = logging.getLogger(__name__)

PROCESSED_FILES_PATH = Path("processed_files.json")
IMAGE_EXTENSIONS = {".heic", ".jpg", ".jpeg", ".png"}


def load_processed_files() -> set:
    if PROCESSED_FILES_PATH.exists():
        return set(json.loads(PROCESSED_FILES_PATH.read_text(encoding="utf-8")))
    return set()


def save_processed_files(processed: set):
    PROCESSED_FILES_PATH.write_text(
        json.dumps(sorted(processed), indent=2), encoding="utf-8"
    )


def mark_processed(file_path: str, processed: set):
    processed.add(file_path)
    save_processed_files(processed)


def convert_heic_to_jpg(heic_path: Path) -> Path:
    jpg_path = heic_path.with_suffix(".jpg")
    pillow_heif.register_heif_opener()
    image = Image.open(heic_path)
    image = image.convert("RGB")
    image.save(jpg_path, "JPEG", quality=95)
    logger.info(f"Converted {heic_path.name} to {jpg_path.name}")
    return jpg_path


def process_image(file_path: Path) -> Path:
    """Convert HEIC to JPG if needed. Delete original HEIC on success."""
    if file_path.suffix.lower() == ".heic":
        jpg_path = convert_heic_to_jpg(file_path)
        file_path.unlink()
        logger.info(f"Deleted original HEIC: {file_path.name}")
        return jpg_path
    return file_path


def maybe_compress(notebook_dir: Path):
    """Zip all JPGs in the notebook dir when count is a multiple of 100.
    Batch number is derived from existing zip count so there are no collisions
    after previous batches have been zipped and their JPGs deleted."""
    jpgs = sorted(
        list(notebook_dir.glob("*.jpg")) + list(notebook_dir.glob("*.jpeg"))
    )
    count = len(jpgs)
    if count > 0 and count % 100 == 0:
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
