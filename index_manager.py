import json
import logging
from datetime import date
from pathlib import Path

logger = logging.getLogger(__name__)

INDEX_PATH = Path("index.json")


def load_index() -> list:
    if INDEX_PATH.exists() and INDEX_PATH.stat().st_size > 0:
        return json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    return []


def save_index(index: list):
    data = json.dumps(index, indent=2, ensure_ascii=False)
    tmp = INDEX_PATH.with_suffix(".tmp")
    tmp.write_text(data, encoding="utf-8")
    tmp.replace(INDEX_PATH)


def entry_exists(index: list, source: dict, notebook: str) -> bool:
    for entry in index:
        if (
            entry.get("author") == source.get("author")
            and entry.get("title") == source.get("title")
            and entry.get("notebook") == notebook
        ):
            return True
    return False


def add_entry(index: list, source: dict, notebook: str, md_filename: str) -> list:
    if entry_exists(index, source, notebook):
        logger.info(f"Skipping duplicate index entry: {source.get('title')}")
        return index
    entry = {
        "title": source.get("title", "Untitled"),
        "author": source.get("author", "Unknown"),
        "year": source.get("year", ""),
        "notebook": notebook,
        "page": source.get("page", ""),
        "date": date.today().isoformat(),
        "md_file": md_filename,
    }
    index.append(entry)
    save_index(index)
    logger.info(f"Index updated: {entry['title']}")
    return index


def extend_page_range(index: list, entry: dict, new_page: str) -> list:
    """Extend the page range of an existing entry to include new_page.
    E.g. page "10" becomes "10-11"; page "10-11" becomes "10-12"."""
    try:
        new = int(new_page)
    except (ValueError, TypeError):
        return index

    current = str(entry.get("page", ""))
    try:
        if "-" in current:
            start, end = (int(p) for p in current.split("-", 1))
        else:
            start = end = int(current)
    except (ValueError, TypeError):
        return index

    if new <= end:
        return index  # already covered

    entry["page"] = f"{start}-{new}"
    save_index(index)
    logger.info(f"Page range updated to {entry['page']} for: {entry.get('title')}")
    return index


def find_entry_by_notebook_page(index: list, notebook: str, page: str) -> dict | None:
    """Find a source entry by notebook name and page number."""
    for entry in index:
        if entry.get("notebook") == notebook and str(entry.get("page")) == str(page):
            return entry
    return None


def find_entry_by_author_year(index: list, author: str, year: str) -> dict | None:
    """Find a source entry by author surname and year (for continuation fallback)."""
    surname = author.strip().split()[-1].lower() if author else ""
    for entry in index:
        entry_author = entry.get("author", "").strip().split()[-1].lower()
        if entry_author == surname and str(entry.get("year")) == str(year):
            return entry
    return None
