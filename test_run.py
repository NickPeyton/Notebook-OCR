"""
One-shot test: copies test_page.heic and runs it through the full pipeline.
Run from the project root: python test_run.py
"""
import io
import json
import shutil
import sys
import logging
from pathlib import Path

# Ensure stdout handles Unicode on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from dotenv import load_dotenv
load_dotenv()

# Basic logging to stdout for the test run
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from main import process_file

TEST_ORIGINAL = Path("notebooks/blue_1/test_page.heic")
TEST_COPY = Path("notebooks/blue_1/test_page_run.heic")


def main():
    if not TEST_ORIGINAL.exists():
        print(f"ERROR: Test image not found at {TEST_ORIGINAL}")
        sys.exit(1)

    # Copy so the original is preserved
    shutil.copy2(TEST_ORIGINAL, TEST_COPY)
    print(f"\n--- Copied test image to {TEST_COPY} ---\n")

    processed_files = set()

    try:
        process_file(TEST_COPY, processed_files)
    except Exception as e:
        print(f"\nERROR during processing: {e}")
        sys.exit(1)

    print("\n--- Pipeline complete. Results: ---\n")

    notes = list(Path("obsidian_notes").glob("*.md"))
    print(f"Markdown notes written ({len(notes)}):")
    for f in notes:
        print(f"  {f.name}")

    index = json.loads(Path("index.json").read_text(encoding="utf-8"))
    print(f"\nIndex entries ({len(index)}):")
    for entry in index:
        print(f"  {entry}")

    # Show only the last 40 lines of library.bib (new entries are appended)
    bib_lines = Path("library.bib").read_text(encoding="utf-8").splitlines()
    bib_tail = "\n".join(bib_lines[-40:]) if bib_lines else "(empty)"
    print(f"\nlibrary.bib (last 40 lines):\n{bib_tail}")

    incomplete_path = Path("incomplete_bib.txt")
    if incomplete_path.exists():
        incomplete = incomplete_path.read_text(encoding="utf-8").strip()
        if incomplete:
            print(f"\nincomplete_bib.txt:\n{incomplete}")

    print("\n--- Test finished ---")


if __name__ == "__main__":
    main()
