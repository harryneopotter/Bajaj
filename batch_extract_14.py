"""
Extract the 14 newly processed Sarvam HTMLs with GPT-4o-mini
"""
import json
import os
import sys
import time
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI

# Load env
env_paths = [Path(".env"), Path(os.path.expanduser("~/.openclaw/.env"))]
for p in env_paths:
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY not found")
    sys.exit(1)

client = OpenAI(api_key=api_key)

SARVAM_DIR = Path("extracted/sarvam")
OUTPUT_DIR = Path("analysis/extractions")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gpt-4o-mini"
MAX_BODY_CHARS = 15000

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
- Extract date in YYYY-MM-DD format
- Product names should be clean
- Ignore: terms & conditions, bank details, totals, tax summary rows
- Do NOT extract HSN codes or tax descriptions as product names
- quantity and unit_price should be numbers
"""

def extract_body(html_path):
    content = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    body = soup.find("body")
    text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n[TRUNCATED]"
    return text

# Load batch files
batch = json.loads(Path("test_batch_15.json").read_text())

# Only process the 14 that succeeded (skip "Bajaj - Catalogue .2024.pdf")
test_files = [doc["filename"].replace(".pdf", ".html") for doc in batch if "Catalogue" not in doc["filename"]]

print(f"Extracting {len(test_files)} HTMLs with GPT-4o-mini...\n")

success = 0
errors = 0
skipped = 0

for i, fname in enumerate(test_files, 1):
    html_path = SARVAM_DIR / fname
    out_path = OUTPUT_DIR / fname.replace(".html", ".json")
    
    if out_path.exists():
        print(f"[{i:2d}] SKIP: {fname} (already extracted)")
        skipped += 1
        continue
    
    if not html_path.exists():
        print(f"[{i:2d}] ERROR: {fname} HTML not found")
        errors += 1
        continue
    
    print(f"[{i:2d}/{len(test_files)}] Extracting: {fname}")
    
    try:
        body_text = extract_body(html_path)
        if len(body_text) < 50:
            print(f"  SKIP: body too short ({len(body_text)} chars)")
            errors += 1
            continue
        
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": QUOTATION_PROMPT},
                {"role": "user", "content": body_text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content
        result = json.loads(text)
        
        # Add metadata
        result["source_file"] = fname
        result["doc_type"] = "quotation"
        
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        
        item_count = len(result.get("items", []))
        print(f"  ✓ {item_count} items extracted")
        success += 1
        
        time.sleep(0.3)  # Small delay to be nice to API
        
    except Exception as e:
        print(f"  ERROR: {e}")
        errors += 1

print("\n" + "=" * 60)
print(f"Extraction complete:")
print(f"  Success: {success}")
print(f"  Errors: {errors}")
print(f"  Skipped: {skipped}")
