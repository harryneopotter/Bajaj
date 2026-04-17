"""
Step 4: Merge verified extractions into production JSON files.

No API cost. Reads analysis/verified/*.json and produces:
- analysis/customer_purchases.json (deduplicated clients + purchases)
- analysis/clean_catalog.json (product catalog with brand, HSN, pricing)
- analysis/verification_report.json (summary of fixes and flags)
"""

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

VERIFIED_DIR = Path("analysis/verified")
OUTPUT_DIR = Path("analysis")

# Prefixes to strip for client name normalization
CLIENT_PREFIXES = [
    "m/s", "m/s.", "messrs", "messrs.", "the principal",
    "the admin officer", "the director", "the secretary",
    "shri", "smt", "dr", "prof",
]


def normalize_client_name(name):
    """Normalize client name for deduplication."""
    if not name:
        return ""
    n = name.strip()
    n = unicodedata.normalize("NFKD", n)
    n = n.lower()
    # Strip common prefixes
    for prefix in CLIENT_PREFIXES:
        if n.startswith(prefix):
            n = n[len(prefix):].strip().lstrip(".,").strip()
    # Collapse whitespace
    n = re.sub(r'\s+', ' ', n).strip()
    # Remove trailing punctuation
    n = n.rstrip(".,;:")
    return n


def normalize_product_name(name):
    """Normalize product name for deduplication."""
    if not name:
        return ""
    n = name.strip()
    n = unicodedata.normalize("NFKD", n)
    n = n.lower()
    n = re.sub(r'\s+', ' ', n).strip()
    return n


def main():
    if not VERIFIED_DIR.exists():
        print(f"ERROR: {VERIFIED_DIR} not found. Run llm_verify.py first.")
        return

    verified_files = sorted(VERIFIED_DIR.glob("*.json"))
    print(f"Merging {len(verified_files)} verified extractions...")

    # Accumulators
    # client_key -> {name, address, phone, gstin, purchases: [...]}
    clients = {}
    # (normalized_product, brand) -> {product, brand, hsn, pricing_tiers: {price -> [customers]}}
    products = {}
    # Report data
    all_fixes = []
    all_flags = []
    stats = {"files": 0, "items": 0, "fixes": 0, "flags": 0, "needs_review": 0}

    for vf in verified_files:
        data = json.loads(vf.read_text())
        extraction = data.get("extraction", data)
        source = data.get("source_file", vf.stem)
        stats["files"] += 1

        # Collect fixes/flags (handle LLM returning unexpected types)
        fixes = data.get("fixes", [])
        flags = data.get("flags", [])
        if not isinstance(fixes, list):
            fixes = []
        if not isinstance(flags, list):
            flags = []
        for f in fixes:
            if isinstance(f, dict):
                f["source_file"] = source
        for f in flags:
            if isinstance(f, dict):
                f["source_file"] = source
        all_fixes.extend(fixes)
        all_flags.extend(flags)
        stats["fixes"] += len(fixes)
        stats["flags"] += len(flags)
        if data.get("status") == "needs_review":
            stats["needs_review"] += 1

        # --- Client ---
        client_info = extraction.get("client", {})
        client_name = (client_info.get("name") or "").strip()
        if not client_name:
            continue

        client_key = normalize_client_name(client_name)
        if not client_key:
            continue

        if client_key not in clients:
            clients[client_key] = {
                "customer": client_name,
                "address": client_info.get("address"),
                "phone": client_info.get("phone"),
                "gstin": client_info.get("gstin"),
                "purchases": [],
            }
        else:
            # Enrich: fill in missing fields from later documents
            existing = clients[client_key]
            if not existing.get("address") and client_info.get("address"):
                existing["address"] = client_info["address"]
            if not existing.get("phone") and client_info.get("phone"):
                existing["phone"] = client_info["phone"]
            if not existing.get("gstin") and client_info.get("gstin"):
                existing["gstin"] = client_info["gstin"]

        # --- Items ---
        items = extraction.get("items", [])
        date = extraction.get("date")
        ref = extraction.get("ref_number")
        doc_type = extraction.get("doc_type", "unknown")

        for item in items:
            product_name = (item.get("product") or "").strip()
            if not product_name:
                continue

            brand = item.get("brand")
            quantity = item.get("quantity")
            unit_price = item.get("unit_price")
            hsn = item.get("hsn_code")

            stats["items"] += 1

            # Add to client purchases
            purchase = {"product": product_name, "price": unit_price}
            if brand:
                purchase["brand"] = brand
            if quantity:
                purchase["quantity"] = quantity
            if date:
                purchase["date"] = date
            if ref:
                purchase["ref"] = ref
            purchase["doc_type"] = doc_type
            purchase["source"] = source

            needs_review = any(
                isinstance(f, dict) and f.get("field", "").startswith("items") and product_name in str(f.get("value", ""))
                for f in flags
            )
            if needs_review:
                purchase["needs_review"] = True

            clients[client_key]["purchases"].append(purchase)

            # Add to product catalog
            prod_key = (normalize_product_name(product_name), (brand or "").lower())
            if prod_key not in products:
                products[prod_key] = {
                    "product": product_name,
                    "brand": brand,
                    "hsn_code": hsn,
                    "pricing_tiers": defaultdict(lambda: {"customers": [], "count": 0}),
                }
            else:
                # Enrich
                if not products[prod_key]["brand"] and brand:
                    products[prod_key]["brand"] = brand
                if not products[prod_key]["hsn_code"] and hsn:
                    products[prod_key]["hsn_code"] = hsn

            if unit_price is not None:
                tier = products[prod_key]["pricing_tiers"][unit_price]
                tier["customers"].append(client_name)
                tier["count"] += 1

    # --- Build outputs ---

    # Customer purchases
    customer_list = sorted(clients.values(), key=lambda c: c["customer"])
    customer_list = [{k: v for k, v in c.items() if v is not None} for c in customer_list]

    # Clean catalog
    catalog = []
    for (_, _), prod in sorted(products.items(), key=lambda x: x[1]["product"]):
        entry = {
            "product": prod["product"],
            "brand": prod["brand"],
            "hsn_code": prod["hsn_code"],
            "pricing_tiers": [],
            "times_quoted": 0,
        }
        prices = []
        for price, tier in prod["pricing_tiers"].items():
            entry["pricing_tiers"].append({
                "price": price,
                "customers": tier["customers"],
                "count": tier["count"],
            })
            entry["times_quoted"] += tier["count"]
            prices.append(price)

        if prices:
            entry["min_price"] = min(prices)
            entry["max_price"] = max(prices)
        catalog.append(entry)

    # Verification report
    report = {
        "stats": stats,
        "fixes_applied": all_fixes,
        "flags_pending": [f for f in all_flags if isinstance(f, dict) and f.get("confidence") == "low"],
        "summary": {
            "total_clients": len(customer_list),
            "total_products": len(catalog),
            "total_items_extracted": stats["items"],
            "files_needing_review": stats["needs_review"],
        },
    }

    # --- Write outputs ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Backup existing files
    for name in ["customer_purchases.json", "clean_catalog.json"]:
        p = OUTPUT_DIR / name
        if p.exists():
            backup = OUTPUT_DIR / f"{p.stem}_backup.json"
            backup.write_text(p.read_text())
            print(f"  Backed up {name} -> {backup.name}")

    (OUTPUT_DIR / "customer_purchases.json").write_text(
        json.dumps(customer_list, indent=2, ensure_ascii=False)
    )
    (OUTPUT_DIR / "clean_catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False)
    )
    (OUTPUT_DIR / "verification_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )

    print(f"\nMerge complete:")
    print(f"  Clients: {len(customer_list)}")
    print(f"  Products: {len(catalog)}")
    print(f"  Items extracted: {stats['items']}")
    print(f"  Fixes applied: {stats['fixes']}")
    print(f"  Flags pending review: {len(report['flags_pending'])}")
    print(f"  Files needing review: {stats['needs_review']}")
    print(f"\nOutputs:")
    print(f"  {OUTPUT_DIR / 'customer_purchases.json'}")
    print(f"  {OUTPUT_DIR / 'clean_catalog.json'}")
    print(f"  {OUTPUT_DIR / 'verification_report.json'}")


if __name__ == "__main__":
    main()
