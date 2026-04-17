import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"

# High-fidelity Institutional Keywords
GOOD_KEYWORDS = ["SCHOOL", "UNIVERSITY", "FOUNDATION", "ACADEMY", "LTD", "CLUB", "INC", "CORP", "ASSOCIATION", "SOCIETY", "INSTITUTE", "COLLEGE", "CONSTRUCTION"]
# Noise Keywords
JUNK_KEYWORDS = ["MADE OF", "DATE", "SR. MANAGER", "ADMINISTRATIVE", "SUB:", "DEAR SIR", "KIND ATTN", "MUNICIPAL", "BAJAJ", "ISO 9001", "GST NO", "UDYAM", "S.NO.", "REPRESENTATION", "PHONE:", "MOB:", "WWW.", "@", "FAX"]

def super_scrub():
    if not CUSTOMERS_PATH.exists(): return
    
    customers = json.loads(CUSTOMERS_PATH.read_text())
    catalog = json.loads(CATALOG_PATH.read_text())
    
    clean_customers = []
    
    for c in customers:
        name = c["customer"].strip()
        name_upper = name.upper()
        
        # 1. Basic Junk Filter
        if len(name) < 5: continue
        if any(name.startswith(char) for char in ["(", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "-"]): continue
        if any(junk in name_upper for junk in JUNK_KEYWORDS): continue
        
        # 2. Intelligent Renaming (Job Title to Institution)
        # Often: "The Principal, ABC School" -> We want "ABC School"
        if "," in name:
            parts = [p.strip() for p in name.split(",")]
            found_inst = False
            for p in parts:
                if any(k in p.upper() for k in GOOD_KEYWORDS):
                    c["customer"] = p
                    found_inst = True
                    break
            # If no part matches institutional keywords, keep the first part but only if not job title
            if not found_inst:
                if any(job in parts[0].upper() for job in ["MANAGER", "PRINCIPAL", "WARDEN", "SUPERVISOR"]):
                    continue # Drop it, it's just a job title fragment
        
        # 3. Clean up the final name (trailing commas, periods)
        c["customer"] = re.sub(r"[,.\s]+$", "", c["customer"]).strip()
        
        # 4. Final filter: Must have at least one GOOD keyword OR be a multi-word proper name
        if any(k in c["customer"].upper() for k in GOOD_KEYWORDS) or " " in c["customer"]:
            clean_customers.append(c)

    # 5. Deduplicate
    final_list = {}
    for c in clean_customers:
        name = c["customer"]
        if name not in final_list or (not final_list[name].get("address") and c.get("address")):
            final_list[name] = c
            
    sorted_customers = sorted(list(final_list.values()), key=lambda x: x["customer"])
    
    # Save
    CUSTOMERS_PATH.write_text(json.dumps(sorted_customers, indent=2))
    print(f"Super Scrub complete: {len(sorted_customers)} high-fidelity clients remaining.")

if __name__ == "__main__":
    super_scrub()
