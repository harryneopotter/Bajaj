import csv
import json
import re
from pathlib import Path

CSV_PATH = Path("/home/sachin/.openclaw/media/inbound/file_3---e83ccca2-6080-4af8-8199-a1f3bef7dbdc.csv")
CATALOG_PATH = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def parse_ocr_csv(csv_path):
    items = []
    client = "Unknown"
    
    with open(csv_path, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        # Skip header
        next(reader)
        
        lines = []
        for row in reader:
            if not row or len(row) < 3: continue
            text = row[2].strip().replace("'", "")
            if text:
                lines.append(text)
                
    # 1. Extract Client (usually after date or Bajaj info)
    for i, line in enumerate(lines[:20]):
        if "The Shri Ram School" in line or "Pathway School" in line:
            client = line
            break
            
    # 2. Extract Items
    # Look for standard table rows first
    # Row pattern: [Index] [Name] [Brand] [Price] [GST] [Unit]
    for i, line in enumerate(lines):
        # Match standard line with price
        # e.g. "Nelco Training Plyometric" or "1,280.00"
        price_match = re.search(r"([0-9,]{2,}(?:\.[0-9]{2})?)(?:/-)?$", line)
        if price_match:
            price = float(price_match.group(1).replace(",", ""))
            if 10 < price < 1000000:
                # Look back for name
                name = lines[i-1] if i > 0 else "Unknown Item"
                # Check if i-2 was a name and i-1 was a brand
                if i > 1 and len(lines[i-2]) > 3 and len(lines[i-1]) > 3:
                    name = f"{lines[i-2]} ({lines[i-1]})"
                
                # Special case: T.T. Tables (Block Layout)
                # "T.T. Table - STAG" -> "Rs.18,125/- each" -> "Stag Action"
                if "Rs." in lines[i-1] or "/-" in lines[i-1]:
                    # This line is the price, check if previous was item and next is detail
                    # Wait, the OCR flow for block items is: Header -> Price -> Item Name
                    pass 

    # Re-using the more robust ingest logic from ingest_all.py but adapted for this linear CSV
    current_items = []
    for i, line in enumerate(lines):
        # Simple extraction for this high-quality CSV
        m = re.search(r"([0-9,]{2,}\.[0-9]{2})", line)
        if m:
            price = float(m.group(1).replace(",", ""))
            # Search upwards for the item name (skip short noise)
            name = "Unknown"
            for j in range(i-1, i-5, -1):
                if j >= 0 and len(lines[j]) > 5 and not any(k in lines[j].upper() for k in ["GST", "RATE", "UNIT", "SI.", "NO."]):
                    name = lines[j]
                    break
            if name != "Unknown":
                current_items.append({"name": name, "price": price})

    return client, current_items

def update_db(client, items):
    # Load
    catalog = {p["product"]: p for p in json.loads(CATALOG_PATH.read_text())}
    customers = {c["customer"]: c for c in json.loads(CUSTOMERS_PATH.read_text())}
    
    if client not in customers:
        customers[client] = {"customer": client, "purchases": []}
    
    for item in items:
        customers[client]["purchases"].append({"product": item["name"], "price": item["price"]})
        
        pname = item["name"]
        if pname not in catalog:
            catalog[pname] = {"product": pname, "pricing_tiers": [], "min_price": 999999, "max_price": 0, "times_quoted": 0}
        
        cat = catalog[pname]
        cat["times_quoted"] += 1
        cat["min_price"] = min(cat["min_price"], item['price'])
        cat["max_price"] = max(cat["max_price"], item['price'])
        
        # Tiers
        found = False
        for t in cat["pricing_tiers"]:
            if t["price"] == item['price']:
                if client not in t["customers"]: t["customers"].append(client)
                t["count"] += 1
                found = True
                break
        if not found:
            cat["pricing_tiers"].append({"price": item['price'], "customers": [client], "count": 1})

    # Save
    CATALOG_PATH.write_text(json.dumps(list(catalog.values()), indent=2))
    CUSTOMERS_PATH.write_text(json.dumps(list(customers.values()), indent=2))

if __name__ == "__main__":
    client, items = parse_ocr_csv(CSV_PATH)
    if items:
        update_db(client, items)
        print(f"Parsed {len(items)} items for {client} from high-fidelity CSV.")
