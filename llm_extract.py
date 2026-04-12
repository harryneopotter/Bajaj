"""
Step 2: LLM-based structured extraction using GPT-4o-mini.

Reads doc_classification.json, sends HTML body content with doc-type-specific
prompts, outputs one JSON per file to analysis/extractions/.
"""

import json
import os
import sys
import time
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI

# --- Config ---
SARVAM_DIR = Path("extracted/sarvam")
CLASSIFICATION_PATH = Path("analysis/doc_classification.json")
OUTPUT_DIR = Path("analysis/extractions")
ENV_PATHS = [Path(".env"), Path(os.path.expanduser("~/.openclaw/.env"))]

MODEL = "gpt-4o-mini"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds


def load_env():
    """Load env vars from .env files."""
    for p in ENV_PATHS:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), val)


QUOTATION_PROMPT = """You are a data extraction assistant for Bajaj Sports, a sports equipment retailer in India.

Extract structured data from this QUOTATION document. Return valid JSON only, no markdown.

Schema:
{
  "client": {
    "name": "Organization name (NOT Bajaj Sports, that's the seller)",
    "address": "Full address or null",
    "phone": "Phone number or null",
    "gstin": "15-char GSTIN or null"
  },
  "date": "YYYY-MM-DD or null",
  "ref_number": "Quotation/reference number or null",
  "items": [
    {
      "product": "Clean product name (no specs dump, no HSN codes)",
      "brand": "Brand name or null",
      "quantity": 10,
      "unit_price": 640.00,
      "hsn_code": "8-digit HSN code or null"
    }
  ]
}

Rules:
- Client is the RECIPIENT, not Bajaj Sports (the sender/seller)
- Extract date in YYYY-MM-DD format. Look for "Date:", "Dt:", or date patterns
- Product names should be clean: "Hi Grip Basketball" not "Hi Grip Basketball Size 7 Art No 13012 Made of Synthetic Leather..."
- Ignore: terms & conditions, bank details, grand totals, subtotals, tax summary rows
- Do NOT extract HSN codes, GST percentages, or "Amount" as product names
- If a row is clearly a subtotal/total/tax line, skip it
- quantity and unit_price should be numbers, not strings
- If you can identify the brand from context (e.g. "Cosco Hi Grip"), split it: brand="Cosco", product="Hi Grip Basketball"
"""

INVOICE_PROMPT = """You are a data extraction assistant for Bajaj Sports, a sports equipment retailer in India.

Extract structured data from this TAX INVOICE document. Return valid JSON only, no markdown.

Schema:
{
  "client": {
    "name": "Buyer/consignee organization name (NOT Bajaj Sports)",
    "address": "Full address or null",
    "phone": "Phone number or null",
    "gstin": "15-char GSTIN or null"
  },
  "date": "YYYY-MM-DD or null",
  "ref_number": "Invoice number or null",
  "items": [
    {
      "product": "Clean product name",
      "brand": "Brand name or null",
      "quantity": 10,
      "unit_price": 640.00,
      "hsn_code": "8-digit HSN code or null"
    }
  ]
}

Rules:
- Client/buyer is the RECIPIENT, not Bajaj Sports (the seller)
- Ignore: IRN strings, e-invoice QR codes, bank details, GST summary rows, grand totals
- Extract ONLY actual product line items from the item table
- Do NOT extract HSN codes, GST rates, CGST/SGST/IGST amounts, or "Amount" as products
- Product names should be clean and readable
- If buyer and consignee differ, use the buyer name
- quantity and unit_price should be numbers, not strings
"""


MAX_BODY_CHARS = 15000  # ~4K tokens, enough for any single document


def extract_body(html_path):
    """Extract body text from HTML, stripping CSS/style/script. Returns text, not HTML."""
    content = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")

    for tag in soup.find_all(["style", "script"]):
        tag.decompose()

    body = soup.find("body")
    if body:
        # Keep table structure as text for better extraction
        text = body.get_text(separator="\n", strip=True)
    else:
        text = soup.get_text(separator="\n", strip=True)

    # Truncate very large documents
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n[TRUNCATED]"
    return text


def call_gpt(client, body_text, doc_type):
    """Call GPT-4o-mini for extraction."""
    prompt = QUOTATION_PROMPT if doc_type == "quotation" else INVOICE_PROMPT

    for attempt in range(MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": body_text},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            text = resp.choices[0].message.content
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from response
            try:
                start = text.index("{")
                end = text.rindex("}") + 1
                return json.loads(text[start:end])
            except (ValueError, json.JSONDecodeError):
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_DELAY)
                    continue
                return None
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  Retry {attempt + 1}/{MAX_RETRIES}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                print(f"  FAILED after {MAX_RETRIES} attempts: {e}")
                return None


def main():
    load_env()

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment or .env files.")
        print(f"Checked: {[str(p) for p in ENV_PATHS]}")
        sys.exit(1)

    client = OpenAI(api_key=api_key)

    if not CLASSIFICATION_PATH.exists():
        print(f"ERROR: {CLASSIFICATION_PATH} not found. Run classify_docs.py first.")
        sys.exit(1)

    classification = json.loads(CLASSIFICATION_PATH.read_text())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Filter to quotation + invoice only
    to_process = {
        fname: info
        for fname, info in classification.items()
        if info["doc_type"] in ("quotation", "invoice")
    }

    print(f"Processing {len(to_process)} files (skipping {len(classification) - len(to_process)} classified as skip/error)")

    done = 0
    errors = 0
    skipped = 0

    for fname, info in to_process.items():
        out_path = OUTPUT_DIR / fname.replace(".html", ".json")

        # Skip if already extracted
        if out_path.exists():
            skipped += 1
            continue

        html_path = SARVAM_DIR / fname
        if not html_path.exists():
            print(f"  SKIP {fname}: HTML file not found")
            errors += 1
            continue

        body_text = extract_body(html_path)
        if len(body_text) < 50:
            print(f"  SKIP {fname}: body too short ({len(body_text)} chars)")
            errors += 1
            continue

        print(f"  [{done + 1}/{len(to_process) - skipped}] {fname} ({info['doc_type']})")

        result = call_gpt(client, body_text, info["doc_type"])
        if result is None:
            errors += 1
            continue

        # Add metadata
        result["source_file"] = fname
        result["doc_type"] = info["doc_type"]

        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        done += 1

        time.sleep(0.2)

    print(f"\nDone. Extracted: {done}, Skipped (existing): {skipped}, Errors: {errors}")
    print(f"Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
