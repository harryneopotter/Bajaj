import json
import re
from pathlib import Path

# The file Ken just sent
INPUT_TEXT = Path("/home/sachin/.openclaw/media/inbound/file_4---eb9c0e1f-e834-49a9-adbb-4b2644681f7c.txt")
CATALOG_PATH = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def parse_high_fidelity_text(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    client = "Unknown"
    items = []
    
    # 1. Identify Client
    for i, line in enumerate(lines[:30]):
        if any(k in line for k in ["School", "Foundation", "University", "Academy", "Ltd."]):
            if "BAJAJ" not in line.upper():
                client = line
                break

    # 2. Stateful Extraction for vertical text
    # Looking for sequence: [Index] -> [Name] -> [Brand] -> [Price] -> [GST]
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Look for standard table index
        if re.match(r"^\d+$", line):
            idx = int(line)
            # Standard tables usually have 5-6 columns following
            # We look for a price pattern in the next 5 lines
            found_price = False
            for j in range(i+1, min(i+10, len(lines))):
                price_match = re.search(r"^([0-9,]{2,}\.[0-9]{2})$", lines[j])
                if price_match:
                    price = float(price_match.group(1).replace(",", ""))
                    # The name is usually the line immediately after index
                    name = lines[i+1]
                    # If i+2 is not the price, it might be the Brand
                    if i+2 != j:
                        name = f"{name} ({lines[i+2]})"
                    items.append({"name": name, "price": price})
                    print(f"DEBUG Table Match: {name} @ {price}")
                    i = j # Move to the price line
                    found_price = True
                    break
            if found_price:
                i += 1
                continue

        # B. Block Layout Header -> Price -> Detail
        if "Rs." in line and "/-" in line:
            price_match = re.search(r"Rs\.?\s*([0-9,]{3,}(?:\.[0-9]{2})?)", line)
            if price_match:
                price = float(price_match.group(1).replace(",", ""))
                # Product name is often the line BEFORE or AFTER
                # In vertical mode, let's look for non-specs
                found_name = None
                for offset in [-1, 1, -2, 2]:
                    if 0 <= i + offset < len(lines):
                        cand = lines[i+offset]
                        if len(cand) > 5 and not any(k in cand.upper() for k in ["BAJAJ", "DATE", "Rs.", "GST", "TERM"]):
                            found_name = cand
                            break
                if found_name:
                    items.append({"name": found_name, "price": price})
                    print(f"DEBUG Block Match: {found_name} @ {price}")

        i += 1

    return client, items

    return client, items

def update_production_data(client, items):
    if not items: return
    
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
        
        found = False
        for t in cat["pricing_tiers"]:
            if t["price"] == item['price']:
                if client not in t["customers"]: t["customers"].append(client)
                t["count"] += 1
                found = True
                break
        if not found:
            cat["pricing_tiers"].append({"price": item['price'], "customers": [client], "count": 1})

    CATALOG_PATH.write_text(json.dumps(list(catalog.values()), indent=2))
    CUSTOMERS_PATH.write_text(json.dumps(list(customers.values()), indent=2))

if __name__ == "__main__":
    text = INPUT_TEXT.read_text()
    client, items = parse_high_fidelity_text(text)
    if items:
        update_production_data(client, items)
        print(f"Refined Parse: {len(items)} items found for {client}.")
