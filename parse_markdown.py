import json
import re
from pathlib import Path

# Paths
MD_FILES = list(Path("/home/sachin/work/bajaj/extracted/mistral/").glob("*.md"))
CATALOG_PATH = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def parse_mistral_markdown(path):
    text = path.read_text(encoding='utf-8')
    client = "Unknown"
    items = []
    
    # 1. Identify Client
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    for i, line in enumerate(lines[:30]):
        if any(k in line for k in ["School", "Foundation", "University", "Academy", "Ltd."]):
            if "BAJAJ" not in line.upper():
                client = line.replace("#", "").strip()
                break

    # 2. Table Parsing
    rows = re.findall(r"\|([^|]+)\|([^|]+)(?:\|([^|]*)\|)?", text, re.MULTILINE | re.DOTALL)
    
    for row in rows:
        cols = [c.strip() for c in row if c]
        if not cols or any(k in cols[0].upper() for k in ["SL. NO", "DISCRIPTION", "---"]):
            continue
            
        for c in reversed(cols):
            price_match = re.search(r"(?:Rs\.?|₹)?\s*([0-9,]{2,}(?:\.[0-9]{2})?)(?:/-)?", c)
            if price_match:
                try:
                    price = float(price_match.group(1).replace(",", ""))
                    if 10 < price < 1000000:
                        name_raw = cols[0]
                        bold_match = re.search(r"\*\*(.+?)\*\*", name_raw)
                        name = bold_match.group(1) if bold_match else name_raw.splitlines()[0]
                        items.append({"name": name.strip(), "price": price})
                        break
                except: continue
        
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
    for md_path in MD_FILES:
        client, items = parse_mistral_markdown(md_path)
        if items:
            update_production_data(client, items)
            print(f"Mistral Ingest: {len(items)} items found for {client}.")
