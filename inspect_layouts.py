import fitz
import re

files = ["/home/sachin/work/bajaj/data/pdf/more-pdf/Q9.pdf", "/home/sachin/work/bajaj/data/pdf/more-pdf/Q2.pdf"]
for f in files:
    print(f"\n--- FILE: {f} ---")
    doc = fitz.open(f)
    for page in doc:
        # Get blocks to see layout structure
        blocks = page.get_text("blocks")
        for b in blocks[:20]: # First 20 blocks
            print(f"Block: {b[4].strip()}")
