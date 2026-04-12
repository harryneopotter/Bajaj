import os
import time
import subprocess
import json
from pathlib import Path

# Configuration
ROOT_DIR = Path("/home/sachin/work/bajaj")
PDF_DIR = ROOT_DIR / "data/pdf"
EXTRACTED_DIR = ROOT_DIR / "extracted"
SARVAM_OUTPUT_DIR = ROOT_DIR / "extracted/sarvam"
SARVAM_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def run_all_batches():
    while True:
        all_pdfs = list(PDF_DIR.rglob("*.pdf"))
        all_pdfs.extend(list(EXTRACTED_DIR.glob("*.pdf")))
        
        # Remove duplicates by filename
        seen = set()
        unique_pdfs = []
        for p in all_pdfs:
            if p.name not in seen:
                unique_pdfs.append(p)
                seen.add(p.name)
        
        to_process = []
        for pdf in unique_pdfs:
            # Check if we already have the html or the zip
            output_zip = SARVAM_OUTPUT_DIR / f"{pdf.stem}_sarvam.zip"
            output_html = SARVAM_OUTPUT_DIR / f"{pdf.stem}.html"
            if not output_zip.exists() and not output_html.exists():
                to_process.append(pdf)
                
        if not to_process:
            print("All files processed.")
            break

        print(f"Remaining to process: {len(to_process)}. Starting next batch...")

        # Process a small chunk
        chunk = to_process[:20]
        for i, pdf in enumerate(chunk, 1):
            print(f"Sarvam Processing: {pdf.name}...")
            try:
                cmd = [
                    "/home/sachin/work/bajaj/quotegen/venv/bin/python3",
                    "/home/sachin/work/bajaj/sarvam_parse.py",
                    str(pdf)
                ]
                subprocess.run(cmd, check=True)
                
                # Unzip
                zip_path = SARVAM_OUTPUT_DIR / f"{pdf.stem}_sarvam.zip"
                if zip_path.exists():
                    html_target = SARVAM_OUTPUT_DIR / f"{pdf.stem}.html"
                    subprocess.run(f"unzip -p {zip_path} document.html > {html_target}", shell=True, check=True)
                
                time.sleep(1) 
            except Exception as e:
                print(f"Error on {pdf.name}: {e}")
                continue
        
        # Auto-ingest after every chunk to update the UI
        print("Syncing database...")
        try:
            subprocess.run(["/home/sachin/work/bajaj/quotegen/venv/bin/python3", "/home/sachin/work/bajaj/parse_html.py"], check=True)
            subprocess.run(["/home/sachin/work/bajaj/quotegen/venv/bin/python3", "/home/sachin/work/bajaj/partition_data.py"], check=True)
            subprocess.run(["/home/sachin/work/bajaj/quotegen/venv/bin/python3", "/home/sachin/work/bajaj/final_polish.py"], check=True)
        except Exception as e:
            print(f"Ingest Error: {e}")

if __name__ == "__main__":
    run_all_batches()
