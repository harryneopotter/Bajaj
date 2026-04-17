import json
import re
from pathlib import Path

# Paths
JSON_PATH = Path("/home/sachin/.openclaw/media/inbound/file_5---39790d60-9159-40a6-b55d-914fcbd601e1.json")
CATALOG_PATH = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def parse_textract_json(path):
    with open(path, 'r') as f:
        data = json.load(f)
    
    blocks = data.get("Blocks", [])
    lines = [b for b in blocks if b["BlockType"] == "LINE"]
    
    # Sort lines by vertical position (Top), then horizontal (Left)
    # Using a small tolerance for "same line" detection
    lines.sort(key=lambda b: (b["Geometry"]["BoundingBox"]["Top"], b["Geometry"]["BoundingBox"]["Left"]))
    
    # Group lines into rows based on Y-coordinate tolerance
    rows = []
    if not lines: return "Unknown", []
    
    current_row = [lines[0]]
    last_top = lines[0]["Geometry"]["BoundingBox"]["Top"]
    
    for i in range(1, len(lines)):
        top = lines[i]["Geometry"]["BoundingBox"]["Top"]
        if abs(top - last_top) < 0.005: # Tolerance for same line
            current_row.append(lines[i])
        else:
            # Sort current row by Left coordinate
            current_row.sort(key=lambda b: b["Geometry"]["BoundingBox"]["Left"])
            rows.append(current_row)
            current_row = [lines[i]]
            last_top = top
    rows.append(current_row)

    client = "Unknown"
    items = []
    
    # 1. Identify Client (search first 20 rows)
    for row in rows[:30]:
        text = " ".join([b["Text"] for b in row])
        if any(k in text for k in ["School", "Foundation", "University", "Academy", "Ltd."]):
            if "BAJAJ" not in text.upper():
                client = text
                break

    # 2. Extract Items from grouped rows
    for row in rows:
        row_text = " ".join([b["Text"] for b in row])
        
        # Pattern A: Standard Table Row (e.g. "1 Hurdle Nelco ... 1,280.00 18% Each")
        # Textract JSON grouped lines usually put columns in order
        m = re.search(r"(\d+)\s+(.+?)\s+([0-9,]{2,}\.[0-9]{2})\s+(\d+%)\s+(.+)$", row_text)
        if m:
            _, desc, price_str, _, _ = m.groups()
            items.append({"name": desc.strip(), "price": float(price_str.replace(",", ""))})
            continue
            
        # Pattern B: Block items where price is sitting alone in a row (typical for Bajaj T.T. tables)
        # e.g. Row: "Rs.18,125/- each"
        if "Rs." in row_text and "/-" in row_text:
            pm = re.search(r"([0-9,]{3,}(?:\.[0-9]{2})?)", row_text)
            if pm:
                price = float(pm.group(1).replace(",", ""))
                # Find the product name - usually the row ABOVE or BELOW that isn't specs
                # In this specific quote, "Stag Action" is the row BELOW "T.T. Table - STAG Rs.18,125/-"
                # Wait, looking at Ken's text file, it's:
                # T.T. Table - STAG
                # Rs.18,125/- each
                # Stag Action
                # [Specs...]
                idx = rows.index(row)
                candidates = []
                if idx > 0: candidates.append(" ".join([b["Text"] for b in rows[idx-1]]))
                if idx < len(rows) - 1: candidates.append(" ".join([b["Text"] for b in rows[idx+1]]))
                
                for cand in candidates:
                    if len(cand) > 5 and not any(k in cand.upper() for k in ["BAJAJ", "DATE", "Rs.", "GST", "TERM"]):
                        items.append({"name": cand, "price": price})
                        break

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
    client, items = parse_textract_json(JSON_PATH)
    if items:
        update_production_data(client, items)
        print(f"Textract JSON Parse: {len(items)} items found for {client}.")
