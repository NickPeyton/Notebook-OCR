# Notebook OCR Project

## Overview
This project automatically OCRs handwritten notebook pages as images arrive in watched folders synced from Google Drive. It runs continuously as a Python process on a Raspberry Pi.

## Goals
1. Watch all notebook subfolders under `notebooks/` for new images
2. Send each new image to the Gemini API for OCR and structured extraction
3. Stitch multi-page sources together using the global index, page numbers, and notebook folder name
4. Output one `.md` file per source to `obsidian_notes/`
5. Update `index.json` with metadata for every source
6. Look up bibliographic data and append to `library.bib`

## Tech Stack
- **Language**: Python
- **OCR/extraction**: Gemini API (key in `gemini_api_key.txt`, also available as `GEMINI_API_KEY` env var)
- **Email alerts**: Gmail SMTP using a Gmail App Password (requires 2FA on the sending account)
- **Bib lookup**: CrossRef first, Semantic Scholar as fallback
- **Runtime**: Raspberry Pi, running continuously
- **File sync**: Google Drive → local folders (script must only process newly-arrived files, not re-process existing ones)

## Folder Structure
```
notebooks/
  blue_1/       # one subfolder per physical notebook
  blue_2/
  ...
obsidian_notes/ # all output .md files go here
index.json      # one global index across all notebooks
library.bib     # cumulative BibTeX bibliography
incomplete_bib.txt  # sources whose bib data could not be found
```

## Processing Pipeline

### Image Handling
- Watch all subfolders of `notebooks/` for new image files
- Input images are typically `.heic` format; convert to a standard format (e.g., JPEG) before sending to Gemini
- After **successful** processing: keep the converted image, **delete** the original `.heic`
- Compress (zip) converted images per notebook every 100 pages (counted per notebook folder)
- Only process **new** arrivals — use a file watcher (e.g., `watchdog`) and track processed files to avoid reprocessing on restart

### OCR & Extraction (Gemini API)
- Use the prompt in `gemini_instructions.txt` verbatim as the system/user instruction
- Extract per source: `title`, `author`, `year`, `notebook` (e.g., `blue_1`), `page`
- Output one `.md` file per source named `author_year_title.md` in `obsidian_notes/`
- Each `.md` file has a YAML front matter block followed by Markdown body

### Continuation Pages
- If a new page begins without a title, it continues a previous source
- Use the notebook folder name + page number extracted from the image + `index.json` to identify which source it continues
- Append the continuation text to the correct existing `.md` file in `obsidian_notes/`

### Index (`index.json`)
- One global index across all notebooks
- Each entry includes: `title`, `author`, `year`, `notebook`, `page`, `date`, `md_file`
- Update after every successfully processed page

### Bibliography (`library.bib`)
- Run bib lookup immediately as part of the pipeline after OCR
- Try **CrossRef** first, then **Semantic Scholar** as fallback
- On success: append a proper BibTeX entry to `library.bib`
- On failure: write a stub BibTeX entry to `library.bib` and log the source details (title, author, year, notebook, page) to `incomplete_bib.txt` for later manual/automated resolution

## Error Handling
- On any failure (API error, bad image, etc.): retry **5 times** with exponential backoff (double the wait between each attempt)
- If all 5 retries fail: log the error, send an alert email to `nicholas.and.dixie@gmail.com` via Gmail SMTP, and **terminate the process**
- Alert email should include: which file failed, the error message, and the full traceback
- Use Python's `logging` module; write logs to a rotating log file

## Code Conventions
- Keep the pipeline modular: separate functions/modules for watching, OCR, stitching, indexing, bib lookup, and compression
- All secrets (API keys, email credentials) loaded from environment variables or local config files — never hardcoded
- The script should handle SIGTERM gracefully (flush state before exit)
