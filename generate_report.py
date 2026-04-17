#!/usr/bin/env python3
"""Generate clean summary reports from parsed catalog data."""

import json
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR = Path("/home/sachin/work/bajaj/analysis")

# Load the parsed data
with open(ANALYSIS_DIR / "product_catalog.json", "r", encoding="utf-8") as f:
    catalog = json.load(f)

with open(ANALYSIS_DIR / "customer_purchases.json", "r", encoding="utf-8") as f:
    customers = json.load(f)

# Filter out garbage entries
def is_valid_product(name):
    if not name or len(name) < 5:
        return False
    if name.isdigit():
        return False
    garbage_patterns = ["weight:", "appx.", "/-", ",", "00", "000", "(after", "discount)", 
                       "ground", "mm", "side", "projection", "length:", "height:", "fastener",
                       "installation charge", "cartage", "extra", 
                       "help protect", "to use of", "wheels to", "use of branded"]
    name_lower = name.lower()
    for pattern in garbage_patterns:
        if pattern in name_lower:
            return False
    return True

# Clean catalog
clean_catalog = [p for p in catalog if is_valid_product(p["product"])]
clean_catalog.sort(key=lambda x: x["times_quoted"], reverse=True)

# Generate reports
print("=" * 80)
print("BAJAJ SPORTS - PRODUCT CATALOG & PRICING ANALYSIS")
print("=" * 80)

print(f"\n📊 SUMMARY")
print(f"   Total products found: {len(clean_catalog)}")
print(f"   Total customers: {len([c for c in customers if c['total_purchases'] > 0])}")

# Top products by quote frequency
print(f"\n🏆 TOP 15 MOST QUOTED PRODUCTS")
print("-" * 80)
for i, prod in enumerate(clean_catalog[:15], 1):
    tiers = len(prod["pricing_tiers"])
    price_range = f"Rs. {prod['min_price']:,.0f}" if prod["min_price"] == prod["max_price"] else f"Rs. {prod['min_price']:,.0f} - {prod['max_price']:,.0f}"
    print(f"{i:2}. {prod['product'][:55]}")
    print(f"    Quoted: {prod['times_quoted']} times | Price tiers: {tiers} | Range: {price_range}")

# Products with multiple price tiers (price discrimination)
print(f"\n💰 PRODUCTS WITH MULTIPLE PRICING TIERS (Different customers, different prices)")
print("-" * 80)
multi_tier = [p for p in clean_catalog if len(p["pricing_tiers"]) > 1]
multi_tier.sort(key=lambda x: len(x["pricing_tiers"]), reverse=True)

for prod in multi_tier[:10]:
    print(f"\n📌 {prod['product']}")
    for tier in prod["pricing_tiers"]:
        customers_str = ", ".join(tier["customers"][:3])
        if len(tier["customers"]) > 3:
            customers_str += f" +{len(tier['customers']) - 3} more"
        print(f"   Rs. {tier['price']:,.2f} - {tier['count']} quote(s)")
        print(f"      Customers: {customers_str}")

# Customer summary
print(f"\n👥 CUSTOMER PURCHASE SUMMARIES")
print("-" * 80)
# Filter out garbage customers
garbage_customers = ["unknown", "bajaj", "durathon", "branded", "disy", "benguluru", "haryana", 
                     "ground", "fastener", "help protect", "and"]

clean_customers = []
for c in customers:
    name = c["customer"].lower()
    if any(g in name for g in garbage_customers):
        continue
    if len(c["customer"]) < 10:
        continue
    clean_customers.append(c)

clean_customers.sort(key=lambda x: x["total_purchases"], reverse=True)

for cust in clean_customers[:8]:
    print(f"\n🏢 {cust['customer']}")
    print(f"   Contact: {cust['contact'] or 'N/A'}")
    print(f"   Total items quoted: {cust['total_purchases']}")
    print(f"   Unique products: {cust['unique_products']}")
    for pur in cust["purchases"][:5]:
        if is_valid_product(pur["product"]):
            prices = ", ".join([f"Rs. {p:,.0f}" for p in pur["prices_paid"]])
            print(f"   • {pur['product'][:40]}: {prices}")

# Save clean catalog
with open(ANALYSIS_DIR / "clean_catalog.json", "w", encoding="utf-8") as f:
    json.dump(clean_catalog, f, indent=2, ensure_ascii=False)

print(f"\n✅ Clean catalog saved: {ANALYSIS_DIR / 'clean_catalog.json'}")
