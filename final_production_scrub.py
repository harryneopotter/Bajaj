import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"

# Patterns from Ken's bad-data report
JUNK_REGEX = [
    r"^IRN:", r"^GSTIN", r"^GOAL POSTS", r"^HOCKEY GOAL POSTS", r"^Estd\. 1949",
    r"^No\. [A-Z0-9/]", r"^Order No:", r"^WL-[0-9]", r"^अनुबंध", r"^Registered office",
    r"^Subject:", r"^Constitution of Business", r"^Name of Items", r"^State Name",
    r"^TYPE OF ENTERPRISE", r"^Symbol of:", r"^Quotation Info:", r"^Unlock Policy",
    r"^We are the Authorized", r"^This is a system generated", r"^The PM SHRI Scheme",
    r"^The Principal$", r"^The Warden$", r"^The Bursar$", r"^The Manager$", r"^The Admin Officer$",
    r"^The Purchase Department$", r"^The Purchase Manager$", r"^General Secretary$", r"^Regional Engineer$",
    r"^Administrative Supervisor", r"^Landmark Near", r"^New Delhi", r"^HONJ04", r"^APPROVED CONTRACTORS",
    r"^C/o\.", r"^Ministry of Commerce", r"^Thank you for", r"^Delivery:", r"has the privilege to", r"regarding the above"
]

INSTITUTIONAL_KEYWORDS = ["SCHOOL", "UNIVERSITY", "FOUNDATION", "ACADEMY", "LTD", "CLUB", "INC", "CORP", "ASSOCIATION", "SOCIETY", "INSTITUTE", "COLLEGE", "ENGINEERS"]

def clean_name(name):
    orig = name
    # 1. Basic normalization
    name = name.strip().replace("&amp;", "&")
    # 2. Strip leading M/s. or Messrs
    name = re.sub(r"^(M/s\.?|Messrs|Kind Attn:?|Consignee)\s*", "", name, flags=re.I).strip()
    # 3. Handle specific noisy cases from Ken's report
    # Strip trailing GSTIN info
    name = re.sub(r"GSTIN:?\s*[0-9A-Z]{15}.*$", "", name, flags=re.I).strip()
    # Strip address chunks appended to names
    name = name.split(" Plot No")[0].split(" 1502,")[0].split(" Tower No")[0].split(" V-37")[0]
    # Clean trailing punctuation
    name = re.sub(r"[,.\s\-–]+$", "", name).strip()
    
    # 4. Filter out purely numeric or too short
    if len(name) < 4 or name.isdigit(): return None
    
    # 5. Check against junk patterns
    for pat in JUNK_REGEX:
        if re.search(pat, name, re.I):
            return None
            
    return name

def finalize_database():
    if not CUSTOMERS_PATH.exists(): return
    
    customers = json.loads(CUSTOMERS_PATH.read_text())
    clean_dict = {}
    
    print(f"Starting scrub of {len(customers)} entries...")
    
    for c in customers:
        raw_name = c["customer"]
        cleaned = clean_name(raw_name)
        
        if not cleaned:
            continue
            
        # Standardize for merging (Upper case keys)
        key = cleaned.upper().replace(" ", "")
        # Remove common variations for better matching
        key = key.replace("PVT", "").replace("LIMITED", "LTD").replace("PVTLTD", "")
        
        if key not in clean_dict:
            c["customer"] = cleaned
            clean_dict[key] = c
        else:
            # Merge purchases if duplicate
            clean_dict[key]["purchases"].extend(c.get("purchases", []))
            # Keep the more detailed address if available
            if not clean_dict[key].get("address") and c.get("address"):
                clean_dict[key]["address"] = c["address"]
            if not clean_dict[key].get("phone") and c.get("phone"):
                clean_dict[key]["phone"] = c["phone"]

    # Final client list
    final_customers = sorted(list(clean_dict.values()), key=lambda x: x["customer"])
    
    # Update master catalog to remove products mapped to deleted customers?
    # No, keep catalog as is, just cleaner client list.
    
    # Save
    CUSTOMERS_PATH.write_text(json.dumps(final_customers, indent=2))
    print(f"Scrub complete. High-fidelity clients: {len(final_customers)}")

if __name__ == "__main__":
    finalize_database()
