import os
import time
import subprocess
from pathlib import Path

# Configuration
PDF_DIR = Path("/home/sachin/work/bajaj/data/pdf")
EXTRACTED_DIR = Path("/home/sachin/work/bajaj/extracted")
SARVAM_OUTPUT_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
SARVAM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_sarvam_batch(limit=50):
    all_pdfs = list(PDF_DIR.rglob("*.pdf"))
    all_pdfs.extend(list(EXTRACTED_DIR.glob("*.pdf")))
    
    # Remove duplicates by filename
    seen = set()
    unique_pdfs = []
    for p in all_pdfs:
        if p.name not in seen:
            unique_pdfs.append(p)
            seen.add(p.name)
    
    print(f"Found {len(unique_pdfs)} unique PDFs.")
    
    to_process = []
    for pdf in unique_pdfs:
        # Check if we already have the html or the zip
        output_zip = SARVAM_OUTPUT_DIR / f"{pdf.stem}_sarvam.zip"
        output_html = SARVAM_OUTPUT_DIR / f"{pdf.stem}.html"
        if not output_zip.exists() and not output_html.exists():
            to_process.append(pdf)
            
    print(f"Already processed: {len(unique_pdfs) - len(to_process)}")
    print(f"Remaining to process: {len(to_process)}")
    
    if not to_process:
        print("Everything is up to date.")
        return

    process_now = to_process[:limit]
    print(f"Starting Sarvam batch of {len(process_now)} files...")

    for i, pdf in enumerate(process_now, 1):
        print(f"[{i}/{len(process_now)}] Sarvam Processing {pdf.name}...")
        try:
            # Run the existing sarvam_parse.py script
            # We use the venv python to ensure dependencies
            cmd = [
                "/home/sachin/work/bajaj/quotegen/venv/bin/python3",
                "/home/sachin/work/bajaj/sarvam_parse.py",
                str(pdf)
            ]
            # Environment variables are handled by the script loading .env or exported in shell
            subprocess.run(cmd, check=True)
            
            # Post-process: Unzip the file immediately to its final html name
            zip_path = SARVAM_OUTPUT_DIR / f"{pdf.stem}_sarvam.zip"
            if zip_path.exists():
                # unzip -p zipfile document.html > target.html
                html_target = SARVAM_OUTPUT_DIR / f"{pdf.stem}.html"
                subprocess.run(f"unzip -p {zip_path} document.html > {html_target}", shell=True, check=True)
                print(f"Extracted HTML to {html_target}")
            
            time.sleep(1) # Safety gap
        except Exception as e:
            print(f"Failed to process {pdf.name}: {e}")
            continue
    
    print(f"Sarvam Batch of {len(process_now)} complete.")

if __name__ == "__main__":
    run_sarvam_batch(limit=50)
