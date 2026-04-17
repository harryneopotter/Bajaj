"""
Complete pipeline: Sarvam → GPT extraction → Production merge
Processes all remaining PDFs (currently 241) that don't have Sarvam HTML
"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path
import sqlite3
from bs4 import BeautifulSoup
from openai import OpenAI

# =============================================================================
# Configuration
# =============================================================================

DB_PATH = Path("/home/sachin/work/bajaj/data/quotevault.db")
SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
EXTRACTIONS_DIR = Path("/home/sachin/work/bajaj/analysis/extractions")
VENV_PYTHON = Path("/home/sachin/work/bajaj/quotegen/venv/bin/python3")
SARVAM_SCRIPT = Path("/home/sachin/work/bajaj/sarvam_parse.py")

SARVAM_DIR.mkdir(parents=True, exist_ok=True)
EXTRACTIONS_DIR.mkdir(parents=True, exist_ok=True)

# Rate limits
SARVAM_DELAY = 7  # seconds between Sarvam requests (10 req/min = 6s, use 7s to be safe)
GPT_DELAY = 0.3   # small delay for GPT API

# GPT settings
MAX_BODY_CHARS = 15000
GPT_MODEL = "gpt-4o-mini"

# Load env
env_path = Path("/home/sachin/work/bajaj/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)

# =============================================================================
# Step 1: Find PDFs needing Sarvam processing
# =============================================================================

def get_pending_pdfs():
    """Get list of PDFs that don't have Sarvam HTML"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('SELECT id, filename, pdf_path FROM docs ORDER BY id DESC')
    rows = cur.fetchall()
    conn.close()
    
    pending = []
    for doc_id, fname, ppath in rows:
        base = Path(fname).stem
        html_path = SARVAM_DIR / f"{base}.html"
        
        if not html_path.exists():
            pending.append({
                'doc_id': doc_id,
                'filename': fname,
                'pdf_path': ppath.replace('/data/', '/home/sachin/work/bajaj/data/')
            })
    
    return pending

# =============================================================================
# Step 2: Sarvam batch processing
# =============================================================================

def process_sarvam_batch(batch):
    """Process PDFs through Sarvam API with rate limiting"""
    print(f"\n{'='*70}")
    print(f"STEP 1: Sarvam HTML Generation ({len(batch)} PDFs)")
    print(f"{'='*70}\n")
    
    success = 0
    errors = []
    skipped = 0
    
    for i, doc in enumerate(batch, 1):
        pdf_path = Path(doc["pdf_path"])
        base_name = doc["filename"].replace(".pdf", "")
        output_html = SARVAM_DIR / f"{base_name}.html"
        
        if not pdf_path.exists():
            print(f"[{i:3d}/{len(batch)}] SKIP: {doc['filename']} - PDF not found")
            skipped += 1
            continue
        
        print(f"[{i:3d}/{len(batch)}] Processing: {doc['filename']}")
        
        try:
            # Run Sarvam parser
            cmd = [str(VENV_PYTHON), str(SARVAM_SCRIPT), str(pdf_path)]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            
            if result.returncode != 0:
                error_msg = result.stderr[:150] if result.stderr else "Unknown error"
                print(f"  ERROR: {error_msg}")
                errors.append({'file': doc['filename'], 'error': error_msg})
                continue
            
            # Extract ZIP
            zip_path = SARVAM_DIR / f"{pdf_path.stem}_sarvam.zip"
            if zip_path.exists():
                extract_cmd = f"unzip -o -q '{zip_path}' -d '{SARVAM_DIR}/temp_{i}' && mv '{SARVAM_DIR}/temp_{i}/document.html' '{output_html}' && rm -rf '{SARVAM_DIR}/temp_{i}' && rm '{zip_path}'"
                subprocess.run(extract_cmd, shell=True, check=True)
                print(f"  ✓ Saved: {base_name}.html")
                success += 1
            else:
                print(f"  WARNING: ZIP not found")
                errors.append({'file': doc['filename'], 'error': 'ZIP not created'})
            
            # Rate limiting
            if i < len(batch):
                time.sleep(SARVAM_DELAY)
        
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT after 90s")
            errors.append({'file': doc['filename'], 'error': 'Timeout'})
        except Exception as e:
            print(f"  FAILED: {e}")
            errors.append({'file': doc['filename'], 'error': str(e)})
    
    print(f"\n{'='*70}")
    print(f"Sarvam Results: {success} success, {len(errors)} errors, {skipped} skipped")
    print(f"{'='*70}\n")
    
    return success, errors, skipped

# =============================================================================
# Step 3: GPT extraction
# =============================================================================

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
  ],
  "source_file": "filename.html",
  "doc_type": "quotation"
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
    """Extract text body from HTML"""
    content = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    body = soup.find("body")
    text = body.get_text(separator="\n", strip=True) if body else soup.get_text(separator="\n", strip=True)
    if len(text) > MAX_BODY_CHARS:
        text = text[:MAX_BODY_CHARS] + "\n[TRUNCATED]"
    return text

def process_gpt_extraction(batch):
    """Extract data from Sarvam HTMLs using GPT-4o-mini"""
    print(f"\n{'='*70}")
    print(f"STEP 2: GPT-4o-mini Extraction")
    print(f"{'='*70}\n")
    
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY not found in environment")
        return 0, []
    
    client = OpenAI(api_key=api_key)
    
    success = 0
    errors = []
    skipped = 0
    
    for i, doc in enumerate(batch, 1):
        base_name = doc["filename"].replace(".pdf", "")
        html_path = SARVAM_DIR / f"{base_name}.html"
        json_path = EXTRACTIONS_DIR / f"{base_name}.json"
        
        if json_path.exists():
            skipped += 1
            continue
        
        if not html_path.exists():
            continue  # Skip if Sarvam failed
        
        print(f"[{i:3d}/{len(batch)}] Extracting: {doc['filename']}")
        
        try:
            body_text = extract_body(html_path)
            if len(body_text) < 50:
                print(f"  SKIP: body too short ({len(body_text)} chars)")
                errors.append({'file': doc['filename'], 'error': 'Body too short'})
                continue
            
            resp = client.chat.completions.create(
                model=GPT_MODEL,
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
            result["source_file"] = f"{base_name}.html"
            result["doc_type"] = "quotation"
            
            json_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            
            item_count = len(result.get("items", []))
            print(f"  ✓ {item_count} items extracted")
            success += 1
            
            time.sleep(GPT_DELAY)
        
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append({'file': doc['filename'], 'error': str(e)})
    
    print(f"\n{'='*70}")
    print(f"Extraction Results: {success} success, {len(errors)} errors, {skipped} skipped")
    print(f"{'='*70}\n")
    
    return success, errors

# =============================================================================
# Main execution
# =============================================================================

if __name__ == "__main__":
    print(f"\n{'='*70}")
    print(f"Bajaj Sports - Complete Processing Pipeline")
    print(f"{'='*70}\n")
    
    # Get pending PDFs
    print("Finding PDFs needing processing...")
    pending = get_pending_pdfs()
    print(f"Found {len(pending)} PDFs without Sarvam HTML\n")
    
    if not pending:
        print("✅ All PDFs already have Sarvam HTML!")
        print("\nChecking for missing extractions...")
        
        # Check if any HTMLs need extraction
        all_htmls = list(SARVAM_DIR.glob("*.html"))
        need_extraction = []
        for html in all_htmls:
            json_path = EXTRACTIONS_DIR / html.name.replace(".html", ".json")
            if not json_path.exists():
                need_extraction.append({'filename': html.name, 'pdf_path': ''})
        
        if need_extraction:
            print(f"Found {len(need_extraction)} HTMLs needing extraction\n")
            process_gpt_extraction(need_extraction)
        else:
            print("✅ All HTMLs already extracted!")
        
        sys.exit(0)
    
    # Process in batch
    sarvam_success, sarvam_errors, sarvam_skipped = process_sarvam_batch(pending)
    
    # Extract with GPT
    gpt_success, gpt_errors = process_gpt_extraction(pending)
    
    # Summary
    print(f"\n{'='*70}")
    print(f"PIPELINE COMPLETE")
    print(f"{'='*70}")
    print(f"\nSarvam HTML Generation:")
    print(f"  Success: {sarvam_success}")
    print(f"  Errors: {len(sarvam_errors)}")
    print(f"  Skipped: {sarvam_skipped}")
    
    print(f"\nGPT Extraction:")
    print(f"  Success: {gpt_success}")
    print(f"  Errors: {len(gpt_errors)}")
    
    if sarvam_errors:
        print(f"\nSarvam errors:")
        for err in sarvam_errors[:10]:  # Show first 10
            print(f"  - {err['file']}: {err['error']}")
    
    if gpt_errors:
        print(f"\nGPT errors:")
        for err in gpt_errors[:10]:
            print(f"  - {err['file']}: {err['error']}")
    
    print(f"\n{'='*70}")
    print("Next step: Merge extractions to production catalogs")
    print("Run: python3 merge_to_production.py")
    print(f"{'='*70}\n")
