import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

# Config
SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
OUTPUT_PATH = Path("/home/sachin/work/bajaj/analysis/doc_classification.json")

# Keywords for classification (Rule-based)
KEYWORDS = {
    "quotation": ["quotation", "proforma", "quote", "estimate"],
    "invoice": ["tax invoice", "irn", "e-invoice", "gstin", "bill of supply"],
    "skip": ["certificate", "ledger", "bank statement", "account statement", "udyam", "msme"]
}

def classify_file(path):
    """
    Reads HTML, scans for keywords in body, returns doc_type + reason.
    """
    try:
        content = path.read_text(encoding="utf-8").lower()
    except Exception as e:
        return "error", str(e)

    # Check invoice/quotation FIRST (udyam/msme/certificate text appears
    # in headers/footers of legitimate business documents)

    # 1. Check for Invoice (before quote — some invoices mention 'quotation ref')
    for kw in KEYWORDS["invoice"]:
        if kw in content:
            return "invoice", f"found '{kw}'"

    # 2. Check for Quotation
    for kw in KEYWORDS["quotation"]:
        if kw in content:
            return "quotation", f"found '{kw}'"

    # 3. Check for Skip (only if no invoice/quotation signal)
    for kw in KEYWORDS["skip"]:
        if kw in content:
            return "skip", f"found '{kw}'"
            
    # 4. Fallback logic
    if "<table" in content:
        # If it has a table but no keywords, assume it's a legacy quote
        return "quotation", "fallback: has table"
        
    return "skip", "fallback: no keywords or table"

def main():
    if not SARVAM_DIR.exists():
        print(f"Error: {SARVAM_DIR} does not exist.")
        return

    results = {}
    html_files = list(SARVAM_DIR.glob("*.html"))
    print(f"Scanning {len(html_files)} files...")

    stats = {"quotation": 0, "invoice": 0, "skip": 0, "error": 0}

    for f in html_files:
        doc_type, reason = classify_file(f)
        results[f.name] = {
            "doc_type": doc_type,
            "reason": reason
        }
        if doc_type in stats:
            stats[doc_type] += 1
        else:
            stats["error"] += 1

    # Save output
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(results, indent=2))
    
    print("\nClassification Complete.")
    print(json.dumps(stats, indent=2))
    print(f"\nResults saved to: {OUTPUT_PATH}")

if __name__ == "__main__":
    main()
