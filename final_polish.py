import json
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"

def final_polish():
    if not CATALOG_PATH.exists(): return
    
    catalog = json.loads(CATALOG_PATH.read_text())
    
    # Filter out entries that are obviously dates or header noise
    # e.g. "30 October", "Municipal Market", "ISO 9001"
    BAD_PATTERNS = [
        r"^\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)",
        r"MUNICIPAL MARKET", r"ISO 9001", r"ESTD", r"SYMBOL OF", r"BAJAJ SPORTS", r"GST NO"
    ]
    
    import re
    cleaned = []
    for p in catalog:
        name = p["product"].upper()
        if any(re.search(pat, name) for pat in BAD_PATTERNS):
            continue
        if len(name) < 5:
            continue
        cleaned.append(p)
        
    CATALOG_PATH.write_text(json.dumps(cleaned, indent=2))
    print(f"Final Polish: Catalog reduced to {len(cleaned)} high-fidelity items.")

if __name__ == "__main__":
    final_polish()
