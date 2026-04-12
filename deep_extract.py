import os
import json
import re
from pathlib import Path

TEXT_DIR = Path("/home/sachin/work/bajaj/data/text/2026/01")
OUTPUT_CUSTOMERS = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")
OUTPUT_CATALOG = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")

def extract_client(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_keywords = ["MUNICIPAL MARKET", "INFO@BAJAJSPORTS", "PHONE:", "ISO 9001", "GST NO", "UDYAM", "27, MUNICIPAL"]
    
    # Find where the header ends
    header_end_idx = 0
    for i, line in enumerate(lines[:15]): # Header is usually in first 15 lines
        if any(k in line.upper() for k in header_keywords):
            header_end_idx = i
            
    # The client is usually right after the header/date
    # Look at the next few lines for something that looks like an address/name
    potential_lines = lines[header_end_idx+1 : header_end_idx+6]
    
    # Skip standalone dates
    date_pattern = r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}"
    
    for line in potential_lines:
        if re.search(date_pattern, line, re.I):
            continue
        # If it's a known non-client line, skip
        if any(k in line.upper() for k in ["KIND REGARDS", "DEAR SIR", "QUOTATION", "SUB:", "SPECIFICATIONS", "S.NO.", "ITEM", "DESCRIPTION", "PRICE"]):
            continue
        
        # Valid name check: starts with letter, not too long, not all caps header
        if len(line) > 3 and re.match(r"^[A-Za-z]", line):
            # Clean up leading M/s or To
            name = re.sub(r"^(To|M/s|Messrs|Kind Attn):?\s*", "", line, flags=re.I).strip()
            if "BAJAJ" not in name.upper():
                return name
    return "Unknown"

def extract_items(text):
    items = []
    # Look for lines with currency patterns: Item Name ... Price
    # Matches patterns like: Cricket Bat Rs. 500 or Football 1500.00
    lines = text.splitlines()
    for line in lines:
        # Avoid header/footer noise
        if any(x in line.upper() for x in ["PHONE", "EMAIL", "WWW.", "MARKET", "ESTD"]):
            continue
            
        m = re.search(r"([A-Za-z0-9 &()_-]{5,})\s+(?:Rs\.?|₹)?\s*([0-9,]{3,}(?:\.[0-9]{2})?)", line)
        if m:
            name, price = m.groups()
            try:
                price_f = float(price.replace(",", ""))
                if price_f > 10: # filter noise
                    items.append({"name": name.strip(), "price": price_f})
            except:
                continue
    return items

def main():
    all_customers = {}
    all_products = {}
    
    files = list(TEXT_DIR.glob("*.txt"))
    print(f"Processing {len(files)} files...")
    
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        client = extract_client(text)
        items = extract_items(text)
        
        if client != "Unknown":
            if client not in all_customers:
                all_customers[client] = {"customer": client, "purchases": []}
            
            for item in items:
                all_customers[client]["purchases"].append({
                    "product": item["name"],
                    "price": item["price"],
                    "date": "2026-01-01" # Placeholder or extract date
                })
                
                prod_name = item["name"]
                if prod_name not in all_products:
                    all_products[prod_name] = {
                        "product": prod_name,
                        "pricing_tiers": [],
                        "min_price": float('inf'),
                        "max_price": 0,
                        "times_quoted": 0
                    }
                
                prod = all_products[prod_name]
                prod["times_quoted"] += 1
                prod["min_price"] = min(prod["min_price"], item["price"])
                prod["max_price"] = max(prod["max_price"], item["price"])
                
                # Update pricing tiers
                found_tier = False
                for tier in prod["pricing_tiers"]:
                    if tier["price"] == item["price"]:
                        if client not in tier["customers"]:
                            tier["customers"].append(client)
                        tier["count"] += 1
                        found_tier = True
                        break
                if not found_tier:
                    prod["pricing_tiers"].append({
                        "price": item["price"],
                        "customers": [client],
                        "count": 1
                    })

    # Finalize and Save
    cust_list = list(all_customers.values())
    prod_list = [p for p in all_products.values() if p["times_quoted"] > 0]
    # Clean up inf prices
    for p in prod_list:
        if p["min_price"] == float('inf'): p["min_price"] = 0

    OUTPUT_CUSTOMERS.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_CUSTOMERS.write_text(json.dumps(cust_list, indent=2))
    OUTPUT_CATALOG.write_text(json.dumps(prod_list, indent=2))
    
    print(f"Done. Found {len(cust_list)} customers and {len(prod_list)} products.")

if __name__ == "__main__":
    main()
