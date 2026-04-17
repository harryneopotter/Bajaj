import json
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"

# Storage for separate data
NOISE_CATALOG = ROOT_DIR / "analysis/noise_catalog.json"
NOISE_CUSTOMERS = ROOT_DIR / "analysis/noise_customers.json"

# Keywords that definitely indicate noise/headers
JUNK_KEYWORDS = [
    "BAJAJ & CO", "MUNICIPAL MARKET", "ISO 9001", "GST NO", "UDYAM", "S.NO.", 
    "DESCRIPTION", "PHOTO", "DISCRIPTION", "PRICES", "Rs.", "Sl. No", "Name of Items",
    "Representation photo only", "Why Us?", "Dignity", "Aesthetics", "Kind Regards"
]

def partition_data():
    if not CATALOG_PATH.exists(): return
    
    catalog = json.loads(CATALOG_PATH.read_text())
    customers = json.loads(CUSTOMERS_PATH.read_text())
    
    clean_cat = []
    noise_cat = []
    clean_cust = []
    noise_cust = []
    
    # 1. Filter Catalog
    for p in catalog:
        name = p["product"].upper()
        if any(k in name for k in JUNK_KEYWORDS) or len(name) < 4:
            noise_cat.append(p)
        else:
            clean_cat.append(p)
            
    # 2. Filter Customers
    for c in customers:
        name = c["customer"].upper()
        if any(k in name for k in JUNK_KEYWORDS) or len(name) < 4 or name == "UNKNOWN":
            noise_cust.append(c)
        else:
            clean_cust.append(c)
            
    # Save partitioned data
    CATALOG_PATH.write_text(json.dumps(clean_cat, indent=2))
    CUSTOMERS_PATH.write_text(json.dumps(clean_cust, indent=2))
    NOISE_CATALOG.write_text(json.dumps(noise_cat, indent=2))
    NOISE_CUSTOMERS.write_text(json.dumps(noise_cust, indent=2))
    
    print(f"CLEAN: {len(clean_cust)} clients, {len(clean_cat)} products.")
    print(f"NOISE: {len(noise_cust)} entities, {len(noise_cat)} entries.")

if __name__ == "__main__":
    partition_data()
