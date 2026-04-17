import sqlite3
import json
import os
from datetime import datetime, timedelta

JSON_FILE = "dummy_quotes_fallback.json"
DB_FILE = "dev_quotes.db"

def generate_dummy_data():
    today = datetime.now()
    return [
        {
            "client_name": "Local High School",
            "client_address": "123 Education Lane",
            "quote_date": today.strftime('%Y-%m-%d'),
            "total_amount": 45000,
            "gst_amount": 5400,
            "grand_total": 50400,
            "items": [
                {"product_name": "Basketball", "description": "Size 7", "unit_price": 1000, "quantity": 10, "gst_percent": 12, "line_total": 10000},
                {"product_name": "Football Net", "description": "Standard", "unit_price": 35000, "quantity": 1, "gst_percent": 12, "line_total": 35000}
            ]
        },
        {
            "client_name": "City Sports Club",
            "client_address": "45 Arena Blvd",
            "quote_date": (today - timedelta(days=5)).strftime('%Y-%m-%d'),
            "total_amount": 120000,
            "gst_amount": 21600,
            "grand_total": 141600,
            "items": [
                {"product_name": "Tennis Racket", "description": "Pro Series", "unit_price": 6000, "quantity": 20, "gst_percent": 18, "line_total": 120000}
            ]
        },
        {
            "client_name": "Inactive College",
            "client_address": "Old Town Road",
            "quote_date": (today - timedelta(days=70)).strftime('%Y-%m-%d'),
            "total_amount": 15000,
            "gst_amount": 2700,
            "grand_total": 17700,
            "items": [
                {"product_name": "Badminton Shuttlecocks", "description": "Nylon Tube", "unit_price": 500, "quantity": 30, "gst_percent": 18, "line_total": 15000}
            ]
        }
    ]

def setup():
    # 1. Create the JSON fallback file
    data = generate_dummy_data()
    with open(JSON_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print(f"✅ Created dummy JSON fallback: {JSON_FILE}")

    # 2. Create the SQLite Database
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)
    
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    # Create Tables (matching production schema)
    c.execute('''
        CREATE TABLE quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT, client_address TEXT, client_contact TEXT,
            quote_date TEXT, total_amount REAL, gst_amount REAL,
            grand_total REAL, notes TEXT, created_at TEXT, pdf_path TEXT
        )
    ''')
    
    c.execute('''
        CREATE TABLE quote_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER, product_name TEXT, description TEXT,
            quantity INTEGER, unit_price REAL, gst_percent REAL,
            line_total REAL, price_source TEXT, unit TEXT
        )
    ''')

    # Insert Data
    for q in data:
        c.execute('''
            INSERT INTO quotes (client_name, client_address, quote_date, total_amount, gst_amount, grand_total, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (q["client_name"], q.get("client_address", ""), q["quote_date"], q["total_amount"], q["gst_amount"], q["grand_total"], datetime.now().isoformat()))
        
        quote_id = c.lastrowid
        
        for item in q["items"]:
            c.execute('''
                INSERT INTO quote_items (quote_id, product_name, description, quantity, unit_price, gst_percent, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (quote_id, item["product_name"], item.get("description", ""), item["quantity"], item["unit_price"], item["gst_percent"], item["line_total"]))

    conn.commit()
    conn.close()
    print(f"✅ Created local development database: {DB_FILE} with {len(data)} quotes.")
    print("🚀 You can now run QuoteQuery locally without needing the production database.")

if __name__ == "__main__":
    setup()
