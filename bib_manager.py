import logging
import re
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

LIBRARY_BIB = Path("library.bib")
INCOMPLETE_BIB = Path("incomplete_bib.txt")


def _normalise(text) -> str:
    """Lowercase letters and digits only, so punctuation and capitalisation don't matter."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def _main_title(title) -> str:
    """The title without its subtitle (text after the first colon), normalised.
    library.bib often stores only the main title, e.g. 'The great transformation'."""
    return _normalise(str(title or "").split(":")[0])


def _parse_entries(bib_text: str) -> list[tuple[str, str]]:
    """(citation key, main title) for each entry in a BibTeX string."""
    entries = []
    for block in re.split(r"(?=^\s*@)", bib_text, flags=re.MULTILINE):
        key = re.match(r"\s*@\w+\s*\{\s*([^,\s]+)", block)
        title = re.search(r"^\s*title\s*=\s*(.+)$", block, flags=re.MULTILINE)
        if key:
            entries.append((key.group(1), _main_title(title.group(1)) if title else ""))
    return entries


def _find_in_library(titles: set[str], library: list[tuple[str, str]]) -> str | None:
    """Citation key of a library entry with one of these main titles, or None.
    Catches the same work under a different year/key (reprints, editions)."""
    titles.discard("")
    return next((key for key, title in library if title in titles), None)


def _unique_key(key: str, used: set[str]) -> str:
    """`key` if unused, else key + b, c, ... (a duplicate key would break BibTeX)."""
    if key not in used:
        return key
    return next(f"{key}{suffix}" for suffix in "bcdefghijklmnopqrstuvwxyz" if f"{key}{suffix}" not in used)


def process_bib_result(source: dict, notebook: str):
    """Handle the bib_status and bib_entry fields from the Gemini response.

    Gemini's verdict is double-checked against library.bib by title, since it
    matches on surname + year only and misses other editions of the same work.
    Call this for each new (non-continuation) source.
    """
    status = source.get("bib_status", "not_found")
    bib_entry = source.get("bib_entry")
    author = source.get("author") or "Unknown"
    year = source.get("year") or ""
    title = source.get("title") or "Untitled"

    if status == "existing":
        logger.info(f"Bib entry already exists: {author} ({year})")
        return

    library = _parse_entries(LIBRARY_BIB.read_text(encoding="utf-8") if LIBRARY_BIB.exists() else "")
    new_entries = _parse_entries(bib_entry or "")
    new_key, new_title = new_entries[0] if new_entries else (None, "")

    match = _find_in_library({_main_title(source.get("title")), new_title}, library)
    if match:
        logger.info(f"Bib entry already exists under a different key: {match} (same title as {title!r})")
        return

    if status == "new" and bib_entry and new_key:
        key = _unique_key(new_key, {k for k, _ in library})
        if key != new_key:
            bib_entry = bib_entry.replace(new_key, key, 1)
            logger.warning(f"Citation key {new_key} is already used by another work; added as {key}")
        with open(LIBRARY_BIB, "a", encoding="utf-8") as f:
            f.write(f"\n{bib_entry.strip()}\n")
        logger.info(f"Added bib entry: {author} ({year})")
        return

    # status == "not_found", or a missing/unreadable bib_entry
    line = (
        f"[{date.today().isoformat()}] "
        f"title={title!r}  author={author!r}  "
        f"year={year!r}  notebook={notebook}  "
        f"page={source.get('page')!r}\n"
    )
    with open(INCOMPLETE_BIB, "a", encoding="utf-8") as f:
        f.write(line)
    logger.info(f"Logged to incomplete_bib.txt: {title!r} ({author}, {year})")
