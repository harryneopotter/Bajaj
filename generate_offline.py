import json
from pathlib import Path

# Paths
ROOT_DIR = Path("/home/sachin/work/bajaj")
CATALOG_PATH = ROOT_DIR / "analysis/clean_catalog.json"
CUSTOMERS_PATH = ROOT_DIR / "analysis/customer_purchases.json"
OFFLINE_HTML = ROOT_DIR / "BAJAJ_OFFLINE_DATA.html"

def generate_offline_view():
    catalog = json.loads(CATALOG_PATH.read_text())
    customers = json.loads(CUSTOMERS_PATH.read_text())
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Bajaj Sports - Offline Data Export</title>
        <style>
            body {{ font-family: sans-serif; line-height: 1.6; color: #333; max-width: 1000px; margin: 40px auto; padding: 20px; }}
            h1 {{ color: #1a237e; border-bottom: 3px solid #1a237e; padding-bottom: 10px; }}
            h2 {{ color: #283593; margin-top: 40px; border-bottom: 1px solid #ddd; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px; }}
            th {{ background: #f5f5f5; text-align: left; padding: 12px; border: 1px solid #ddd; }}
            td {{ padding: 10px; border: 1px solid #ddd; vertical-align: top; }}
            .price {{ font-weight: bold; color: #1a237e; }}
            .meta {{ color: #666; font-size: 12px; }}
        </style>
    </head>
    <body>
        <h1>🏏 Bajaj Sports - Data Inventory (Offline)</h1>
        <p>Generated: 2026-02-06 | <strong>{len(customers)}</strong> Clients | <strong>{len(catalog)}</strong> Products</p>
        
        <h2>Clients</h2>
        <table>
            <thead>
                <tr>
                    <th style="width:30%">Name</th>
                    <th style="width:50%">Address / Details</th>
                    <th style="width:20%">Purchase Count</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for c in sorted(customers, key=lambda x: x['customer']):
        html += f"""
                <tr>
                    <td><strong>{c['customer']}</strong></td>
                    <td>{c.get('address', '').replace('\\n', '<br>')}</td>
                    <td>{len(c.get('purchases', []))} records found</td>
                </tr>
        """
        
    html += """
            </tbody>
        </table>
        
        <h2>Product Catalog</h2>
        <table>
            <thead>
                <tr>
                    <th style="width:50%">Product Name</th>
                    <th style="width:25%">Price Range (Min - Max)</th>
                    <th style="width:25%">Recent Clients</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for p in sorted(catalog, key=lambda x: x['product']):
        clients = ", ".join(list(set([cust for tier in p['pricing_tiers'] for cust in tier['customers']]))[:3])
        html += f"""
                <tr>
                    <td>{p['product']}</td>
                    <td class="price">₹{p['min_price']:,.2f} - ₹{p['max_price']:,.2f}</td>
                    <td class="meta">{clients}...</td>
                </tr>
        """
        
    html += """
            </tbody>
        </table>
    </body>
    </html>
    """
    
    OFFLINE_HTML.write_text(html)
    print(f"Generated offline view: {OFFLINE_HTML}")

if __name__ == "__main__":
    generate_offline_view()
