# Notebook OCR — Claude Instructions

## Project context
OCR pipeline for handwritten notebook pages. See `ARCHITECTURE.md` for the full design and `README.md` for setup/usage.

## Research domain
Economic history. The user is an economic historian. Tailor suggestions accordingly.

## Before editing
- Read the file first. Read `ARCHITECTURE.md` if you need to understand how modules fit together.
- Read `gemini_instructions.txt` before changing anything in `ocr.py` — the prompt structure matters.
- Read `model_config.json` before changing anything in `rate_limiter.py`.

## Code conventions
- Python. Simple, explicit, modular — one concern per module.
- No unnecessary abstractions, docstrings, or comments on code you didn't change.
- Secrets come from environment variables or `.env` — never hardcode them.
- All state files (`index.json`, `library.bib`, `processed_files.json`, `rate_usage.json`) use atomic writes (write to `.tmp`, then replace) where implemented. Follow this pattern for new state files.

## Key constraints
- **One Gemini API call per page.** OCR, metadata extraction, bib lookup, and continuation detection all happen in a single request. Do not add separate API calls without discussing the rate-limit impact.
- **Rate limits are tight.** Free-tier Gemini. Model priorities and limits are in `model_config.json`. Any change that increases API calls per page needs justification.
- **This runs unattended.** The pipeline must handle errors gracefully — retry, alert, terminate. Do not swallow exceptions silently or leave the process in a broken state.

## Testing
There is no test suite. To test changes, run `python test_run.py [image path]`: it runs one page through `process_file` in a temporary copy of the project (real notes and state files are never touched; one Gemini request) and prints what was added. Do not add test infrastructure unless asked.

## Documentation
- `README.md` is for non-technical users. Keep setup and troubleshooting instructions clear and jargon-free.
- `ARCHITECTURE.md` is the technical reference. Update it when the pipeline design changes.
- Keep both in sync with the code. If you change behaviour, update the relevant docs in the same change.
