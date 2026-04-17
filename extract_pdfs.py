#!/usr/bin/env python3
"""Extract text from all PDFs in the bajaj data directory."""

import os
import fitz  # PyMuPDF
from pathlib import Path

PDF_DIR = Path("/home/sachin/work/bajaj/data/pdf/2026/01")
OUTPUT_DIR = Path("/home/sachin/work/bajaj/extracted")
OUTPUT_DIR.mkdir(exist_ok=True)

pdfs = sorted(PDF_DIR.glob("*.pdf"))
print(f"Found {len(pdfs)} PDFs to process")

scanned_count = 0
text_count = 0

for i, pdf_path in enumerate(pdfs, 1):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        
        for page in doc:
            text += page.get_text("text")
        
        doc.close()
        
        # Save extracted text
        output_file = OUTPUT_DIR / f"{pdf_path.stem}.txt"
        output_file.write_text(text, encoding="utf-8")
        
        # Check if it's likely a scan (very little or no text)
        text_len = len(text.strip())
        if text_len < 100:
            scanned_count += 1
            status = "SCAN (little/no text)"
        else:
            text_count += 1
            status = f"OK ({text_len} chars)"
        
        print(f"[{i}/{len(pdfs)}] {pdf_path.name}: {status}")
        
    except Exception as e:
        print(f"[{i}/{len(pdfs)}] {pdf_path.name}: ERROR - {e}")

print(f"\nDone! Extracted: {text_count}, Likely scans: {scanned_count}, Total: {len(pdfs)}")
