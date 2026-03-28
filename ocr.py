import json
import logging
import os
import re
from pathlib import Path

from google import genai
from google.genai.types import Part

from error_handler import with_retry

logger = logging.getLogger(__name__)

GEMINI_INSTRUCTIONS_PATH = Path("gemini_instructions.txt")
MODEL_NAME = "gemini-2.5-flash"


def load_base_prompt() -> str:
    return GEMINI_INSTRUCTIONS_PATH.read_text(encoding="utf-8")


def build_prompt(notebook: str, index: list) -> str:
    base = load_base_prompt()
    index_json = json.dumps(index, indent=2)
    return f"""{base}

---
The notebook this page comes from is: {notebook}

Current index of all sources processed so far:
```json
{index_json}
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
      "body": "markdown-formatted notes content only, no YAML front matter"
    }}
  ]
}}

Rules:
- One object per source found on the page.
- If a source continues from a previous page (no title at the top of the page), set is_continuation to true, and set continuation_notebook and continuation_page to match the entry in the index that this page continues. Leave title/author/year/page as null if they cannot be determined independently.
- Expand all abbreviations in the body (e.g. "mkt" -> "market").
- Format the body with proper Markdown headings.
- Extract page numbers from the physical page image itself."""


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

    logger.info(f"Sending {image_path.name} to Gemini ({MODEL_NAME})")
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=[
            Part.from_bytes(data=image_data, mime_type=mime_type),
            prompt,
        ],
    )
    logger.info("Gemini response received.")

    return parse_response(response.text)
