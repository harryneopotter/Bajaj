#!/usr/bin/env python3
"""
Process pending PDFs in batches of 50 with progress tracking
"""
import os
import sys
import time
import json
import subprocess
from pathlib import Path
import sqlite3

# Config
DB_PATH = Path("/home/sachin/work/bajaj/data/quotevault.db")
SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
VENV_PYTHON = Path("/home/sachin/work/bajaj/quotegen/venv/bin/python3")
SARVAM_SCRIPT = Path("/home/sachin/work/bajaj/sarvam_parse.py")
SARVAM_DELAY = 7  # seconds

BATCH_SIZE = int(sys.argv[1]) if len(sys.argv) > 1 else 50

# Load env
env_path = Path("/home/sachin/work/bajaj/.env")
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key.strip(), val)

def get_pending_batch(limit=50):
    """Get next batch of PDFs needing Sarvam processing"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    cur.execute('SELECT id, filename, pdf_path FROM docs ORDER BY id DESC')
    rows = cur.fetchall()
    conn.close()
    
    pending = []
    for doc_id, fname, ppath in rows:
        if len(pending) >= limit:
            break
        
        base = Path(fname).stem
        html_path = SARVAM_DIR / f"{base}.html"
        
        if not html_path.exists():
            pending.append({
                'doc_id': doc_id,
                'filename': fname,
                'pdf_path': ppath.replace('/data/', '/home/sachin/work/bajaj/data/')
            })
    
    return pending

print(f"Fetching next {BATCH_SIZE} PDFs needing Sarvam processing...")
batch = get_pending_batch(BATCH_SIZE)

if not batch:
    print("✅ No pending PDFs found!")
    sys.exit(0)

print(f"Processing {len(batch)} PDFs\n")

success = 0
errors = []

for i, doc in enumerate(batch, 1):
    pdf_path = Path(doc["pdf_path"])
    base_name = doc["filename"].replace(".pdf", "")
    output_html = SARVAM_DIR / f"{base_name}.html"
    
    if not pdf_path.exists():
        print(f"[{i:3d}/{len(batch)}] SKIP: {doc['filename']} - PDF not found")
        continue
    
    print(f"[{i:3d}/{len(batch)}] {doc['filename']}")
    
    try:
        cmd = [str(VENV_PYTHON), str(SARVAM_SCRIPT), str(pdf_path)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
        
        if result.returncode != 0:
            # Check if it's the page limit error
            if "maximum allowed is 10" in result.stderr:
                print(f"  SKIP: exceeds 10-page limit")
                continue
            error_msg = result.stderr[:100] if result.stderr else "Unknown error"
            print(f"  ERROR: {error_msg}")
            errors.append(doc['filename'])
            continue
        
        # Extract ZIP
        zip_path = SARVAM_DIR / f"{pdf_path.stem}_sarvam.zip"
        if zip_path.exists():
            temp_dir = SARVAM_DIR / f"temp_{i}"
            
            # Clean temp dir if it exists
            if temp_dir.exists():
                import shutil
                shutil.rmtree(temp_dir)
            
            extract_cmd = f"unzip -o -q '{zip_path}' -d '{temp_dir}'"
            subprocess.run(extract_cmd, shell=True, check=True)
            
            temp_html = temp_dir / "document.html"
            if temp_html.exists():
                temp_html.rename(output_html)
                import shutil
                shutil.rmtree(temp_dir)
                zip_path.unlink()
                print(f"  ✓ Saved")
                success += 1
            else:
                print(f"  ERROR: document.html not in ZIP")
                errors.append(doc['filename'])
        else:
            print(f"  ERROR: ZIP not created")
            errors.append(doc['filename'])
        
        # Rate limit
        if i < len(batch):
            time.sleep(SARVAM_DELAY)
    
    except subprocess.TimeoutExpired:
        print(f"  TIMEOUT")
        errors.append(doc['filename'])
    except Exception as e:
        print(f"  FAILED: {e}")
        errors.append(doc['filename'])

print(f"\n{'='*60}")
print(f"Batch complete: {success} success, {len(errors)} errors")
if errors:
    print(f"\nErrors: {', '.join(errors[:5])}")
    if len(errors) > 5:
        print(f"... and {len(errors)-5} more")
print(f"{'='*60}")
