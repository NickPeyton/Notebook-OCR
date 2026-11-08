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
    # `or` (not a .get default) so that null values from Gemini are replaced too
    entry = {
        "title": source.get("title") or "Untitled",
        "author": source.get("author") or "Unknown",
        "year": source.get("year") or "",
        "notebook": notebook,
        "page": source.get("page") or "",
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


def _page_in_range(entry_page: str, query_page: str) -> bool:
    """Check whether query_page falls within entry_page (which may be a range like '10-14')."""
    try:
        q = int(query_page)
    except (ValueError, TypeError):
        return str(entry_page) == str(query_page)

    entry_str = str(entry_page)
    try:
        if "-" in entry_str:
            start, end = (int(p) for p in entry_str.split("-", 1))
            return start <= q <= end
        else:
            return int(entry_str) == q
    except (ValueError, TypeError):
        return entry_str == query_page


def find_entry_by_notebook_page(index: list, notebook: str, page: str) -> dict | None:
    """Find a source entry by notebook name and page number.

    Handles page ranges: if entry has page '10-14', a query for '12' will match.
    """
    for entry in index:
        if entry.get("notebook") == notebook and _page_in_range(entry.get("page", ""), page):
            return entry
    return None


def _normalise(text) -> str:
    """Lowercase letters and digits only, so punctuation and capitalisation don't matter."""
    return "".join(ch for ch in str(text or "").lower() if ch.isalnum())


def find_entry_by_title_year(index: list, title, year, notebook: str) -> dict | None:
    """Existing entry for the same source (same title and year), preferring one in `notebook`.
    Used to add a re-read source to its existing note, whatever filename it was given."""
    wanted = _normalise(title)
    if not wanted or wanted == "untitled":
        return None
    matches = [
        entry for entry in index
        if _normalise(entry.get("title")) == wanted
        and str(entry.get("year") or "") == str(year or "")
    ]
    same_notebook = [entry for entry in matches if entry.get("notebook") == notebook]
    return (same_notebook or matches or [None])[0]


def _surname(author) -> str:
    """Last word of the author string, lowercased. Empty string if there is no author."""
    words = str(author or "").split()
    return words[-1].lower() if words else ""


def find_entry_by_author_year(index: list, author: str, year: str) -> dict | None:
    """Find a source entry by author surname and year (for continuation fallback)."""
    surname = _surname(author)
    if not surname:
        return None
    for entry in index:
        if _surname(entry.get("author")) == surname and str(entry.get("year")) == str(year):
            return entry
    return None
