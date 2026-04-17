import os
import time
from pathlib import Path
from mistral_parse import parse_pdf_to_markdown

# Configuration
PDF_DIR = Path("/home/sachin/work/bajaj/data/pdf")
EXTRACTED_DIR = Path("/home/sachin/work/bajaj/extracted")
MISTRAL_DIR = Path("/home/sachin/work/bajaj/extracted/mistral")
MISTRAL_DIR.mkdir(parents=True, exist_ok=True)

def run_batch(limit=50):
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
        output_file = MISTRAL_DIR / f"{pdf.stem}_mistral.md"
        if not output_file.exists():
            to_process.append(pdf)
            
    print(f"Already processed: {len(unique_pdfs) - len(to_process)}")
    print(f"Remaining to process: {len(to_process)}")
    
    if not to_process:
        print("Everything is up to date.")
        return

    # Respect the batch limit
    process_now = to_process[:limit]
    print(f"Starting batch of {len(process_now)} files...")

    for i, pdf in enumerate(process_now, 1):
        print(f"[{i}/{len(process_now)}] Processing {pdf.name}...")
        try:
            parse_pdf_to_markdown(pdf, MISTRAL_DIR)
            time.sleep(1)
        except Exception as e:
            print(f"Failed to process {pdf.name}: {e}")
            continue
    
    print(f"Batch of {len(process_now)} complete. Please verify and give the go-ahead for next batch.")

if __name__ == "__main__":
    run_batch(limit=50)
