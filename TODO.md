# Notebook OCR — Build TODO

> Test asset: `notebooks/blue_1/test_page.heic`

---

## 1. Project Setup
- [ ] Create `requirements.txt` with all dependencies:
  - `watchdog` (file watching)
  - `pillow` + `pillow-heif` (HEIC conversion)
  - `google-generativeai` (Gemini API)
  - `requests` (CrossRef / Semantic Scholar lookups)
  - `python-dotenv` (load `.env`)
- [ ] Create `obsidian_notes/` folder
- [ ] Initialise `index.json` as an empty array `[]`
- [ ] Initialise `library.bib` and `incomplete_bib.txt` as empty files
- [ ] Confirm `.env` is populated on the Pi before running

---

## 2. Module: Image Handling (`image_handler.py`)
- [ ] On new file event, check extension — skip non-image files
- [ ] Convert `.heic` → `.jpg` using `pillow-heif`
- [ ] After successful processing: delete the original `.heic`
- [ ] Track page count per notebook folder; when count hits 100, zip all `.jpg` files in that folder into `[notebook]_pages_[batch].zip`
- [ ] Maintain a `processed_files.json` (list of already-processed file paths) so the watcher doesn't reprocess on Pi restart

---

## 3. Module: File Watcher (`watcher.py`)
- [ ] Use `watchdog` to monitor all immediate subfolders of `notebooks/`
- [ ] Trigger pipeline only for new files not already in `processed_files.json`
- [ ] Handle edge case: file still being written when event fires (brief delay + size-stability check before processing)
- [ ] Handle SIGTERM gracefully — flush state and exit cleanly

---

## 4. Module: Gemini OCR (`ocr.py`)
- [ ] Load API key from env (`GEMINI_API_KEY`)
- [ ] Load prompt from `gemini_instructions.txt`
- [ ] Send converted image + current `index.json` to Gemini API
- [ ] Parse Gemini response into structured objects:
  - List of sources found on the page, each with: `title`, `author`, `year`, `notebook`, `page`, `body`
  - Flag if page is a continuation (no title at top)
- [ ] Wrap all API calls in retry logic (see Module 7)

---

## 5. Module: Output Writer (`output_writer.py`)
- [ ] For each new source: write `author_year_title.md` to `obsidian_notes/` with YAML front matter + Markdown body
- [ ] For continuation pages: identify the matching source in `index.json` using notebook name + page number, then append body text to the correct existing `.md` file
- [ ] Sanitise filenames (strip special characters, replace spaces with `_`)

---

## 6. Module: Index Manager (`index_manager.py`)
- [ ] Read/write `index.json` atomically (write to temp file, then rename) to avoid corruption on crash
- [ ] Add one entry per source with: `title`, `author`, `year`, `notebook`, `page`, `date`, `md_file`
- [ ] Never duplicate entries — check before inserting

---

## 7. Module: Bibliography Lookup (`bib_lookup.py`)
- [ ] Query CrossRef API with title + author + year
- [ ] If CrossRef returns no confident match, query Semantic Scholar
- [ ] On success: format and append BibTeX entry to `library.bib`
- [ ] On failure: append stub BibTeX entry to `library.bib` (with title/author/year filled in, other fields as `TODO`) and log full source details to `incomplete_bib.txt`

---

## 8. Module: Error Handling & Alerts (`error_handler.py`)
- [ ] Implement retry wrapper: 5 attempts, exponential backoff (e.g. 5s → 10s → 20s → 40s → 80s)
- [ ] On 5th failure: log full traceback, send alert email via Gmail SMTP, terminate process
- [ ] Alert email to `nicholas.and.dixie@gmail.com` includes: filename, error message, full traceback
- [ ] Load Gmail credentials from env (`GMAIL_ADDRESS`, `GMAIL_APP_PASSWORD`)
- [ ] All logging via Python `logging` module → rotating log file (`ocr_pipeline.log`)

---

## 9. Main Orchestrator (`main.py`)
- [ ] Load `.env` via `python-dotenv`
- [ ] Initialise logger
- [ ] Start file watcher
- [ ] For each new image, run in order: image handling → OCR → output writing → index update → bib lookup
- [ ] Register SIGTERM handler for graceful shutdown

---

## 10. Deployment (Raspberry Pi)
- [ ] Write `systemd` service file (`notebook_ocr.service`) so the script runs on boot and restarts on crash
- [ ] Write `SETUP.md` covering:
  - Python environment setup on Pi
  - Installing dependencies from `requirements.txt`
  - Google Drive sync setup (e.g. `rclone`)
  - Populating `.env`
  - Enabling and starting the systemd service
  - How to check logs (`journalctl` + `ocr_pipeline.log`)

---

## 11. Testing
- [ ] Run full pipeline end-to-end on `notebooks/blue_1/test_page.heic`
- [ ] Verify `.md` file appears in `obsidian_notes/`
- [ ] Verify `index.json` updated correctly
- [ ] Verify `library.bib` updated (or `incomplete_bib.txt` if no match found)
- [ ] Simulate a continuation page and verify correct `.md` file is appended to
- [ ] Simulate API failure and verify retry + email alert behaviour
