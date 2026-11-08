import json
import logging
import os
import re
import time
from pathlib import Path

import httpx
from google import genai
from google.genai import errors
from google.genai.types import Part

from error_handler import with_retry
from rate_limiter import select_model, record_rate_limit

logger = logging.getLogger(__name__)

GEMINI_INSTRUCTIONS_PATH = Path("gemini_instructions.txt")
LIBRARY_BIB = Path("library.bib")
NETWORK_WAIT = 60  # seconds between attempts while there is no network connection


def load_base_prompt() -> str:
    return GEMINI_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def build_prompt(notebook: str, index: list) -> str:
    base = load_base_prompt()
    index_json = json.dumps(index, indent=2)
    bib_text = LIBRARY_BIB.read_text(encoding="utf-8") if LIBRARY_BIB.exists() else ""
    return f"""{base}

---
The notebook this page comes from is: {notebook}

Current index of all sources processed so far:
```json
{index_json}
```

Current bibliography (library.bib):
```bibtex
{bib_text}
```

Return your response ONLY as a valid JSON object — no surrounding text or markdown fences — using this exact structure:
{{
  "sources": [
    {{
      "title": "string or null",
      "author": "string or null",
      "year": "string or null",
      "page": "string or null",
      "is_continuation": false,
      "continuation_notebook": null,
      "continuation_page": null,
      "body": "markdown-formatted notes content only, no YAML front matter",
      "bib_status": "existing | new | not_found",
      "bib_entry": "full BibTeX entry string, or null"
    }}
  ]
}}

Rules:
- One object per source found on the page.
- If a source continues from a previous page (no title at the top of the page), set is_continuation to true, and set continuation_notebook and continuation_page to match the entry in the index that this page continues. Leave title/author/year/page as null if they cannot be determined independently.
- Expand all abbreviations in the body (e.g. "mkt" -> "market").
- Format the body with proper Markdown headings.
- Extract page numbers from the physical page image itself.

Bibliography rules:
- For each source, check whether it already appears in library.bib above (match on author surname(s) AND year exactly).
- If it is already there: set bib_status to "existing" and bib_entry to null.
- If it is NOT there and you can confidently identify the full publication: set bib_status to "new" and bib_entry to a complete BibTeX entry. The citation key should be SurnameYear (e.g. "Allen2009"). The author surname(s) and year in the entry MUST match the source metadata exactly.
- If it is NOT there and you cannot confidently identify the source: set bib_status to "not_found" and bib_entry to null.
- For continuation pages, set bib_status to "existing" and bib_entry to null (the original page already handled it)."""


def parse_response(text: str) -> dict:
    text = text.strip()
    # Strip markdown code fences if the model wraps the JSON anyway
    match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", text)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


@with_retry
def ocr_image(image_path: Path, notebook: str, index: list) -> dict:
    api_key = os.environ["GEMINI_API_KEY"]
    client = genai.Client(api_key=api_key)

    prompt = build_prompt(notebook, index)

    with open(image_path, "rb") as f:
        image_data = f.read()

    suffix = image_path.suffix.lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    mime_type = mime_map.get(suffix, "image/jpeg")

    # Neither of these is a failure of the page, so neither uses up a retry:
    # - a 429 (rejected without using quota): put that model on cooldown and try the
    #   next one; select_model() waits if every model is cooling down
    # - no connection at all (e.g. Wi-Fi not up yet after login): wait and try again
    while True:
        model = select_model()
        logger.info(f"Sending {image_path.name} to Gemini ({model})")
        try:
            response = client.models.generate_content(
                model=model,
                contents=[
                    Part.from_bytes(data=image_data, mime_type=mime_type),
                    prompt,
                ],
            )
        except errors.APIError as e:
            if e.code == 429:
                record_rate_limit(model, e.details)
                continue
            raise
        except httpx.ConnectError as e:
            logger.warning(f"Cannot reach Gemini ({e}) — waiting {NETWORK_WAIT}s for the connection")
            time.sleep(NETWORK_WAIT)
            continue

        logger.info(f"Gemini response received from {model}.")
        return parse_response(response.text)
