import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"

def deep_clean():
    if not CATALOG_PATH.exists(): return
    
    catalog = json.loads(CATALOG_PATH.read_text())
    customers = json.loads(CUSTOMERS_PATH.read_text())
    
    # 1. Cleaning the master catalog
    cleaned_catalog = []
    removed_products = set()
    
    for p in catalog:
        name = p["product"].upper()
        # Price validation
        min_p = p["min_price"]
        max_p = p["max_price"]
        
        # Skip if price looks like a year
        if 2000 <= min_p <= 2030: continue
        # Skip if price looks like a pincode (Delhi/NCR)
        if 110000 <= min_p <= 110999: continue
        if 122000 <= min_p <= 122999: continue
        if 201000 <= min_p <= 201999: continue
        
        # Skip if name contains junk
        if any(k in name for k in ["DATE", "EXPIRY", "PHONE", "MOB:", "INVOICE", "SL. NO", "GST", "UDYAM", "CERTIFICATE"]):
            removed_products.add(p["product"])
            continue
            
        cleaned_catalog.append(p)
        
    # 2. Cleaning customer history
    cleaned_customers = []
    for c in customers:
        new_purchases = []
        for pur in c.get("purchases", []):
            pname = pur["product"].upper()
            price = pur["price"]
            
            # Use same validation logic
            if 2000 <= price <= 2030: continue
            if 110000 <= price <= 110999 or 122000 <= price <= 122999 or 201000 <= price <= 201999: continue
            if any(k in pname for k in ["DATE", "EXPIRY", "PHONE", "MOB:", "INVOICE", "SL. NO", "GST", "UDYAM", "CERTIFICATE"]):
                continue
            
            new_purchases.append(pur)
        
        c["purchases"] = new_purchases
        if len(c["customer"]) > 3: # Final name check
            cleaned_customers.append(c)

    # Save
    CATALOG_PATH.write_text(json.dumps(cleaned_catalog, indent=2))
    CUSTOMERS_PATH.write_text(json.dumps(cleaned_customers, indent=2))
    
    print(f"Deep Clean: {len(cleaned_catalog)} products, {len(cleaned_customers)} clients.")

if __name__ == "__main__":
    deep_clean()
