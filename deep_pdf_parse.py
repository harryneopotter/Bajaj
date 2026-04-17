import os
import fitz
import json
import re
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
PDF_DIRS = [ROOT_DIR / "data/pdf", ROOT_DIR / "extracted"] # Checking common spots
OUTPUT_CATALOG = ROOT_DIR / "analysis/clean_catalog.json"
OUTPUT_CUSTOMERS = ROOT_DIR / "analysis/customer_purchases.json"

# Keywords to identify Bajaj headers vs Clients
BAJAJ_KEYWORDS = ["BAJAJ & CO", "BAJAJ SPORTS", "MUNICIPAL MARKET", "CONNAUGHT CIRCUS", "07AAFPB2487F1ZY"]

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

def parse_bajaj_doc(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if not lines: return None
    
    # 1. Identify Client
    client = "Unknown"
    # Logic: Skip the Bajaj header block, look for the first address-like block
    header_end = 0
    for i, line in enumerate(lines[:15]):
        if any(k in line.upper() for k in BAJAJ_KEYWORDS):
            header_end = i
            
    # Client is usually after the date line
    for i in range(header_end + 1, min(header_end + 10, len(lines))):
        line = lines[i]
        # Skip dates, specific doc titles
        if re.search(r"\d{1,2}[-/]\d{1,2}[-/]\d{2,4}", line): continue
        if re.search(r"\d{1,2}\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)", line, re.I): continue
        if any(k in line.upper() for k in ["QUOTATION", "INVOICE", "SPECIFICATION", "KIND ATTN", "SUB:", "DEAR"]): continue
        
        if len(line) > 3:
            client = line
            break

    # 2. Extract Items & Prices
    items = []
    # Pattern for items: Description ... Qty? ... Rate ... Total?
    # Usually matches something like "Cricket Bat  10  500.00  5000.00" 
    # or just "Item Name   1200"
    for line in lines:
        # Looking for a description followed by a price-like number at the end
        match = re.search(r"([A-Za-z0-9 &().+/-]{5,})\s+.*?(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)$", line)
        if match:
            desc, price_str = match.groups()
            # Clean price
            try:
                price = float(price_str.replace(",", ""))
                if price > 50 and price < 500000: # Filter noise
                    items.append({"name": desc.strip(), "price": price})
            except: continue
            
    return {"client": client, "items": items}

def main():
    catalog = {}
    customers = {}
    
    pdf_files = []
    for d in PDF_DIRS:
        if d.exists():
            pdf_files.extend(list(d.rglob("*.pdf")))
            
    print(f"Found {len(pdf_files)} PDFs. Starting Deep Parse...")
    
    processed_count = 0
    for pdf in pdf_files:
        text = extract_text_from_pdf(pdf)
        data = parse_bajaj_doc(text)
        if data and data['items']:
            processed_count += 1
            client = data['client']
            
            # Update Customers
            if client not in customers:
                customers[client] = {"customer": client, "purchases": []}
            
            for item in data['items']:
                customers[client]["purchases"].append({"product": item['name'], "price": item['price']})
                
                # Update Catalog
                pname = item['name']
                if pname not in catalog:
                    catalog[pname] = {"product": pname, "pricing_tiers": [], "min_price": 999999, "max_price": 0, "times_quoted": 0}
                
                cat = catalog[pname]
                cat["times_quoted"] += 1
                cat["min_price"] = min(cat["min_price"], item['price'])
                cat["max_price"] = max(cat["max_price"], item['price'])
                
                # Simple pricing tier logic
                found_tier = False
                for t in cat["pricing_tiers"]:
                    if t["price"] == item['price']:
                        if client not in t["customers"]: t["customers"].append(client)
                        t["count"] += 1
                        found_tier = True
                        break
                if not found_tier:
                    cat["pricing_tiers"].append({"price": item['price'], "customers": [client], "count": 1})

    # Save
    with open(OUTPUT_CATALOG, "w") as f:
        json.dump(list(catalog.values()), f, indent=2)
    with open(OUTPUT_CUSTOMERS, "w") as f:
        json.dump(list(customers.values()), f, indent=2)
        
    print(f"Deep Parse Complete. Processed {processed_count} relevant documents.")
    print(f"Extracted {len(customers)} unique clients and {len(catalog)} unique products.")

if __name__ == "__main__":
    main()
