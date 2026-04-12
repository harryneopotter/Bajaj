import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

# Path to the sarvam extracted folder
SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
CATALOG_PATH = Path("/home/sachin/work/bajaj/analysis/clean_catalog.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def parse_html_quote(path):
    content = path.read_text(encoding='utf-8')
    soup = BeautifulSoup(content, 'html.parser')
    
    client = "Unknown"
    address = ""
    phone = ""
    date = "2026-01-01" # Default placeholder
    items = []
    
    # 1. Identify Date (usually in a paragraph)
    for p in soup.find_all('p', class_='paragraph'):
        dm = re.search(r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", p.get_text(), re.I)
        if dm:
            # Simple normalization to YYYY-MM-DD (roughly)
            day, month, year = dm.groups()
            date = f"{year}-{month}-{day}"
            break

    # 2. Identify Client, Address, Phone
    paragraphs = soup.find_all('p', class_='paragraph')
    for p in paragraphs:
        text_content = p.get_text(separator="\n").strip()
        lines = [l.strip() for l in text_content.split('\n') if l.strip()]
        if not lines: continue
        
        cand_client = "Unknown"
        cand_address = ""
        
        # If the first line is a date, skip it
        if re.search(r"\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}", lines[0]):
            if len(lines) > 1:
                cand_client = lines[1]
                cand_address = "\n".join(lines[2:])
        else:
            cand_client = lines[0]
            cand_address = "\n".join(lines[1:])
            
        # Basic validation: If it contains Bajaj, it's not the client
        if "BAJAJ" in cand_client.upper() or len(cand_client) < 3:
            continue
            
        # Clean the client name
        client = re.sub(r"^(To|M/s|Messrs|Kind Attn):?\s*", "", cand_client, flags=re.I).strip()
        address = cand_address.strip()
        
        # Check for phone
        phone_match = re.search(r"(?:Mob|Ph|Tel|Cell|Contact)\s*:?\s*([0-9+ -]{10,})", text_content, re.I)
        if phone_match:
            phone = phone_match.group(1).strip()
        
        if client != "Unknown":
            break

    # 3. Table Parsing
    tables = soup.find_all('table')
    for table in tables:
        rows = table.find_all('tr')
        for row in rows:
            cols = row.find_all(['td', 'th'])
            if not cols: continue
            
            col_texts = [c.get_text(separator=" ").strip() for c in cols]
            
            if len(col_texts) >= 4:
                for idx in [3, 2, 4]:
                    if idx < len(col_texts):
                        price_match = re.search(r"([0-9,]{2,}\.[0-9]{2})", col_texts[idx])
                        if price_match:
                            try:
                                price = float(price_match.group(1).replace(",", ""))
                                name = col_texts[1]
                                if idx == 3 and len(col_texts) > 2 and len(col_texts[2]) > 3:
                                    name = f"{name} ({col_texts[2]})"
                                items.append({"name": name.strip(), "price": price})
                                break
                            except: continue
            
            elif len(col_texts) == 2:
                pm = re.search(r"(?:Rs\.?|₹)?\s*([0-9,]{3,}(?:\.[0-9]{2})?)(?:/-)?", col_texts[1])
                if pm:
                    try:
                        price = float(pm.group(1).replace(",", ""))
                        name_raw = col_texts[0].strip()
                        if not name_raw: continue
                        name = name_raw.splitlines()[0].strip()
                        items.append({"name": name, "price": price})
                    except: continue

    return client, address, phone, date, items

def update_production_data(client, address, phone, date, items):
    if not items or client == "Unknown": return
    
    # Load
    catalog = {}
    if CATALOG_PATH.exists() and CATALOG_PATH.stat().st_size > 0:
        try:
            catalog = {p["product"]: p for p in json.loads(CATALOG_PATH.read_text())}
        except: pass
        
    customers = {}
    if CUSTOMERS_PATH.exists() and CUSTOMERS_PATH.stat().st_size > 0:
        try:
            customers = {c["customer"]: c for c in json.loads(CUSTOMERS_PATH.read_text())}
        except: pass
    
    # Update Customer
    if client not in customers:
        customers[client] = {"customer": client, "address": address, "phone": phone, "purchases": []}
    else:
        # Merge/Update address/phone if missing
        if not customers[client].get("address") and address:
            customers[client]["address"] = address
        if not customers[client].get("phone") and phone:
            customers[client]["phone"] = phone
    
    for item in items:
        # Add to customer history with extracted date
        customers[client]["purchases"].append({"product": item["name"], "price": item["price"], "date": date})
        
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

    # Save
    CATALOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CATALOG_PATH.write_text(json.dumps(list(catalog.values()), indent=2))
    CUSTOMERS_PATH.write_text(json.dumps(list(customers.values()), indent=2))

if __name__ == "__main__":
    html_files = list(SARVAM_DIR.glob("*.html"))
    for html_path in html_files:
        try:
            client, address, phone, date, items = parse_html_quote(html_path)
            if items:
                update_production_data(client, address, phone, date, items)
        except Exception as e:
            print(f"Error on {html_path.name}: {e}")
    print("Ingestion complete.")
