"""
One-page test of the full pipeline, run in a temporary copy of the project.
Your real notes, index.json, library.bib and processed_files.json are never touched,
and the background pipeline is not affected.

Run from the project folder:
    python test_run.py                                  # uses a default image
    python test_run.py notebooks/red_1/IMG_2785.jpg     # any image (.jpg, .png or .heic)

Uses one Gemini request (more if Gemini returns an error and the call is retried).
The temporary folder is left in place so you can inspect the output.
"""
import io
import json
import logging
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Ensure stdout handles Unicode on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT = Path(__file__).resolve().parent
DEFAULT_IMAGE = PROJECT / "notebooks" / "blue_1" / "IMG_2658.jpg"
# State the pipeline reads, copied so the test sees the same index, bibliography and cooldowns
STATE_FILES = [
    "gemini_instructions.txt",
    "model_config.json",
    "index.json",
    "library.bib",
    "incomplete_bib.txt",
    "rate_usage.json",
]


def make_test_copy(image: Path) -> Path:
    """Copy the pipeline's state, notes and the test image into a new temporary folder."""
    work = Path(tempfile.mkdtemp(prefix="notebook_ocr_test_"))
    for name in STATE_FILES:
        if (PROJECT / name).exists():
            shutil.copy2(PROJECT / name, work / name)
    shutil.copytree(PROJECT / "obsidian_notes", work / "obsidian_notes")
    notebook_dir = work / "notebooks" / image.parent.name
    notebook_dir.mkdir(parents=True)
    shutil.copy2(image, notebook_dir / image.name)
    return work


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else ""


def snapshot(work: Path) -> dict:
    """Contents of every output file, to compare before and after the run."""
    files = {name: read(work / name) for name in ("library.bib", "incomplete_bib.txt")}
    for note in (work / "obsidian_notes").glob("*.md"):
        files[f"obsidian_notes/{note.name}"] = read(note)
    files["index"] = json.loads(read(work / "index.json") or "[]")
    return files


def report(before: dict, after: dict):
    """Print only what the test run added or changed."""
    print("\n================ RESULTS ================")

    for name in sorted(k for k in after if k.startswith("obsidian_notes/")):
        old, new = before.get(name), after[name]
        if old is None:
            print(f"\n--- New note: {name} ---\n{new}")
        elif new != old:
            print(f"\n--- Added to existing note: {name} ---\n{new[len(old):].lstrip()}")

    new_entries = [e for e in after["index"] if e not in before["index"]]
    print("\n--- index.json: new or changed entries ---")
    print(json.dumps(new_entries, indent=2, ensure_ascii=False) if new_entries else "(none)")

    for name in ("library.bib", "incomplete_bib.txt"):
        added = after[name][len(before[name]):].strip()
        print(f"\n--- {name}: added ---\n{added or '(nothing)'}")


def main():
    image = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_IMAGE
    if not image.exists():
        print(f"ERROR: Test image not found: {image}")
        sys.exit(1)

    work = make_test_copy(image)
    os.chdir(work)  # every pipeline path is relative, so from here on only the copy is used

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    # Imported after chdir; main.py still loads the API key from the project's .env
    from main import process_file

    print(f"\n--- Testing {image.name} (notebook: {image.parent.name}) in {work} ---\n")
    before = snapshot(work)
    try:
        process_file(Path("notebooks") / image.parent.name / image.name, set())
    except Exception as e:
        # No alert email is sent from a test run
        print(f"\nERROR during processing: {e}")
        print(f"Test folder: {work}")
        sys.exit(1)

    report(before, snapshot(work))
    print(f"\nTest folder (delete when done): {work}")


if __name__ == "__main__":
    main()
