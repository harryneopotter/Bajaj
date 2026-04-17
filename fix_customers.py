import os
import json
import re
from pathlib import Path

TEXT_DIR = Path("/home/sachin/work/bajaj/data/text/2026/01")
OUTPUT_CUSTOMERS = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

def extract_details(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    header_keywords = ["MUNICIPAL MARKET", "INFO@BAJAJSPORTS", "PHONE:", "ISO 9001", "GST NO", "UDYAM", "27, MUNICIPAL"]
    
    header_end_idx = 0
    for i, line in enumerate(lines[:15]):
        if any(k in line.upper() for k in header_keywords):
            header_end_idx = i
            
    potential_lines = lines[header_end_idx+1 : header_end_idx+10]
    date_pattern = r"\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}"
    
    client_name = "Unknown"
    address_lines = []
    phone = ""
    
    found_name = False
    for line in potential_lines:
        if re.search(date_pattern, line, re.I):
            continue
        if any(k in line.upper() for k in ["KIND REGARDS", "DEAR SIR", "QUOTATION", "SUB:", "SPECIFICATIONS", "S.NO.", "ITEM", "DESCRIPTION", "PRICE"]):
            if found_name: break
            continue
        
        if not found_name and len(line) > 3 and re.match(r"^[A-Za-z]", line):
            client_name = re.sub(r"^(To|M/s|Messrs|Kind Attn):?\s*", "", line, flags=re.I).strip()
            if "BAJAJ" in client_name.upper():
                client_name = "Unknown"
                continue
            found_name = True
            continue
            
        if found_name:
            # Check for phone
            phone_match = re.search(r"(?:Mob|Ph|Tel|Cell|Contact)\s*:?\s*([0-9+ -]{10,})", line, re.I)
            if phone_match:
                phone = phone_match.group(1).strip()
            elif len(line) > 5:
                address_lines.append(line)
                
    return client_name, "\n".join(address_lines), phone

def main():
    all_customers = {}
    files = list(TEXT_DIR.glob("*.txt"))
    
    for p in files:
        text = p.read_text(encoding="utf-8", errors="ignore")
        name, addr, ph = extract_details(text)
        
        if name != "Unknown":
            if name not in all_customers:
                all_customers[name] = {
                    "customer": name,
                    "address": addr,
                    "phone": ph,
                    "purchases": []
                }
            else:
                # Update missing details if found in other docs
                if not all_customers[name]["address"] and addr:
                    all_customers[name]["address"] = addr
                if not all_customers[name]["phone"] and ph:
                    all_customers[name]["phone"] = ph

    # Keep existing purchase extraction logic (simplified for this update)
    # ... (omitting full re-extraction of items for brevity since the issue is contact info)
    
    # Load current data to merge
    if OUTPUT_CUSTOMERS.exists():
        existing = json.loads(OUTPUT_CUSTOMERS.read_text())
        for e in existing:
            n = e["customer"]
            if n in all_customers:
                all_customers[n]["purchases"] = e.get("purchases", [])

    OUTPUT_CUSTOMERS.write_text(json.dumps(list(all_customers.values()), indent=2))
    print(f"Updated {len(all_customers)} customers with address/phone info.")

if __name__ == "__main__":
    main()
