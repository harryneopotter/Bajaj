#!/usr/bin/env python3
"""
Parse extracted PDF text to build:
1. Product catalog with all pricing tiers
2. Customer list with purchase history
"""

import os
import re
import json
from pathlib import Path
from collections import defaultdict

EXTRACTED_DIR = Path("/home/sachin/work/bajaj/extracted")
OUTPUT_DIR = Path("/home/sachin/work/bajaj/analysis")
OUTPUT_DIR.mkdir(exist_ok=True)

# Patterns for extraction
PRICE_PATTERN = r'Rs\.?\s*([\d,]+(?:\.\d{2})?)'
PRICE_PATTERN_ALT = r'([\d,]+(?:\.\d{2})?)\s*[-/]?\s*(?:Rs|INR|\u20b9)'
GST_PATTERN = r'(\d{1,2})\s*%\s*(?:GST|gst)'

def extract_customer_info(text):
    """Extract customer name and details from quotation."""
    lines = text.split('\n')
    customer = {
        "name": None,
        "address": [],
        "contact": None,
        "email": None
    }
    
    # Look for "To" section or "Kind Attn"
    in_to_section = False
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Customer name after "To" or "Kind Atten/Attn"
        if re.search(r'\bTo\b', line_stripped) and not re.search(r'Total|Total\s+Amount', line_stripped, re.I):
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 3 and not next_line.startswith('Date'):
                    customer["name"] = next_line
                    in_to_section = True
                    continue
        
        if re.search(r'Kind\s*Atten', line_stripped, re.I):
            # Sometimes customer name follows Kind Attn
            match = re.search(r'Kind\s*Atten\.?\s*:?\s*(.*?)(?:\s+Mob|$)', line_stripped, re.I)
            if match:
                contact_person = match.group(1).strip()
                # Actual customer usually comes before this
                if i > 0:
                    prev_lines = [lines[j].strip() for j in range(max(0, i-3), i)]
                    for pl in reversed(prev_lines):
                        if pl and len(pl) > 3 and 'Bajaj' not in pl and 'QUOTATION' not in pl:
                            if not customer["name"]:
                                customer["name"] = pl
                            break
        
        # Extract phone numbers
        phone_match = re.search(r'(?:Mob\.?|Phone|Tel\.?)\s*:?\s*([\d\s\-+/]+)', line_stripped, re.I)
        if phone_match:
            customer["contact"] = phone_match.group(1).strip()
        
        # Extract email
        email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', line_stripped)
        if email_match and 'bajajsports.com' not in email_match.group(0):
            customer["email"] = email_match.group(0)
    
    return customer

def extract_products_and_prices(text):
    """Extract products with prices from quotation text."""
    products = []
    lines = text.split('\n')
    
    current_category = None
    
    for i, line in enumerate(lines):
        line_stripped = line.strip()
        
        # Detect category headers (usually all caps or followed by many spaces/dots)
        if re.match(r'^[A-Za-z\s]+(?:Ball|Sports|Equipment|Game)', line_stripped) and len(line_stripped) < 50:
            if '...' in text.split('\n')[min(i+1, len(lines)-1)] or i == 0 or lines[i-1].strip() == '':
                current_category = line_stripped
                continue
        
        # Look for lines with prices
        price_matches = re.findall(PRICE_PATTERN, line_stripped)
        if not price_matches:
            price_matches = re.findall(PRICE_PATTERN_ALT, line_stripped)
        
        if price_matches:
            price_str = price_matches[0].replace(',', '')
            try:
                price = float(price_str)
            except:
                continue
            
            # Extract GST if present
            gst_match = re.search(GST_PATTERN, line_stripped)
            gst = int(gst_match.group(1)) if gst_match else None
            
            # Look for product name in this line and surrounding lines
            product_name = None
            
            # Try current line first (remove price part)
            clean_line = re.sub(r'Rs\.?\s*[\d,]+(?:\.\d{2})?', '', line_stripped)
            clean_line = re.sub(r'\d{1,2}\s*%\s*(?:GST|gst)', '', clean_line, flags=re.I)
            clean_line = re.sub(r'\bEach\b|\bSet\b|\bPair\b|\bPer\s+\w+', '', clean_line, flags=re.I).strip()
            
            if len(clean_line) > 3 and not clean_line.isdigit():
                product_name = clean_line
            
            # If no good name found, look at previous lines
            if not product_name or len(product_name) < 5:
                for j in range(i-1, max(0, i-4), -1):
                    prev = lines[j].strip()
                    if prev and len(prev) > 3 and not re.search(r'\d{4,}', prev):
                        if not re.match(r'^(Sl\.|No\.|Name|Brand|Rate|GST|Unit|\d+\.?\s*$)', prev, re.I):
                            product_name = prev
                            break
            
            if product_name:
                # Clean up product name
                product_name = re.sub(r'^\d+\.?\s*', '', product_name)  # Remove leading numbers
                product_name = re.sub(r'\s+', ' ', product_name)  # Normalize spaces
                
                products.append({
                    "name": product_name.strip()[:100],  # Limit length
                    "category": current_category,
                    "price": price,
                    "gst_percent": gst,
                    "raw_line": line_stripped[:200]
                })
    
    return products

def parse_all_documents():
    """Parse all extracted text files."""
    catalog = defaultdict(lambda: {"prices": [], "categories": set()})
    customers = defaultdict(lambda: {"purchases": [], "contact": None, "email": None})
    
    text_files = list(EXTRACTED_DIR.glob("*.txt"))
    print(f"Processing {len(text_files)} files...")
    
    for txt_file in text_files:
        text = txt_file.read_text(encoding='utf-8', errors='ignore')
        
        # Skip empty files
        if len(text.strip()) < 100:
            continue
        
        # Extract customer info
        customer = extract_customer_info(text)
        customer_name = customer.get("name") or "Unknown"
        
        # Extract products
        products = extract_products_and_prices(text)
        
        # Add to catalog and customer history
        for prod in products:
            prod_name = prod["name"]
            
            # Add to catalog
            catalog[prod_name]["prices"].append({
                "price": prod["price"],
                "gst": prod["gst_percent"],
                "customer": customer_name,
                "file": txt_file.name
            })
            if prod["category"]:
                catalog[prod_name]["categories"].add(prod["category"])
            
            # Add to customer purchase history
            customers[customer_name]["purchases"].append({
                "product": prod_name,
                "price": prod["price"],
                "gst": prod["gst_percent"],
                "file": txt_file.name
            })
        
        if customer.get("contact"):
            customers[customer_name]["contact"] = customer["contact"]
        if customer.get("email"):
            customers[customer_name]["email"] = customer["email"]
    
    return catalog, customers

def generate_reports(catalog, customers):
    """Generate structured reports."""
    
    # 1. Product Catalog with Pricing Tiers
    catalog_report = []
    for product_name, data in sorted(catalog.items()):
        prices = data["prices"]
        
        # Group by price to find tiers
        price_map = defaultdict(list)
        for p in prices:
            price_map[p["price"]].append(p["customer"])
        
        tiers = []
        for price, cust_list in sorted(price_map.items()):
            tiers.append({
                "price": price,
                "customers": list(set(cust_list)),
                "count": len(cust_list)
            })
        
        catalog_report.append({
            "product": product_name,
            "categories": list(data["categories"]),
            "pricing_tiers": tiers,
            "min_price": min(p["price"] for p in prices) if prices else None,
            "max_price": max(p["price"] for p in prices) if prices else None,
            "times_quoted": len(prices)
        })
    
    # 2. Customer Purchase History
    customer_report = []
    for cust_name, data in sorted(customers.items()):
        if cust_name == "Unknown" and not data["purchases"]:
            continue
            
        # Group purchases by product
        product_summary = defaultdict(lambda: {"prices": [], "count": 0})
        for p in data["purchases"]:
            product_summary[p["product"]]["prices"].append(p["price"])
            product_summary[p["product"]]["count"] += 1
        
        purchases_list = []
        for prod, pdata in product_summary.items():
            purchases_list.append({
                "product": prod,
                "times_purchased": pdata["count"],
                "prices_paid": sorted(set(pdata["prices"]))
            })
        
        customer_report.append({
            "customer": cust_name,
            "contact": data["contact"],
            "email": data["email"],
            "total_purchases": len(data["purchases"]),
            "unique_products": len(product_summary),
            "purchases": purchases_list
        })
    
    return catalog_report, customer_report

if __name__ == "__main__":
    catalog, customers = parse_all_documents()
    
    catalog_report, customer_report = generate_reports(catalog, customers)
    
    # Save reports
    with open(OUTPUT_DIR / "product_catalog.json", "w", encoding="utf-8") as f:
        json.dump(catalog_report, f, indent=2, ensure_ascii=False)
    
    with open(OUTPUT_DIR / "customer_purchases.json", "w", encoding="utf-8") as f:
        json.dump(customer_report, f, indent=2, ensure_ascii=False)
    
    # Summary
    print(f"Products found: {len(catalog_report)}")
    print(f"Customers found: {len(customer_report)}")
    print(f"Reports saved to: {OUTPUT_DIR}")
    
    # Print sample
    print("\n=== Sample Products ===")
    for prod in catalog_report[:5]:
        print(f"\n{prod['product']}")
        for tier in prod['pricing_tiers'][:3]:
            print(f"  Rs. {tier['price']:,.2f} - {tier['count']} quote(s)")
