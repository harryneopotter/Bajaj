#!/usr/bin/env python3
"""
Invoice parser MVP skeleton
- Detects 3-4 layouts and parses client, date, items
- CLI entry to process /home/sachin/work/bajaj/extracted
- Writes to data/invoices.sqlite and outputs invoices.json + invoices_verification.json
"""
import sys
from pathlib import Path
import json
import sqlite3
from typing import List, Dict, Optional

EXTRACTED_DIR = Path("/home/sachin/work/bajaj/extracted")
DB_PATH = Path("/home/sachin/work/bajaj/data/invoices.sqlite")
OUTPUT_JSON = Path("/home/sachin/work/bajaj/invoices.json")
VERIF_JSON = Path("/home/sachin/work/bajaj/invoices_verification.json")

# Simple data models
class Item:
    def __init__(self, name:str, price:float, gst_pct:float=None, qty:int=None, total:float=None):
        self.name=name
        self.price=price
        self.gst_pct=gst_pct
        self.qty=qty
        self.total=total if total is not None else (price * (qty or 1))

class InvoiceData:
    def __init__(self, client:str, date:str, items:List[Item], source_file:str, doc_type:str=None):
        self.client=client
        self.date=date
        self.items=items
        self.source_file=source_file
        self.doc_type = doc_type or "unknown"

# Placeholder parsers (to be filled with real regex later)
import re

def layout_detector(text:str) -> int:
    text=text or ""
    # Very rough detectors; replace with real heuristics later
    if re.search(r"Item|Description|Rate|GST|Amount", text, re.I):
        return 1  # Layout A
    if re.search(r"Total\s*[:]|Grand Total|Subtotal", text, re.I):
        return 2  # Layout B/C
    if re.search(r"Bill To|Client|To:\s*", text, re.I):
        return 3  # Layout C
    return 4  # Layout D (noisy)


def parse_layout_A(text:str) -> Optional[InvoiceData]:
    # Very naive placeholder: first line as client, last line as date, rest as items with simple price line
    lines=[l.strip() for l in text.splitlines() if l.strip()]
    client = lines[0] if lines else "Unknown"
    date = lines[-1] if lines else ""
    items=[]
    for ln in lines[1:]:
        m = re.findall(r"([A-Za-z0-9 &()_-]+)\\s+Rs\\.?\\s*([0-9,]+(?:\\.[0-9]{2})?)", ln)
        if m:
            for name, price in m:
                price_f=float(price.replace(",",""))
                items.append(Item(name=name.strip(), price=price_f))
    # Simple document-type inference from text cues
    dt = "invoice"
    if re.search(r"Quotation|Quote", text, re.I):
        dt = "quote"
    if items:
        return InvoiceData(client=client, date=date, items=items, source_file="A-layout.txt", doc_type=dt)
    return None


def parse_layout_B(text:str) -> Optional[InvoiceData]:
    # placeholder - similar structure able to extract lines with price at end
    return None


def parse_layout_C(text:str) -> Optional[InvoiceData]:
    return None


def parse_layout_D(text:str) -> Optional[InvoiceData]:
    return None

PARSERS = {
    1: parse_layout_A,
    2: parse_layout_B,
    3: parse_layout_C,
    4: parse_layout_D,
}

def save_to_db(inv: InvoiceData, db_path: Path) -> None:
    # Minimal stub: ensure DB exists with expected schema, insert invoice and one dummy item
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoices (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      source_file TEXT,
      client_id INTEGER,
      date TEXT,
      total REAL,
      raw_text_hash TEXT,
      verified INTEGER,
      type TEXT
    )""")
*** End Patch    cur.execute("""
    CREATE TABLE IF NOT EXISTS clients (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      name TEXT
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS invoice_items (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      invoice_id INTEGER,
      product_id INTEGER,
      quantity INTEGER,
      unit_price REAL,
      line_total REAL
    )""")
    cur.execute("""
    CREATE TABLE IF NOT EXISTS audit_log (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      invoice_id INTEGER,
      action TEXT,
      source TEXT,
      timestamp TEXT,
      note TEXT
    )""")
    conn.commit()

    # Insert simplistic data for demonstration
    # In a real MVP, map client and products to IDs properly
    cur.execute("INSERT INTO invoices (source_file, client_id, date, total, raw_text_hash, verified) VALUES (?, ?, ?, ?, ?, ?)",
                (inv.source_file, None, inv.date, sum([it.price for it in inv.items]) if inv.items else None, "hash", 1))
    inv_id = cur.lastrowid
    for it in inv.items:
        cur.execute("INSERT INTO invoice_items (invoice_id, product_id, quantity, unit_price, line_total) VALUES (?, ?, ?, ?, ?)",
                    (inv_id, None, it.qty or 1, it.price, it.total))
    conn.commit()
    conn.close()

def main():
    # Simple CLI: process all .txt files in EXTRACTED_DIR
    EXTRACTED_DIR = Path("/home/sachin/work/bajaj/extracted")
    texts = []
    for p in sorted(EXTRACTED_DIR.glob("*.txt")):
        texts.append(p.read_text(encoding="utf-8", errors="ignore"))
    # For MVP, run layout detector on first doc only to show flow
    if not texts:
        print("No extracted texts found.")
        return
    first = texts[0]
    layout = layout_detector(first)
    parser = PARSERS.get(layout)
    inv=None
    if parser:
        inv = parser(first)
    # Output simple JSON
    invoices_out = []
    if inv:
        invoices_out.append({
            "client": inv.client,
            "date": inv.date,
            "source_file": inv.source_file,
            "items": [{"name": it.name, "price": it.price} for it in inv.items]
        })
    else:
        invoices_out.append({"note":"no parsed invoice"})

    OUTPUT_JSON = Path("/home/sachin/work/bajaj/invoices.json")
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_JSON.write_text(json.dumps(invoices_out, indent=2), encoding="utf-8")

    # Persist to DB (best-effort)
    if inv:
        save_to_db(inv, Path("/home/sachin/work/bajaj/data/invoices.sqlite"))

    print(f"Processed {len(texts)} files. Layout {layout}. Outputs: {OUTPUT_JSON}")

if __name__ == "__main__":
    main()
