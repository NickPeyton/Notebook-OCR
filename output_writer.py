import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

OBSIDIAN_NOTES_DIR = Path("obsidian_notes")
UNMATCHED_NOTES = OBSIDIAN_NOTES_DIR / "_unmatched_continuations.md"


def sanitise_filename(name: str) -> str:
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name[:80]


def _str(value) -> str:
    """Convert a value to string, treating None as empty string."""
    return "" if value is None else str(value)


def extract_surname(full_name: str) -> str:
    """Take the last whitespace-delimited token as the surname."""
    return full_name.strip().split()[-1] if full_name.strip() else "Unknown"


def build_md_filename(source: dict) -> str:
    full_author = _str(source.get("author")) or "Unknown"
    surname = sanitise_filename(extract_surname(full_author))
    year = _str(source.get("year"))
    title = sanitise_filename(_str(source.get("title")) or "Untitled")
    return f"{surname}_{year}_{title}.md"


def yaml_quote(value: str) -> str:
    """Wrap a YAML string value in double quotes, escaping any internal double quotes."""
    value = str(value).replace('"', '\\"')
    return f'"{value}"'


def build_frontmatter(source: dict, notebook: str, today: str) -> str:
    return (
        f"---\n"
        f"title: {yaml_quote(_str(source.get('title')) or 'Untitled')}\n"
        f"author: {yaml_quote(_str(source.get('author')) or 'Unknown')}\n"
        f"year: {yaml_quote(_str(source.get('year')))}\n"
        f"notebook: {yaml_quote(notebook)}\n"
        f"page: {yaml_quote(_str(source.get('page')))}\n"
        f"date: {yaml_quote(today)}\n"
        f"---\n\n"
    )


def write_source(source: dict, notebook: str, today: str) -> Path:
    filename = build_md_filename(source)
    filepath = OBSIDIAN_NOTES_DIR / filename
    if filepath.exists():
        # Same author/year/title as an existing note (e.g. a missed continuation, or a
        # book carried on into a new notebook): add to it rather than overwrite it.
        logger.warning(f"{filename} already exists — appending instead of overwriting.")
        append_continuation(source, filepath)
        return filepath
    frontmatter = build_frontmatter(source, notebook, today)
    content = frontmatter + (source.get("body") or "")
    filepath.write_text(content, encoding="utf-8")
    logger.info(f"Written: {filepath.name}")
    return filepath


def append_continuation(source: dict, existing_md: Path):
    body = source.get("body") or ""
    with open(existing_md, "a", encoding="utf-8") as f:
        f.write(f"\n\n{body}")
    logger.info(f"Appended continuation to: {existing_md.name}")


def write_unmatched(source: dict, notebook: str, image_name: str, reason: str):
    """Save a continuation page that could not be matched to a note, so its text is not lost.
    Move the text into the right note by hand, then delete it from this file."""
    header = (
        f"## {image_name} (notebook {notebook}, page {_str(source.get('page')) or '?'})\n\n"
        f"Not matched: {reason}. Gemini's guess: "
        f"author {_str(source.get('author')) or '?'}, year {_str(source.get('year')) or '?'}, "
        f"continues notebook {_str(source.get('continuation_notebook')) or notebook} "
        f"page {_str(source.get('continuation_page')) or '?'}.\n\n"
    )
    with open(UNMATCHED_NOTES, "a", encoding="utf-8") as f:
        f.write(header + (source.get("body") or "") + "\n\n")
    logger.warning(f"Unmatched continuation from {image_name} saved to {UNMATCHED_NOTES.name}")
