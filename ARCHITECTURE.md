# Notebook OCR Project

## Overview
This project automatically OCRs handwritten notebook pages as images arrive in watched folders synced from Google Drive. It runs continuously as a background process (Windows scheduled task or Linux systemd service).

## Goals
1. Watch all notebook subfolders under `notebooks/` for new images (including folders created after startup)
2. Send each new image to the Gemini API for OCR, structured extraction, and bibliography lookup — all in a single API call per page
3. Stitch multi-page sources together using the global index, page numbers, and notebook folder name
4. Output one `.md` file per source to `obsidian_notes/`
5. Update `index.json` with metadata for every source
6. Append new BibTeX entries to `library.bib`; log unresolvable sources to `incomplete_bib.txt`

## Tech Stack
- **Language**: Python
- **OCR/extraction/bib**: Gemini API (`GEMINI_API_KEY` env var) — one call per page handles OCR, metadata extraction, and bibliography lookup
- **Rate limiting**: driven by Gemini's own 429 responses (no limits configured locally); model cascade order defined in `model_config.json`, cooldowns stored in `rate_usage.json`
- **Email alerts**: Gmail SMTP using a Gmail App Password (requires 2FA on the sending account)
- **Runtime**: Windows (scheduled task) or Raspberry Pi (systemd service), running continuously
- **File sync**: Google Drive → local folders (script must only process newly-arrived files, not re-process existing ones)

## Folder Structure
```
notebooks/
  blue_1/              # one subfolder per physical notebook
  blue_2/
  ...
obsidian_notes/        # all output .md files go here
  _unmatched_continuations.md  # continuation pages that could not be matched to a note
index.json             # one global index across all notebooks
library.bib            # cumulative BibTeX bibliography
incomplete_bib.txt     # sources whose bib data could not be found
model_config.json      # Gemini model names in priority order
rate_usage.json        # auto-generated — per-model cooldowns after 429s
processed_files.json   # auto-generated — tracks processed images
ocr_pipeline.log       # auto-generated — rotating log file
```

## Processing Pipeline

### Image Handling
- Watch `notebooks/` recursively for new image files (created or renamed into place) — new subfolders are detected automatically
- The watcher thread only records that an image arrived (ignoring the pipeline's own HEIC→JPG conversions); the main thread does all processing, one page at a time
- **Backlogs** (e.g. pages added while the computer was off): processing starts only once no new image has arrived for 60 seconds (startup counts as an arrival). Drive delivers a backlog in random order, so this lets the whole batch land first
- Before each page, the folders are rescanned and the **earliest unprocessed image by filename** is processed next, so pages are always handled in the order they were photographed. Continuations therefore always come after the page they continue
- When idle, the folders are rescanned at least every 5 minutes. Nothing depends on the watcher having seen a file arrive: pages that arrived while the pipeline was off, or were still downloading when first seen (skipped until stable), are picked up by the scan
- `processed_files.json` keys use forward slashes (`notebooks/blue_1/IMG_1.jpg`) so they match on Windows and Linux
- Input images may be `.heic` (converted to JPEG before sending to Gemini) or `.jpg`/`.png`
- After **successful** processing: keep the converted image, **delete** the original `.heic`. Both paths are marked processed first, so a failed deletion cannot cause reprocessing. A JPEG sitting next to a HEIC of the same name is treated as an unfinished conversion and skipped
- Compress (zip) a notebook's **processed** images once there are 100 of them; images still waiting to be processed are never zipped

### OCR & Extraction (Gemini API)
- Use the prompt in `gemini_instructions.txt` as the base instruction (describes how to read the notebook pages)
- `ocr.py` appends the notebook name, current index, current `library.bib`, and a JSON output schema to the prompt
- One API call per page returns: source metadata, transcribed body, and bibliography status/entries
- Extract per source: `title`, `author`, `year`, `notebook` (e.g., `blue_1`), `page`
- Output one `.md` file per source named `author_year_title.md` in `obsidian_notes/`
- Each `.md` file has a YAML front matter block followed by Markdown body
- A new (non-continuation) source that is already in `index.json` (same title, ignoring case and punctuation, and same year) is appended to that entry's `.md` file, whatever filename would have been generated. This covers re-processed pages, missed continuations, and books continued in a new notebook (which also get their own index entry for the new notebook, pointing to the same note). Same notebook: the entry's page range is extended
- Existing notes are never overwritten: if the generated filename already exists, the new text is appended
- `null` values returned by Gemini are replaced with defaults (`Untitled`, `Unknown`, empty string) before they reach the index or notes

### Rate Limiting & Model Cascade
- Google publishes free-tier limits only in AI Studio (no API) and changes them without notice, so no limits are configured locally. Gemini's 429 responses are the source of truth; rejected requests do not use quota
- `model_config.json` is a JSON list of model names in priority order
- On a 429, `rate_limiter.py` reads the error details (`QuotaFailure` violations and `RetryInfo`):
  - per-day quota (`quotaId` contains `PerDay`): model skipped until 00:05 **Pacific** time (Gemini daily quotas reset at midnight Pacific; the 5 minutes allow for a late reset)
  - anything else (per-minute requests or tokens): model skipped for the suggested `retryDelay`, or 60s if none is given
  - the quota hit and its value (e.g. `GenerateRequestsPerDayPerProjectPerModel-FreeTier=20`) are logged and saved in `rate_usage.json`
- A 429 moves straight to the next model and does **not** use up one of the 5 retries
- `select_model()` picks the highest-priority model not on cooldown. If all are cooling down, it waits for the earliest one — until the next daily reset if every model has hit its daily limit, so a large backlog is simply spread over several days. It sleeps in steps of at most 60s and re-checks the clock, so the wait stays correct across laptop sleep
- To change models (e.g. when a preview model is retired), edit the list in `model_config.json`

### Continuation Pages
- If a new page begins without a title, it continues a previous source
- Use the notebook folder name + page number extracted from the image + `index.json` to identify which source it continues
- Page range matching: a query for page 12 will match an index entry with page "10-14"
- Append the continuation text to the correct existing `.md` file in `obsidian_notes/`
- If no match is found (or the matched `.md` is missing), the text is appended to `obsidian_notes/_unmatched_continuations.md` with the image name, notebook, page and Gemini's guess, for manual filing. It is never discarded

### Index (`index.json`)
- One global index across all notebooks
- Each entry includes: `title`, `author`, `year`, `notebook`, `page`, `date`, `md_file`
- Update after every successfully processed page

### Bibliography (`library.bib`)
- Gemini checks `library.bib` (included in the prompt) for each source during OCR
- If the source is already present (matched on author surname(s) + year): no action
- If Gemini can confidently identify the full publication: it returns a BibTeX entry, which is appended to `library.bib`
- If Gemini cannot identify the source: the source details are logged to `incomplete_bib.txt` for manual resolution
- `bib_manager.py` double-checks Gemini's "new" and "not_found" verdicts locally (no API call): if `library.bib` already has an entry with the same **main title** (text before any colon, ignoring case and punctuation), nothing is added or logged. This catches other editions and reprints filed under a different year/key (e.g. `Polanyi1957` for the 1944 book)
- If a genuinely new entry's citation key is already used by a different work, it is added with a suffix (`Smith2009b`, `c`, ...) so `library.bib` never has duplicate keys

## Error Handling
- Repeatable steps — the Gemini call and HEIC conversion — retry **5 times** with exponential backoff (5s, doubling between attempts)
- No network connection at all (`httpx.ConnectError`, e.g. Wi-Fi not up yet after login) is not counted as a failure: the Gemini call waits 60s and tries again, indefinitely, without using up a retry. A request that never connected uses no quota
- Steps that write notes, the index or the bibliography are not retried, since repeating them could duplicate text
- Any error that is not resolved (retries exhausted, or any other failure during processing, startup or a folder scan): log it, send an alert email via Gmail SMTP, and **terminate the process** with exit code 1
- Alert email includes: which file failed (or what the pipeline was doing), the error message, and the full traceback. A failure to send the email is logged and does not hide the original error
- The systemd service uses `Restart=on-abnormal`, so it restarts after a crash but not after this deliberate stop (which would otherwise retry the same failing page indefinitely)
- Use Python's `logging` module; write logs to a rotating log file
