"""
Batch process 15 PDFs through Sarvam with rate limiting
"""
import os
import time
import subprocess
import json
from pathlib import Path

# Load env
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)

SARVAM_OUTPUT_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
SARVAM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# Load batch manifest
batch = json.loads(Path("test_batch_15.json").read_text())

print(f"Processing {len(batch)} PDFs with Sarvam (10 req/min limit)...\n")

success = 0
errors = 0
skipped = 0

for i, doc in enumerate(batch, 1):
    pdf_path = Path(doc["pdf_path_host"])
    base_name = doc["filename"].replace(".pdf", "")
    output_html = SARVAM_OUTPUT_DIR / f"{base_name}.html"
    
    if not pdf_path.exists():
        print(f"[{i:2d}] SKIP: {doc['filename']} - PDF not found")
        skipped += 1
        continue
    
    if output_html.exists():
        print(f"[{i:2d}] SKIP: {doc['filename']} - HTML exists")
        skipped += 1
        continue
    
    print(f"[{i:2d}/{len(batch)}] Processing: {doc['filename']}")
    
    try:
        cmd = [
            "/home/sachin/work/bajaj/quotegen/venv/bin/python3",
            "/home/sachin/work/bajaj/sarvam_parse.py",
            str(pdf_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if result.returncode != 0:
            print(f"  ERROR: {result.stderr[:150]}")
            errors += 1
            continue
        
        # Show last line of output
        lines = result.stdout.strip().splitlines()
        if lines:
            print(f"  {lines[-1]}")
        
        # Extract ZIP
        zip_path = SARVAM_OUTPUT_DIR / f"{pdf_path.stem}_sarvam.zip"
        if zip_path.exists():
            extract_cmd = f"unzip -o -q '{zip_path}' -d '{SARVAM_OUTPUT_DIR}/temp_{i}' && mv '{SARVAM_OUTPUT_DIR}/temp_{i}/document.html' '{output_html}' && rm -rf '{SARVAM_OUTPUT_DIR}/temp_{i}'"
            subprocess.run(extract_cmd, shell=True, check=True)
            print(f"  ✓ Saved: {base_name}.html")
            success += 1
        else:
            print(f"  WARNING: ZIP not found")
            errors += 1
        
        # Rate limiting: 10 req/min = 6s between requests
        if i < len(batch):
            print(f"  Rate limit: 7s...\n")
            time.sleep(7)
        
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT after 90s")
        errors += 1
    except Exception as e:
        print(f"  FAILED: {e}")
        errors += 1

print("\n" + "=" * 60)
print(f"Sarvam batch complete:")
print(f"  Success: {success}")
print(f"  Errors: {errors}")
print(f"  Skipped: {skipped}")
