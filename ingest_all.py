import os
import fitz
import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
PDF_DIRS = [ROOT_DIR / "data/pdf", ROOT_DIR / "extracted"]
OUTPUT_CATALOG = ROOT_DIR / "analysis/clean_catalog.json"
OUTPUT_CUSTOMERS = ROOT_DIR / "analysis/customer_purchases.json"

# Keywords to identify Bajaj headers vs Clients
BAJAJ_KEYWORDS = ["BAJAJ & CO", "BAJAJ SPORTS", "MUNICIPAL MARKET", "CONNAUGHT CIRCUS", "07AAFPB2487F1ZY", "INFO@BAJAJSPORTS"]

def extract_text_from_pdf(pdf_path):
    try:
        doc = fitz.open(pdf_path)
        text = ""
        for page in doc:
            text += page.get_text("text") + "\n"
        return text
    except Exception as e:
        print(f"Error reading {pdf_path}: {e}")
        return ""

def parse_bajaj_doc_v2(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return None
    
    # 1. Improved Client Identification
    client = "Unknown"
    header_end = 0
    for i, line in enumerate(lines[:15]):
        if any(k in line.upper() for k in BAJAJ_KEYWORDS):
            header_end = i
            
    # Look for the first block that looks like a name/address
    for i in range(header_end + 1, min(header_end + 10, len(lines))):
        line = lines[i]
        if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", line): continue
        if re.search(r"\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line, re.I): continue
        if any(k in line.upper() for k in ["QUOTATION", "INVOICE", "SPECIFICATION", "KIND ATTN", "SUB:", "DEAR", "TO,"]): continue
        
        if len(line) > 3 and not any(k in line.upper() for k in BAJAJ_KEYWORDS):
            client = line
            break

    # 2. Aggressive Item/Price Extraction (v2)
    # Target lines with numbers at the end, handling fragmented layouts
    items = []
    for i, line in enumerate(lines):
        # Ignore obvious Bajaj contact info lines
        if any(k in line.upper() for k in BAJAJ_KEYWORDS) or "@" in line:
            continue
            
        # Pattern: [Description] ... [Price]
        # Price matches: 1,280.00 or 18125 or 15,900.00/-
        match = re.search(r"([A-Za-z0-9 &().+/-]{5,})\s+.*?([0-9,]{2,}(?:\.[0-9]{2})?)(?:/-)?$", line)
        if match:
            desc, price_str = match.groups()
            try:
                price = float(price_str.replace(",", ""))
                if 10 < price < 1000000:
                    items.append({"name": desc.strip(), "price": price})
            except: continue
        else:
            # Fallback for fragmented layout (Price sitting on its own line)
            price_match = re.search(r"^(?:Rs\.?|₹)?\s*([0-9,]{3,}(?:\.[0-9]{2})?)(?:/-)?$", line)
            if price_match:
                try:
                    price = float(price_match.group(1).replace(",", ""))
                    if 10 < price < 1000000:
                        # Look for name in surrounding lines (3 above or 3 below)
                        found_name = None
                        for j in list(range(i-1, i-4, -1)) + list(range(i+1, i+4)):
                            if 0 <= j < len(lines):
                                potential = lines[j]
                                if len(potential) > 5 and not any(k in potential.upper() for k in ["TERMS", "KIND", "BAJAJ", "DATE", "SUB:"]):
                                    found_name = potential
                                    break
                        if found_name:
                            items.append({"name": found_name.strip(), "price": price})
                except: continue

    return {"client": client, "items": items}

def main():
    catalog = {}
    customers = {}
    
    pdf_files = []
    for d in PDF_DIRS:
        if d.exists():
            pdf_files.extend(list(d.rglob("*.pdf")))
            
    print(f"Found {len(pdf_files)} PDFs. Starting Aggressive Ingestion...")
    
    for pdf in pdf_files:
        text = extract_text_from_pdf(pdf)
        data = parse_bajaj_doc_v2(text)
        if data and (data['items'] or data['client'] != "Unknown"):
            client = data['client']
            
            if client not in customers:
                customers[client] = {"customer": client, "purchases": []}
            
            for item in data['items']:
                customers[client]["purchases"].append({"product": item['name'], "price": item['price']})
                
                pname = item['name']
                if pname not in catalog:
                    catalog[pname] = {"product": pname, "pricing_tiers": [], "min_price": 999999, "max_price": 0, "times_quoted": 0}
                
                cat = catalog[pname]
                cat["times_quoted"] += 1
                cat["min_price"] = min(cat["min_price"], item['price'])
                cat["max_price"] = max(cat["max_price"], item['price'])
                
                found_tier = False
                for t in cat["pricing_tiers"]:
                    if t["price"] == item['price']:
                        if client not in t["customers"]: t["customers"].append(client)
                        t["count"] += 1
                        found_tier = True
                        break
                if not found_tier:
                    cat["pricing_tiers"].append({"price": item['price'], "customers": [client], "count": 1})

    # Save all raw findings
    with open(OUTPUT_CATALOG, "w") as f:
        json.dump(list(catalog.values()), f, indent=2)
    with open(OUTPUT_CUSTOMERS, "w") as f:
        json.dump(list(customers.values()), f, indent=2)
        
    print(f"Ingestion Complete. Found {len(customers)} unique clients/entities and {len(catalog)} products.")

if __name__ == "__main__":
    main()
