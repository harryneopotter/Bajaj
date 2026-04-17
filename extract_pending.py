#!/usr/bin/env python3
"""Quick GPT extraction for pending HTMLs"""
import os
import sys
import json
import time
from pathlib import Path
from bs4 import BeautifulSoup
from openai import OpenAI

# Load env
env_path = Path("/home/sachin/work/bajaj/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)

SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
EXTRACTIONS_DIR = Path("/home/sachin/work/bajaj/analysis/extractions")
EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

MAX_BODY_CHARS = 15000
MODEL = "gpt-4o-mini"

PROMPT = """You are a data extraction assistant for Bajaj Sports, a sports equipment retailer in India.

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
      "product": "Clean product name",
      "brand": "Brand name or null",
      "quantity": 10,
      "unit_price": 640.00,
      "hsn_code": "8-digit HSN code or null"
    }
  ]
}

Rules:
- Client is the RECIPIENT, not Bajaj Sports
- Extract date in YYYY-MM-DD format
- Product names should be clean
- Ignore: terms, bank details, totals, tax rows
- Do NOT extract HSN codes as product names
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

# Find pending HTMLs
all_htmls = list(SARVAM_DIR.glob("*.html"))
pending = []
for html in all_htmls:
    # Use same filename for JSON (just change extension)
    json_path = EXTRACTIONS_DIR / html.name.replace(".html", ".json")
    if not json_path.exists():
        pending.append(html)

print(f"Total HTMLs: {len(all_htmls)}")
print(f"Pending extraction: {len(pending)}\n")

if not pending:
    print("✅ All HTMLs already extracted!")
    sys.exit(0)

# Show first few
print(f"First {min(5, len(pending))} pending files:")
for html in pending[:5]:
    print(f"  - {html.name}")
print()

api_key = os.environ.get("OPENAI_API_KEY")
if not api_key:
    print("ERROR: OPENAI_API_KEY not found")
    sys.exit(1)

client = OpenAI(api_key=api_key)

success = 0
errors = 0

for i, html_path in enumerate(pending, 1):
    json_path = EXTRACTIONS_DIR / html_path.name.replace(".html", ".json")
    
    print(f"[{i:3d}/{len(pending)}] {html_path.name[:50]}...")
    
    try:
        body_text = extract_body(html_path)
        if len(body_text) < 50:
            print(f"  SKIP: body too short")
            errors += 1
            continue
        
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": PROMPT},
                {"role": "user", "content": body_text},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        
        text = resp.choices[0].message.content
        result = json.loads(text)
        result["source_file"] = html_path.name
        result["doc_type"] = "quotation"
        
        json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        
        item_count = len(result.get("items", []))
        client_name = result.get("client", {}).get("name", "Unknown")[:30]
        print(f"  ✓ {client_name} | {item_count} items")
        success += 1
        
        time.sleep(0.3)
    
    except Exception as e:
        print(f"  ERROR: {str(e)[:60]}")
        errors += 1

print(f"\n{'='*60}")
print(f"Complete: {success} success, {errors} errors")
print(f"{'='*60}")
