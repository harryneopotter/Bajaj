import json
import re
from pathlib import Path
from bs4 import BeautifulSoup

# Paths
SARVAM_DIR = Path("/home/sachin/work/bajaj/extracted/sarvam")
MAPPING_PATH = Path("/home/sachin/work/bajaj/analysis/pdf_client_mapping.json")
CUSTOMERS_PATH = Path("/home/sachin/work/bajaj/analysis/customer_purchases.json")

# High-fidelity Institutional Keywords
GOOD_KEYWORDS = ["SCHOOL", "UNIVERSITY", "FOUNDATION", "ACADEMY", "LTD", "CLUB", "INC", "CORP", "ASSOCIATION", "SOCIETY", "INSTITUTE", "COLLEGE", "CONSTRUCTION"]
# Noise Keywords
JUNK_KEYWORDS = ["MADE OF", "DATE", "SR. MANAGER", "ADMINISTRATIVE", "SUB:", "DEAR SIR", "KIND ATTN", "MUNICIPAL", "BAJAJ", "ISO 9001", "GST NO", "UDYAM", "S.NO.", "REPRESENTATION", "PHONE:", "MOB:", "WWW.", "@", "FAX"]

def clean_client_name(name):
    name = name.strip()
    name_upper = name.upper()
    if len(name) < 5: return "Unknown"
    if any(name.startswith(char) for char in ["(", "0", "1", "2", "3", "4", "5", "6", "7", "8", "9", ".", "-"]): return "Unknown"
    if any(junk in name_upper for junk in JUNK_KEYWORDS): return "Unknown"
    
    if "," in name:
        parts = [p.strip() for p in name.split(",")]
        for p in parts:
            if any(k in p.upper() for k in GOOD_KEYWORDS):
                return re.sub(r"[,.\s]+$", "", p).strip()
        if any(job in parts[0].upper() for job in ["MANAGER", "PRINCIPAL", "WARDEN", "SUPERVISOR", "DIRECTOR", "OFFICER", "ADMIN"]):
            return "Unknown"
    
    if any(job in name_upper for job in ["THE PRINCIPAL", "THE MANAGER", "KIND ATTN"]):
        return "Unknown"

    return re.sub(r"[,.\s\-–]+$", "", name).strip()

def extract_invoice_no(soup):
    # Search for invoice numbers in table cells
    for td in soup.find_all(['td', 'th']):
        text = td.get_text(separator=" ").strip()
        # Look for Invoice No patterns
        m = re.search(r"(?:Invoice No|Inv No|Invoice No\.)[:\s]*([A-Z0-9/-]+)", text, re.I)
        if m:
            return m.group(1).strip()
        # Look for GeM Invoice patterns
        m = re.search(r"GeM Invoice No[:\s]*([A-Z0-9-]+)", text, re.I)
        if m:
            return m.group(1).strip()
    return None

def generate_mapping():
    mapping = {}
    html_files = list(SARVAM_DIR.glob("*.html"))
    
    print(f"Generating audit mapping for {len(html_files)} files...")
    
    for html_path in html_files:
        try:
            content = html_path.read_text(encoding='utf-8')
            soup = BeautifulSoup(content, 'html.parser')
            
            # 1. Extract Client
            client = "Unknown"
            paragraphs = soup.find_all('p', class_='paragraph')
            for p in paragraphs:
                lines = [l.strip() for l in p.get_text(separator="\n").split('\n') if l.strip()]
                found_best = "Unknown"
                for line in lines:
                    cleaned = clean_client_name(line)
                    if cleaned != "Unknown":
                        if any(k in cleaned.upper() for k in GOOD_KEYWORDS):
                            found_best = cleaned
                            break
                        if found_best == "Unknown":
                            found_best = cleaned
                if found_best != "Unknown":
                    client = found_best
                    break
            
            # 2. Extract Invoice No
            inv_no = extract_invoice_no(soup)
            
            # Map
            pdf_name = html_path.name.replace(".html", ".pdf")
            mapping[pdf_name] = {
                "client": client,
                "invoice_no": inv_no
            }
            
        except Exception as e:
            print(f"Error mapping {html_path.name}: {e}")

    MAPPING_PATH.write_text(json.dumps(mapping, indent=2))
    print(f"Audit mapping saved to {MAPPING_PATH}")

if __name__ == "__main__":
    generate_mapping()
