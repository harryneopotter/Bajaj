#!/usr/bin/env python3
"""
Bajaj Sports - Quotation Generator MVP
FastAPI app for creating quotations with:
- Client autocomplete (from past data)
- Product autocomplete with pricing history
- Pricing suggestions (last price to client, or other clients)
- PDF generation (WeasyPrint)
"""
import os
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
from contextlib import contextmanager

from fastapi import FastAPI, Request, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi import UploadFile, File
import shutil
import hashlib

# Config
BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/home/sachin/work/bajaj"))
ANALYSIS_DIR = DATA_DIR / "analysis"
DB_PATH = BASE_DIR / "quotes.db"
UNIT_TERMS_PATH = BASE_DIR / "unit_terms.json"
PRODUCT_IMAGES_REGISTRY = ANALYSIS_DIR / "product_images.json"
IMAGES_DIR = BASE_DIR / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)

# Load catalog data
def load_catalog() -> List[Dict]:
    path = ANALYSIS_DIR / "clean_catalog.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []

def load_customers() -> List[Dict]:
    path = ANALYSIS_DIR / "customer_purchases.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return []


def load_unit_terms() -> List[str]:
    try:
        if UNIT_TERMS_PATH.exists():
            data = json.loads(UNIT_TERMS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(x).strip() for x in data if str(x).strip()]
    except Exception:
        pass
    return ["Nos", "Piece", "Pair", "Set"]


def normalize_unit_term(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return ""
    # normalize common variants
    s = s.replace("Nos.", "Nos").replace("No.", "Nos")
    return s


def register_unit_term(term: str) -> None:
    term = normalize_unit_term(term)
    if not term:
        return

    terms = load_unit_terms()
    low = {t.lower() for t in terms}
    if term.lower() in low:
        return

    terms.append(term)
    terms = sorted(terms, key=lambda x: x.lower())
    UNIT_TERMS_PATH.write_text(json.dumps(terms, ensure_ascii=False, indent=2), encoding="utf-8")

CATALOG = load_catalog()
CUSTOMERS = load_customers()
UNIT_TERMS = load_unit_terms()

# Build lookup indices
PRODUCT_INDEX: Dict[str, Dict] = {}
for p in CATALOG:
    name = p.get("product", "").strip()
    if name:
        PRODUCT_INDEX[name.lower()] = p

CUSTOMER_NAMES: List[str] = []
for c in CUSTOMERS:
    name = c.get("customer", "").strip()
    if name and name not in CUSTOMER_NAMES:
        CUSTOMER_NAMES.append(name)

app = FastAPI(title="Bajaj Sports Quote Generator")

ALLOWED_IPS = {"100.84.92.33", "100.119.13.60"}
import fastapi
@app.middleware("http")
async def ip_whitelist_middleware(request: fastapi.Request, call_next):
    if request.client.host not in ALLOWED_IPS:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": f"Access denied. Your IP ({request.client.host}) is not authorized."})
    return await call_next(request)


# Static files for downloads/broken scans
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# DB setup
@contextmanager
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def ensure_columns(conn: sqlite3.Connection, table: str, cols: Dict[str, str]) -> None:
    """Add missing columns (SQLite) safely."""
    existing = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, decl in cols.items():
        if name in existing:
            continue
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")


def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quotes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            client_address TEXT,
            client_contact TEXT,
            quote_date TEXT NOT NULL,
            total_amount REAL,
            gst_amount REAL,
            grand_total REAL,
            notes TEXT,
            created_at TEXT NOT NULL,
            pdf_path TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS quote_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quote_id INTEGER NOT NULL,
            product_name TEXT NOT NULL,
            description TEXT,
            quantity INTEGER DEFAULT 1,
            unit_price REAL NOT NULL,
            gst_percent REAL DEFAULT 18.0,
            line_total REAL NOT NULL,
            price_source TEXT,
            FOREIGN KEY(quote_id) REFERENCES quotes(id)
        )""")

        # forward-compatible columns
        ensure_columns(conn, 'quote_items', {
            'unit': 'TEXT',
        })

        conn.commit()

init_db()

# HTML Templates
MAIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bajaj Sports - Quote Generator</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #fafafa;
            min-height: 100vh;
            color: #333;
        }
        .header {
            background: #111;
            color: white;
            padding: 16px 24px;
            box-shadow: 0 2px 12px rgba(0,0,0,0.2);
            display: flex;
            align-items: center;
            justify-content: space-between;
            border-bottom: 4px solid #c5a059;
        }
        .header-content { display: flex; align-items: center; gap: 20px; }
        .header img { height: 60px; }
        .header h1 { font-size: 22px; font-weight: 600; margin: 0; }
        .header p { opacity: 0.7; margin-top: 2px; font-size: 13px; }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 24px;
        }
        
        .card {
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
            padding: 24px;
            margin-bottom: 20px;
            border: 1px solid #eee;
        }
        .card h2 {
            font-size: 15px;
            font-weight: 700;
            color: #111;
            margin-bottom: 16px;
            padding-bottom: 12px;
            border-bottom: 2px solid #f0f0f0;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        
        .form-row {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 16px;
            margin-bottom: 16px;
        }
        
        .form-group { display: flex; flex-direction: column; }
        .form-group label {
            font-size: 13px;
            font-weight: 500;
            color: #555;
            margin-bottom: 6px;
        }
        .form-group input, .form-group textarea {
            padding: 10px 12px;
            border: 1px solid #ddd;
            border-radius: 8px;
            font-size: 14px;
            transition: border-color 0.2s, box-shadow 0.2s;
        }
        .form-group input:focus, .form-group textarea:focus {
            outline: none;
            border-color: #c5a059;
            box-shadow: 0 0 0 3px rgba(197,160,89,0.1);
        }
        
        .autocomplete-wrapper { position: relative; }
        .autocomplete-list {
            position: absolute;
            top: 100%;
            left: 0;
            right: 0;
            background: white;
            border: 1px solid #ddd;
            border-radius: 8px;
            max-height: 350px;
            overflow-y: auto;
            z-index: 100;
            box-shadow: 0 8px 24px rgba(0,0,0,0.15);
            display: none;
        }
        .autocomplete-list.active { display: block; }
        .autocomplete-item {
            padding: 12px 16px;
            cursor: pointer;
            border-bottom: 1px solid #f0f0f0;
            transition: background 0.2s;
        }
        .autocomplete-item:hover { background: #fff9f0; }
        .autocomplete-item:last-child { border-bottom: none; }
        .autocomplete-item .name { font-weight: 600; color: #111; font-size: 15px; }
        .autocomplete-item .meta { font-size: 13px; color: #666; margin-top: 4px; line-height: 1.4; }
        .autocomplete-item .price-row { display: flex; justify-content: space-between; margin-top: 6px; border-top: 1px solid #eee; padding-top: 4px; }
        .autocomplete-item .price-tag { font-weight: bold; color: #c5a059; }
        
        .items-table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
        }
        .items-table th {
            text-align: left;
            font-size: 11px;
            font-weight: 700;
            color: #888;
            padding: 10px 8px;
            border-bottom: 2px solid #eee;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .items-table td {
            padding: 12px 8px;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: top;
        }
        .items-table input {
            width: 100%;
            padding: 8px;
            border: 1px solid #ddd;
            border-radius: 6px;
            font-size: 14px;
        }
        .items-table input:focus {
            outline: none;
            border-color: #c5a059;
        }
        
        .price-hint {
            font-size: 11px;
            margin-top: 4px;
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: 500;
        }
        .price-hint.last-client {
            background: #fff3e0;
            color: #e65100;
            border: 1px solid #ffe0b2;
        }
        .price-hint.other-client {
            background: #f5f5f5;
            color: #666;
        }
        
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 14px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
        }
        .btn-primary {
            background: #111;
            color: white;
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        .btn-primary:hover { 
            background: #c5a059; 
            transform: translateY(-1px);
            box-shadow: 0 6px 16px rgba(197,160,89,0.3);
        }
        .btn-secondary {
            background: #fff;
            color: #111;
            border: 1px solid #ddd;
        }
        .btn-secondary:hover { background: #f5f5f5; }
        
        .btn-row {
            display: flex;
            gap: 12px;
            margin-top: 20px;
        }
        
        .totals {
            display: flex;
            flex-direction: column;
            align-items: flex-end;
            padding: 16px 0;
            border-top: 2px solid #eee;
            margin-top: 16px;
        }
        .total-row {
            display: flex;
            justify-content: space-between;
            width: 300px;
            padding: 8px 0;
            font-size: 14px;
            color: #666;
        }
        .total-row.grand {
            font-size: 20px;
            font-weight: 800;
            color: #111;
            border-top: 2px solid #111;
            padding-top: 12px;
            margin-top: 8px;
        }
        
        .remove-btn {
            background: none;
            border: none;
            color: #ff5252;
            cursor: pointer;
            font-size: 20px;
            padding: 4px 8px;
            transition: opacity 0.2s;
        }
        .remove-btn:hover { opacity: 0.7; }
        
        .add-row-btn {
            margin-top: 12px;
            background: #fff;
            color: #111;
            border: 2px dashed #ddd;
        }
        .add-row-btn:hover { border-color: #c5a059; color: #c5a059; }
        
        .status-bar {
            position: fixed;
            bottom: 24px;
            right: 24px;
            padding: 14px 24px;
            background: #111;
            color: white;
            border-radius: 12px;
            box-shadow: 0 12px 32px rgba(0,0,0,0.25);
            display: none;
            z-index: 1000;
            border-left: 4px solid #c5a059;
        }
        .status-bar.error { border-left-color: #ff5252; }
        .status-bar.active { display: block; animation: slideUp 0.3s ease-out; }
        
        @keyframes slideUp {
            from { transform: translateY(20px); opacity: 0; }
            to { transform: translateY(0); opacity: 1; }
        }
        
        .past-quotes {
            margin-top: 24px;
        }
        .quote-row {
            display: flex;
            align-items: center;
            padding: 16px;
            border-bottom: 1px solid #f0f0f0;
            gap: 16px;
            transition: background 0.2s;
        }
        .quote-row:hover { background: #fff9f0; }
        .quote-info { flex: 1; }
        .quote-info .client { font-weight: 700; color: #111; font-size: 15px; }
        .quote-info .date { font-size: 12px; color: #888; margin-top: 2px; }
        .quote-amount { font-weight: 800; color: #c5a059; font-size: 16px; }
        .nav-links { display: flex; gap: 12px; margin-left: auto; }
        .nav-links a { color: #c5a059; text-decoration: none; font-size: 13px; font-weight: 600; opacity: 0.8; transition: opacity 0.2s; }
        .nav-links a:hover { opacity: 1; text-decoration: underline; }
        .nav-links a.active { opacity: 1; border-bottom: 2px solid #c5a059; }
    </style>
</head>
<body>
    <div class="header">
        <div class="header-content">
            <img src="static/logo.png" alt="Bajaj & Company">
            <div>
                <h1>Quotation System</h1>
                <p>Digital Intelligence Layer</p>
            </div>
        </div>
        <div style="display: flex; flex-direction: column; align-items: flex-end; gap: 4px;">
            <div style="font-size: 12px; opacity: 0.6;">v1.2 Production</div>
        </div>
    </div>
    
    <div class="container">
        <input type="hidden" id="quote-id" value="">
        <!-- Client Info -->
        <div class="card">
            <h2>Client Information</h2>
            <div class="form-row">
                <div class="form-group">
                    <label>Client Name *</label>
                    <div class="autocomplete-wrapper">
                        <input type="text" id="client-name" placeholder="Start typing..." autocomplete="off">
                        <div class="autocomplete-list" id="client-suggestions"></div>
                    </div>
                </div>
                <div class="form-group">
                    <label>Contact Number</label>
                    <input type="text" id="client-contact" placeholder="Phone number">
                </div>
            </div>
            <div class="form-group">
                <label>Address</label>
                <textarea id="client-address" rows="2" placeholder="Full address"></textarea>
            </div>
            <div class="form-group">
                <label>GSTIN</label>
                <input type="text" id="client-gstin" placeholder="15-char GSTIN">
            </div>
            <div class="form-row">
                <div class="form-group">
                    <label>Quote Date</label>
                    <input type="date" id="quote-date" value="">
                </div>
                <div class="form-group" style="flex-direction: row; align-items: center; gap: 10px; margin-top: 20px;">
                    <input type="checkbox" id="use-letterhead" style="width: auto;">
                    <label for="use-letterhead" style="margin-bottom: 0;">Print on Letterhead (Leaves 45mm top margin)</label>
                </div>
            </div>
        </div>
        
        <!-- Line Items -->
        <div class="card">
            <h2>Quotation Items</h2>
            <table class="items-table">
                <thead>
                    <tr>
                        <th style="width: 33%">Product</th>
                        <th style="width: 22%">Description</th>
                        <th style="width: 12%">Unit</th>
                        <th style="width: 8%">GST%</th>
                        <th style="width: 13%">Unit Price (₹)</th>
                        <th style="width: 10%">Image</th>
                        <th style="width: 12%">Total (₹)</th>
                        <th style="width: 5%"></th>
                    </tr>
                </thead>
                <tbody id="items-body">
                    <!-- Items added dynamically -->
                </tbody>
            </table>

            <datalist id="unit-list"></datalist>
            
            <button class="btn add-row-btn" onclick="addItemRow()">+ Add Item</button>
            
            <div class="totals">
                <div class="total-row">
                    <span>Subtotal (Taxable):</span>
                    <span id="subtotal">₹0.00</span>
                </div>
                <div class="total-row">
                    <span>GST @5%:</span>
                    <span id="gst-5">₹0.00</span>
                </div>
                <div class="total-row">
                    <span>GST @12%:</span>
                    <span id="gst-12">₹0.00</span>
                </div>
                <div class="total-row">
                    <span>GST @18%:</span>
                    <span id="gst-18">₹0.00</span>
                </div>
                <div class="total-row">
                    <span>Total GST:</span>
                    <span id="gst-amount">₹0.00</span>
                </div>
                <div class="total-row grand">
                    <span>Grand Total:</span>
                    <span id="grand-total">₹0.00</span>
                </div>
            </div>
        </div>
        
        <!-- Notes -->
        <div class="card">
            <h2>Additional Notes</h2>
            <div class="form-group">
                <textarea id="notes" rows="3" placeholder="Terms, conditions, delivery notes..."></textarea>
            </div>
        </div>
        <!-- Optional Sections -->
        <div class="card">
            <h2>Optional Sections</h2>
            
            <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <input type="checkbox" id="enable-payment-terms" onchange="document.getElementById('payment-terms-wrap').style.display = this.checked ? 'block' : 'none'">
                    <label for="enable-payment-terms" style="font-weight: 600; font-size: 14px; margin: 0;">Payment Terms</label>
                </div>
                <div id="payment-terms-wrap" style="display: none;">
                    <textarea id="payment-terms" rows="2" style="width: 100%;" placeholder="e.g., 50% advance, balance against delivery">100% advance along with firm purchase order.</textarea>
                </div>
            </div>

            <div style="margin-bottom: 20px; padding-bottom: 15px; border-bottom: 1px solid #eee;">
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <input type="checkbox" id="enable-transport" onchange="document.getElementById('transport-wrap').style.display = this.checked ? 'block' : 'none'">
                    <label for="enable-transport" style="font-weight: 600; font-size: 14px; margin: 0;">Transportation Charges</label>
                </div>
                <div id="transport-wrap" style="display: none;">
                    <input type="text" id="transport-charges" style="width: 100%;" placeholder="e.g., Extra at actuals / Included">Extra at actuals.
                </div>
            </div>

            <div>
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 10px;">
                    <input type="checkbox" id="enable-installation" onchange="document.getElementById('installation-wrap').style.display = this.checked ? 'block' : 'none'">
                    <label for="enable-installation" style="font-weight: 600; font-size: 14px; margin: 0;">Installation Charges</label>
                </div>
                <div id="installation-wrap" style="display: none;">
                    <input type="text" id="installation-charges" style="width: 100%;" placeholder="e.g., Free of cost / ₹5,000 extra">Installation and GST charges extra at actuals.
                </div>
            </div>
        </div>

        
        <!-- Actions -->
        <div class="btn-row">
            <button class="btn btn-primary" onclick="generateQuote()">📄 View / Download PDF</button>
            <button class="btn btn-secondary" onclick="saveQuote()">💾 Save Draft</button>
            <button class="btn btn-secondary" onclick="clearForm()">🗑️ New Quote</button>
            <button class="btn btn-secondary" style="background: #e8f5e9; color: #2e7d32;" onclick="shareWhatsApp()">📱 Share on WhatsApp</button>
        </div>
        
        <!-- Recent Quotes -->
        <div class="card past-quotes">
            <h2>Recent Quotations</h2>
            <div id="recent-quotes">
                <p style="color: #888; font-size: 14px; padding: 20px 0;">No quotations yet. Create your first one above!</p>
            </div>
        </div>

        <div style="text-align: center; padding: 20px; font-size: 12px; color: #aaa;">
            Automated by <a href="https://bluepanda.in" target="_blank" style="color: #c5a059; text-decoration: none; font-weight: bold;">BluePanda</a>
        </div>
    </div>
    
    <div class="status-bar" id="status-bar"></div>
    
    <script>
        // Legacy: GST is now per-line item (5%/18%).
        const GST_PERCENT = 18;
        let itemCounter = 0;
        
        // Set today's date
        document.getElementById('quote-date').value = new Date().toISOString().split('T')[0];
        
        // Client autocomplete
        const clientInput = document.getElementById('client-name');
        const clientSuggestions = document.getElementById('client-suggestions');
        
        clientInput.addEventListener('input', async (e) => {
            const query = e.target.value.trim();
            if (query.length < 2) {
                clientSuggestions.classList.remove('active');
                return;
            }
            
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            if (baseUrl === '/bajaj') {
                // We are at /bajaj, so baseUrl is /bajaj
            } else if (baseUrl === '') {
                // Root
            }
            const res = await fetch(`${baseUrl}/api/clients?q=${encodeURIComponent(query)}`);
            const clients = await res.json();
            
            if (clients.length === 0) {
                clientSuggestions.classList.remove('active');
                return;
            }
            
            clientSuggestions.innerHTML = clients.map(c => `
                <div class="autocomplete-item" onclick="selectClient('${escapeHtml(c.name)}')">
                    <div class="name">${escapeHtml(c.name)}</div>
                    <div class="meta">${c.address ? escapeHtml(c.address.substring(0, 50)) : ''}${c.gstin ? ' · GSTIN: ' + escapeHtml(c.gstin) : ''}</div>
                    <div class="meta" style="color:#aaa;">${c.purchase_count || 0} previous purchases</div>
                </div>
            `).join('');
            clientSuggestions.classList.add('active');
        });
        
        clientInput.addEventListener('blur', () => {
            setTimeout(() => clientSuggestions.classList.remove('active'), 200);
        });
        
        function selectClient(name) {
            clientInput.value = name;
            clientSuggestions.classList.remove('active');
            
            // Find client data to fill other fields
            fetch(`${window.location.pathname.replace(/\/+$/, '')}/api/clients?q=${encodeURIComponent(name)}`)
                .then(res => res.json())
                .then(data => {
                    const client = data.find(c => c.name === name);
                    if (client) {
                        document.getElementById('client-contact').value = client.phone || '';
                        document.getElementById('client-address').value = client.address || '';
                        document.getElementById('client-gstin').value = client.gstin || '';
                    }
                });

            // Refresh pricing hints for all items
            refreshAllPriceHints();
        }
        
        function escapeHtml(str) {
            return str.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
        }
        
        // Add item row
        function addItemRow() {
            itemCounter++;
            const tbody = document.getElementById('items-body');
            const row = document.createElement('tr');
            row.id = `item-row-${itemCounter}`;
            row.innerHTML = `
                <td>
                    <div class="autocomplete-wrapper">
                        <input type="text" class="product-input" data-row="${itemCounter}" 
                               placeholder="Search product..." autocomplete="off">
                        <div class="autocomplete-list" id="product-suggestions-${itemCounter}"></div>
                        <div class="price-hint" id="price-hint-${itemCounter}"></div>
                    </div>
                </td>
                <td><input type="text" class="desc-input" placeholder="Optional"></td>
                <td>
                    <div class="autocomplete-wrapper">
                        <input type="text" class="unit-input" list="unit-list" placeholder="e.g., Nos" autocomplete="off">
                    </div>
                </td>
                <td>
                    <select class="gst-input" onchange="updateLineTotal(${itemCounter})" style="width: 100%; padding: 8px; border: 1px solid #ddd; border-radius: 8px;">
                        <option value="5">5%</option>
                        <option value="12">12%</option>
                        <option value="18" selected>18%</option>
                    </select>
                </td>
                <td><input type="number" class="price-input" data-row="${itemCounter}" value="0" step="0.01" 
                           onchange="updateLineTotal(${itemCounter})"></td>
                <td>
                    <div id="image-preview-${itemCounter}" style="margin-bottom: 4px; display: none;">
                        <img src="" style="width: 40px; height: 40px; object-fit: cover; border-radius: 4px;">
                    </div>
                    <button class="btn" style="padding: 4px 8px; font-size: 11px;" onclick="openImagePicker(${itemCounter})">🖼️ Pick</button>
                    <input type="hidden" class="image-url-input" id="image-url-${itemCounter}">
                </td>
                <td class="line-total" id="line-total-${itemCounter}">₹0.00</td>
                <td><button class="remove-btn" onclick="removeRow(${itemCounter})">×</button></td>
            `;
            tbody.appendChild(row);
            
            // Setup product autocomplete
            const productInput = row.querySelector('.product-input');
            setupProductAutocomplete(productInput, itemCounter);
        }
        
        function setupProductAutocomplete(input, rowId) {
            const suggestions = document.getElementById(`product-suggestions-${rowId}`);
            
            input.addEventListener('input', async (e) => {
                const query = e.target.value.trim();
                if (query.length < 2) {
                    suggestions.classList.remove('active');
                    return;
                }
                
                const clientName = document.getElementById('client-name').value.trim();
                const baseUrl = window.location.pathname.replace(/\/+$/, '');
                const res = await fetch(`${baseUrl}/api/products?q=${encodeURIComponent(query)}&client=${encodeURIComponent(clientName)}`);
                const products = await res.json();
                
                if (products.length === 0) {
                    suggestions.classList.remove('active');
                    return;
                }
                
                suggestions.innerHTML = products.map(p => `
                    <div class="autocomplete-item" onclick="selectProduct(${rowId}, ${JSON.stringify(p).replace(/"/g, '&quot;')})">
                        <div class="name">${escapeHtml(p.product)}${p.brand ? ' <span style="color:#c5a059;font-size:12px;">(' + escapeHtml(p.brand) + ')</span>' : ''}</div>
                        <div class="meta">${p.price_hint || ''}</div>
                        <div class="price-row">
                            <span class="price-tag">₹${p.suggested_price.toLocaleString('en-IN')}</span>
                            <span style="font-size: 11px; color: #888;">${p.price_source}</span>
                        </div>
                    </div>
                `).join('');
                suggestions.classList.add('active');
            });
            
            input.addEventListener('blur', () => {
                setTimeout(() => suggestions.classList.remove('active'), 200);
            });
        }
        
        function selectProduct(rowId, product) {
            const row = document.getElementById(`item-row-${rowId}`);
            row.querySelector('.product-input').value = product.product;
            row.querySelector('.price-input').value = product.suggested_price;
            
            // Show price hint
            const hint = document.getElementById(`price-hint-${rowId}`);
            hint.textContent = product.price_hint || '';
            hint.className = 'price-hint ' + (product.price_class || 'standard');
            
            document.getElementById(`product-suggestions-${rowId}`).classList.remove('active');
            updateLineTotal(rowId);
        }
        
        function updateLineTotal(rowId) {
            const row = document.getElementById(`item-row-${rowId}`);
            if (!row) return;
            
            const price = parseFloat(row.querySelector('.price-input').value) || 0;
            const total = price;
            
            document.getElementById(`line-total-${rowId}`).textContent = `₹${total.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            updateTotals();
        }
        
        function updateTotals() {
            let subtotal = 0;
            let gst5 = 0;
            let gst12 = 0;
            let gst18 = 0;

            document.querySelectorAll('[id^="item-row-"]').forEach(row => {
                const price = parseFloat(row.querySelector('.price-input')?.value) || 0;
                const gstPercent = parseFloat(row.querySelector('.gst-input')?.value) || 0;
                subtotal += price;
                const g = price * (gstPercent / 100);
                if (gstPercent === 5) gst5 += g;
                else if (gstPercent === 12) gst12 += g;
                else if (gstPercent === 18) gst18 += g;
                else {
                    // future slabs: treat as 18 bucket for now
                    gst18 += g;
                }
            });

            const gst = gst5 + gst12 + gst18;
            const grand = subtotal + gst;

            document.getElementById('subtotal').textContent = `₹${subtotal.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            document.getElementById('gst-5').textContent = `₹${gst5.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            document.getElementById('gst-12').textContent = `₹${gst12.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            document.getElementById('gst-18').textContent = `₹${gst18.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            document.getElementById('gst-amount').textContent = `₹${gst.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
            document.getElementById('grand-total').textContent = `₹${grand.toLocaleString('en-IN', {minimumFractionDigits: 2})}`;
        }
        
        function removeRow(rowId) {
            const row = document.getElementById(`item-row-${rowId}`);
            if (row) {
                row.remove();
                updateTotals();
            }
        }
        
        function refreshAllPriceHints() {
            // When client changes, we could refresh price hints
            // For MVP, user can re-select products to get updated hints
        }
        
        function clearForm() {
            document.getElementById('quote-id').value = '';
            document.getElementById('client-name').value = '';
            document.getElementById('client-contact').value = '';
            document.getElementById('client-address').value = '';
            document.getElementById('notes').value = '';
            document.getElementById('items-body').innerHTML = '';
            document.getElementById('quote-date').value = new Date().toISOString().split('T')[0];
            itemCounter = 0;
            updateTotals();
            addItemRow(); // Start with one empty row
        }
        
        function collectFormData() {
            const items = [];
            document.querySelectorAll('[id^="item-row-"]').forEach(row => {
                const product = row.querySelector('.product-input').value.trim();
                const desc = row.querySelector('.desc-input').value.trim();
                const unit = row.querySelector('.unit-input')?.value.trim() || '';
                const gst_percent = parseFloat(row.querySelector('.gst-input')?.value) || 18;
                const price = parseFloat(row.querySelector('.price-input').value) || 0;
                if (product && price > 0) {
                    // Quotes are always per-unit. Quantity is captured later in PO, not quote.
                    const image_url = row.querySelector(".image-url-input").value; items.push({ product, description: desc, unit, gst_percent, quantity: 1, unit_price: price, image_url });
                }
            });
            
            return {
                id: document.getElementById('quote-id').value,
                client_name: document.getElementById('client-name').value.trim(),
                client_contact: document.getElementById('client-contact').value.trim(),
                client_address: document.getElementById('client-address').value.trim(),
                quote_date: document.getElementById('quote-date').value,
                use_letterhead: document.getElementById('use-letterhead').checked,
                notes: document.getElementById('notes').value.trim(),
                items: items
            };
        }
        
        async function saveQuote() {
            const data = collectFormData();
            if (!data.client_name) {
                showStatus('Please enter client name', true);
                return;
            }
            if (data.items.length === 0) {
                showStatus('Please add at least one item', true);
                return;
            }

            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(baseUrl + '/api/quotes', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            if (res.ok) {
                showStatus('Quote saved successfully!');
                loadRecentQuotes();
            } else {
                showStatus('Failed to save quote', true);
            }
        }
        
        async function generateQuote() {
            const data = collectFormData();
            if (!data.client_name) {
                showStatus('Please enter client name', true);
                return;
            }
            if (data.items.length === 0) {
                showStatus('Please add at least one item', true);
                return;
            }
            
            showStatus('Generating PDF...');

            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(baseUrl + '/api/quotes/pdf', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            });
            
            if (res.ok) {
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `quote_${data.client_name.replace(/[^a-zA-Z0-9]/g, '_')}_${data.quote_date}.pdf`;
                a.click();
                URL.revokeObjectURL(url);
                showStatus('PDF downloaded!');
                loadRecentQuotes();
            } else {
                showStatus('Failed to generate PDF', true);
            }
        }
        
        async function shareWhatsApp() {
            const data = collectFormData();
            if (!data.client_name || data.items.length === 0) {
                showStatus('Add client and items first', true);
                return;
            }
            
            let msg = `*QUOTATION FROM BAJAJ SPORTS*%0A%0A`;
            msg += `*Client:* ${data.client_name}%0A`;
            msg += `*Date:* ${data.quote_date}%0A%0A`;
            
            data.items.forEach((item, i) => {
                msg += `${i+1}. *${item.product}*%0A`;
                msg += `   Rate (per unit): ₹${item.unit_price.toLocaleString()}%0A`;
            });
            
            const subtotal = data.items.reduce((sum, i) => sum + (i.unit_price), 0);
            const gst5 = data.items.reduce((sum, i) => sum + (i.gst_percent === 5 ? (i.unit_price * 0.05) : 0), 0);
            const gst12 = data.items.reduce((sum, i) => sum + (i.gst_percent === 12 ? (i.unit_price * 0.12) : 0), 0);
            const gst18 = data.items.reduce((sum, i) => sum + (i.gst_percent === 18 ? (i.unit_price * 0.18) : 0), 0);
            const gst = gst5 + gst12 + gst18;
            const grand = subtotal + gst;
            
            msg += `%0A*Subtotal (Taxable):* ₹${subtotal.toLocaleString()}`;
            msg += `%0A*GST @5%:* ₹${gst5.toLocaleString()}`;
            msg += `%0A*GST @12%:* ₹${gst12.toLocaleString()}`;
            msg += `%0A*GST @18%:* ₹${gst18.toLocaleString()}`;
            msg += `%0A*TOTAL:* ₹${grand.toLocaleString()}`;
            
            if (data.notes) msg += `%0A%0A*Notes:* ${data.notes}`;
            
            const phone = data.client_contact.replace(/[^0-9]/g, '');
            const url = `https://wa.me/${phone.length === 10 ? '91'+phone : phone}?text=${msg}`;
            window.open(url, '_blank');
        }
        async function loadRecentQuotes() {
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/quotes?limit=10`);
            const quotes = await res.json();
            
            const container = document.getElementById('recent-quotes');
            if (quotes.length === 0) {
                container.innerHTML = '<p style="color: #888; font-size: 14px; padding: 20px 0;">No quotations yet.</p>';
                return;
            }
            
            container.innerHTML = quotes.map(q => `
                <div class="quote-row">
                    <div class="quote-info" onclick="editQuote(${q.id})" style="cursor: pointer;">
                        <div class="client">${escapeHtml(q.client_name)}</div>
                        <div class="date">${q.quote_date}</div>
                    </div>
                    <div class="quote-amount">₹${q.grand_total.toLocaleString('en-IN', {minimumFractionDigits: 2})}</div>
                    <div class="btn-row" style="margin-top: 0;">
                        <button class="btn btn-secondary" style="padding: 6px 12px;" onclick="editQuote(${q.id})">Edit</button>
                        <a href="${baseUrl}/api/quotes/${q.id}/pdf" class="btn btn-secondary" style="padding: 6px 12px;">PDF</a>
                    </div>
                </div>
            `).join('');
        }

        async function editQuote(id) {
            showStatus('Loading quote...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/quotes/${id}`);
            if (!res.ok) {
                showStatus('Failed to load quote', true);
                return;
            }
            const q = await res.json();
            
            // Fill form
            document.getElementById('quote-id').value = q.id;
            document.getElementById('client-name').value = q.client_name;
            document.getElementById('client-contact').value = q.client_contact || '';
            document.getElementById('client-address').value = q.client_address || '';
            document.getElementById('quote-date').value = q.quote_date;
            if (document.getElementById('use-letterhead')) {
                document.getElementById('use-letterhead').checked = !!q.use_letterhead;
            }
            document.getElementById('notes').value = q.notes || '';
            
            // Fill items
            document.getElementById('items-body').innerHTML = '';
            itemCounter = 0;
            for (const item of q.items) {
                addItemRow();
                const row = document.getElementById(`item-row-${itemCounter}`);
                row.querySelector('.product-input').value = item.product_name;
                row.querySelector('.desc-input').value = item.description || '';
                row.querySelector('.price-input').value = item.unit_price;
                if (row.querySelector('.unit-input')) row.querySelector('.unit-input').value = item.unit || '';
                if (row.querySelector('.gst-input')) row.querySelector('.gst-input').value = String(item.gst_percent || 18);
                updateLineTotal(itemCounter);
            }
            
            window.scrollTo({ top: 0, behavior: 'smooth' });
            showStatus('Quote loaded for editing');
        }
        
        function showStatus(msg, isError = false) {
            const bar = document.getElementById('status-bar');
            bar.textContent = msg;
            bar.className = 'status-bar active' + (isError ? ' error' : '');
            setTimeout(() => bar.classList.remove('active'), 3000);
        }
        
        async function loadUnitTerms() {
            try {
                const baseUrl = window.location.pathname.replace(/\/+$/, '');
                const res = await fetch(baseUrl + '/api/units');
                const units = await res.json();
                const dl = document.getElementById('unit-list');
                if (!dl) return;
                dl.innerHTML = (units || []).map(u => `<option value="${escapeHtml(u)}"></option>`).join('');
            } catch (e) {
                console.warn('Could not load unit terms', e);
            }
        }

        // Initialize
        addItemRow();
        loadUnitTerms();
        loadRecentQuotes();
    </script>

    <!-- Image Picker Modal -->
    <div id="image-modal" class="card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2000; width: 500px; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
        <h2>Pick Product Image</h2>
        <div id="existing-images" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; max-height: 200px; overflow-y: auto; padding: 10px; border: 1px solid #eee; border-radius: 8px;">
            <p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 16px;">
            <label style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px;">Upload New Image</label>
            <input type="file" id="image-upload-file" accept="image/*" style="font-size: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
                <button class="btn btn-primary" onclick="uploadNewImage()">Upload & Use</button>
                <button class="btn btn-secondary" onclick="closeImagePicker()">Cancel</button>
            </div>
        </div>
    </div>
    <div id="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1999; display: none;" onclick="closeImagePicker()"></div>

    <script>
        let currentPickerRow = null;

        async function openImagePicker(rowId) {
            currentPickerRow = rowId;
            const product = document.querySelector(`#item-row-${rowId} .product-input`).value.trim();
            if (!product) {
                showStatus('Enter product name first', true);
                return;
            }

            document.getElementById('image-modal').style.display = 'block';
            document.getElementById('modal-overlay').style.display = 'block';

            // Load existing images
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/images/${encodeURIComponent(product)}`);
            const images = await res.json();
            
            const container = document.getElementById('existing-images');
            if (images.length > 0) {
                container.innerHTML = images.map(img => `
                    <div style="cursor: pointer; border: 2px solid transparent;" onclick="selectExistingImage('${img.url}')">
                        <img src="${baseUrl}/${img.url}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;">
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>';
            }
        }

        function closeImagePicker() {
            document.getElementById('image-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentPickerRow = null;
        }

        function selectExistingImage(url) {
            const preview = document.getElementById(`image-preview-${currentPickerRow}`);
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            preview.querySelector('img').src = `${baseUrl}/${url}`;
            preview.style.display = 'block';
            document.getElementById(`image-url-${currentPickerRow}`).value = url;
            closeImagePicker();
        }

        async function uploadNewImage() {
            const fileInput = document.getElementById('image-upload-file');
            if (!fileInput.files[0]) {
                alert('Pick a file first');
                return;
            }

            const product = document.querySelector(`#item-row-${currentPickerRow} .product-input`).value.trim();
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('product_name', product);
            formData.append('category', 'uncategorized'); // Can be improved to use product cat

            showStatus('Uploading image...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/upload-image`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const img = await res.json();
                selectExistingImage(img.url);
                showStatus('Image uploaded!');
            } else {
                showStatus('Upload failed', true);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(MAIN_HTML)

@app.get("/api/units")
async def get_unit_terms():
    # Return current unit terms for UI autocomplete
    return load_unit_terms()

@app.get("/api/clients")
async def search_clients(q: str = ""):
    """Search clients by name prefix."""
    q_lower = q.lower().strip()
    if len(q_lower) < 2:
        return []
    
    matches = []
    for c in CUSTOMERS:
        name = c.get("customer", "")
        if q_lower in name.lower():
            matches.append({
                "name": name,
                "address": c.get("address", ""),
                "phone": c.get("phone", ""),
                "gstin": c.get("gstin", ""),
                "purchase_count": len(c.get("purchases", []))
            })
            if len(matches) >= 10:
                break
    return matches

@app.get("/api/products")

@app.get("/api/images/{product_name}")
async def get_product_images(product_name: str):
    if not PRODUCT_IMAGES_REGISTRY.exists():
        return []
    registry = json.loads(PRODUCT_IMAGES_REGISTRY.read_text())
    return registry.get(product_name.lower(), [])

@app.post("/api/upload-image")
async def upload_image(product_name: str = Form(...), category: str = Form("uncategorized"), file: UploadFile = File(...)):
    cat_dir = IMAGES_DIR / category.lower().replace(" ", "_")
    cat_dir.mkdir(parents=True, exist_ok=True)
    
    # Save file with hash to avoid collisions
    contents = await file.read()
    file_hash = hashlib.md5(contents).hexdigest()[:8]
    ext = Path(file.filename).suffix or ".jpg"
    safe_name = product_name.lower().replace(" ", "_")[:50]
    filename = f"{safe_name}_{file_hash}{ext}"
    file_path = cat_dir / filename
    
    file_path.write_bytes(contents)
    
    # Update registry
    registry = {}
    if PRODUCT_IMAGES_REGISTRY.exists():
        try:
            registry = json.loads(PRODUCT_IMAGES_REGISTRY.read_text())
        except: pass
        
    p_key = product_name.lower()
    img_entry = {
        "url": f"static/images/{category.lower().replace(' ', '_')}/{filename}",
        "filename": filename,
        "category": category,
        "uploaded_at": datetime.now().isoformat()
    }
    
    if p_key not in registry:
        registry[p_key] = []
    registry[p_key].append(img_entry)
    PRODUCT_IMAGES_REGISTRY.write_text(json.dumps(registry, indent=2))
    
    return img_entry

async def search_products(q: str = "", client: str = ""):
    """Search products with pricing suggestions based on client."""
    q_lower = q.lower().strip()
    if len(q_lower) < 2:
        return []
    
    client_lower = client.lower().strip() if client else ""
    
    matches = []
    for p in CATALOG:
        name = p.get("product", "")
        if q_lower in name.lower():
            # Determine best price
            pricing_tiers = p.get("pricing_tiers", [])
            suggested_price = p.get("min_price", 0)
            price_source = ""
            price_hint = ""
            price_class = "standard"
            
            # Check if client has bought this before
            if client_lower and pricing_tiers:
                for tier in pricing_tiers:
                    customers = tier.get("customers", [])
                    for cust in customers:
                        if client_lower in cust.lower():
                            suggested_price = tier.get("price", suggested_price)
                            price_source = "(last price to this client)"
                            price_hint = f"Last sold to {client} at ₹{suggested_price:,.0f}"
                            price_class = "last-client"
                            break
                    if price_class == "last-client":
                        break
            
            # If no client match, show price range
            if not price_source and pricing_tiers:
                min_p = p.get("min_price", 0)
                max_p = p.get("max_price", 0)
                suggested_price = min_p
                if min_p != max_p:
                    price_source = f"(range: ₹{min_p:,.0f} - ₹{max_p:,.0f})"
                    price_hint = f"Quoted {p.get('times_quoted', 0)} times, ₹{min_p:,.0f} - ₹{max_p:,.0f}"
                else:
                    price_source = f"(standard)"
                price_class = "other-client"
            
            matches.append({
                "product": name,
                "brand": p.get("brand", ""),
                "hsn_code": p.get("hsn_code", ""),
                "categories": p.get("categories", []),
                "suggested_price": suggested_price,
                "price_source": price_source,
                "price_hint": price_hint,
                "price_class": price_class,
                "times_quoted": p.get("times_quoted", 0)
            })
            
            if len(matches) >= 15:
                break
    
    return matches

@app.get("/api/quotes")
async def list_quotes(limit: int = 20):
    """List recent quotes."""
    with db() as conn:
        rows = conn.execute("""
            SELECT id, client_name, quote_date, grand_total, pdf_path
            FROM quotes
            ORDER BY id DESC
            LIMIT ?
        """, (limit,)).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/quotes/{quote_id}")
async def get_quote(quote_id: int):
    """Fetch a single quote with items."""
    with db() as conn:
        quote = conn.execute("SELECT * FROM quotes WHERE id = ?", (quote_id,)).fetchone()
        if not quote:
            raise HTTPException(404, "Quote not found")
        items = conn.execute("SELECT * FROM quote_items WHERE quote_id = ?", (quote_id,)).fetchall()
        
        data = dict(quote)
        data["items"] = [dict(i) for i in items]
        return data

@app.post("/api/quotes")
async def create_quote(request: Request):
    """Save or update a quote in the database."""
    data = await request.json()
    quote_id = data.get("id")
    
    items = data.get("items", [])

    # Quotes are always per-unit. Quantity is handled later during PO.
    subtotal = sum(i.get("unit_price", 0) for i in items)

    # Per-line GST slabs (currently 5%, 12% and 18%)
    gst5 = sum(i.get("unit_price", 0) * 0.05 for i in items if float(i.get("gst_percent", 18) or 0) == 5)
    gst12 = sum(i.get("unit_price", 0) * 0.12 for i in items if float(i.get("gst_percent", 18) or 0) == 12)
    gst18 = sum(i.get("unit_price", 0) * 0.18 for i in items if float(i.get("gst_percent", 18) or 0) == 18)
    gst = gst5 + gst12 + gst18

    grand = subtotal + gst

    # Normalize + persist unit terms for autocomplete
    for it in items:
        try:
            register_unit_term(it.get('unit') or '')
        except Exception:
            pass
    
    with db() as conn:
        if quote_id:
            # Update existing
            conn.execute("""
                UPDATE quotes SET 
                    client_name=?, client_address=?, client_contact=?, quote_date=?, 
                    total_amount=?, gst_amount=?, grand_total=?, notes=?
                WHERE id=?
            """, (
                data.get("client_name"),
                data.get("client_address"),
                data.get("client_contact"),
                data.get("quote_date"),
                subtotal,
                gst,
                grand,
                data.get("notes"),
                quote_id
            ))
            # Refresh items: delete and re-insert
            conn.execute("DELETE FROM quote_items WHERE quote_id=?", (quote_id,))
        else:
            # Insert new
            cur = conn.execute("""
                INSERT INTO quotes (client_name, client_address, client_contact, quote_date, 
                                  total_amount, gst_amount, grand_total, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("client_name"),
                data.get("client_address"),
                data.get("client_contact"),
                data.get("quote_date"),
                subtotal,
                gst,
                grand,
                data.get("notes"),
                datetime.now().isoformat()
            ))
            quote_id = cur.lastrowid
        
        for item in items:
            # Force per-unit quote semantics.
            qty = 1
            price = item.get("unit_price", 0)
            line_total = price
            unit = item.get("unit") or ""
            gst_percent = float(item.get("gst_percent", 18) or 18)

            conn.execute("""
                INSERT INTO quote_items (quote_id, product_name, description, unit, gst_percent, quantity,
                                        unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                quote_id,
                item.get("product"),
                item.get("description"),
                unit,
                gst_percent,
                qty,
                price,
                line_total
            ))

            # Update unit terms store for autocomplete
            try:
                register_unit_term(unit)
            except Exception:
                pass
        
        conn.commit()
    
    return {"id": quote_id, "status": "saved"}

@app.post("/api/quotes/pdf")
async def generate_pdf(request: Request):
    """Generate PDF for a quote."""
    data = await request.json()
    
    items = data.get("items", [])
    # Quotes are always per-unit. Quantity is handled later during PO.
    subtotal = sum(i.get("unit_price", 0) for i in items)

    gst5 = sum(i.get("unit_price", 0) * 0.05 for i in items if float(i.get("gst_percent", 18) or 0) == 5)
    gst12 = sum(i.get("unit_price", 0) * 0.12 for i in items if float(i.get("gst_percent", 18) or 0) == 12)
    gst18 = sum(i.get("unit_price", 0) * 0.18 for i in items if float(i.get("gst_percent", 18) or 0) == 18)
    gst = gst5 + gst12 + gst18

    grand = subtotal + gst
    
    # Build HTML for PDF
    items_html = ""
    for idx, item in enumerate(items, 1):
        # Per-unit quote
        price = item.get("unit_price", 0)
        total = price
        img_url = item.get("image_url")
        img_html = ""
        if img_url:
            # Construct absolute path for WeasyPrint
            # img_url is static/images/...
            local_path = BASE_DIR / img_url
            if local_path.exists():
                img_html = f'<img src="{local_path.as_uri()}" style="width: 60px; height: 60px; object-fit: cover; border-radius: 4px; margin-right: 10px; vertical-align: middle;">'
        items_html += f"""
        <tr>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">{idx}</td>
            <td style="padding: 12px; border-bottom: 1px solid #eee;">
                <div style="display: flex; align-items: center;">
                    {img_html}
                    <div>
                        <strong>{item.get('product', '')}</strong>
                        {f"<br><small style='color:#666'>{item.get('description','')}</small>" if item.get('description') else ''}
                    </div>
                </div>
            </td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">{item.get('unit','') or ''}</td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: center;">{int(float(item.get('gst_percent',18) or 18))}</td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">₹{price:,.2f}</td>
            <td style="padding: 12px; border-bottom: 1px solid #eee; text-align: right;">₹{total:,.2f}</td>
        </tr>
        """


    # Check if we should leave space for letterhead
    use_letterhead = data.get("use_letterhead", False)
    header_style = "display: none;" if use_letterhead else "display: block;"
    body_margin = "45mm" if use_letterhead else "20mm"
    pdf_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            @page {{ size: A4; margin: [[BODY_MARGIN]] 20mm 20mm 20mm; }}
            body {{ font-family: Arial, sans-serif; font-size: 12px; color: #333; }}
            .header {{ text-align: center; margin-bottom: 30px; padding-bottom: 20px; border-bottom: 2px solid #1a237e; [[HEADER_STYLE]] }}
            .header h1 {{ color: #1a237e; margin: 0; font-size: 24px; }}
            .header p {{ margin: 5px 0 0; color: #666; }}
            .info-grid {{ display: flex; justify-content: space-between; margin-bottom: 30px; }}
            .info-box {{ width: 48%; }}
            .info-box h3 {{ font-size: 12px; color: #888; margin: 0 0 8px; text-transform: uppercase; }}
            .info-box p {{ margin: 4px 0; }}
            table {{ width: 100%; border-collapse: collapse; margin-bottom: 30px; }}
            th {{ background: #1a237e; color: white; padding: 12px; text-align: left; font-weight: 500; }}
            .totals {{ width: 300px; margin-left: auto; }}
            .totals tr td {{ padding: 8px; }}
            .totals .grand {{ font-size: 16px; font-weight: bold; color: #1a237e; border-top: 2px solid #1a237e; }}
            .notes {{ margin-top: 30px; padding: 15px; background: #f5f5f5; border-radius: 4px; }}
            .footer {{ margin-top: 40px; text-align: center; color: #888; font-size: 10px; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>🏏 BAJAJ SPORTS</h1>
            <p>27 Municipal Market, Connaught Circus, New Delhi 110001</p>
            <p>Phone: +91-11-23742070 | info@bajajsports.com | www.bajajsports.com</p>
            <p>GST No. 07AAFPB2487F1ZY | MSME No. UDYAM-DL-01-0008669</p>
            <p>ISO 9001:2015</p>
        </div>
        
        <h2 style="color: #1a237e; text-align: center; margin-bottom: 20px;">QUOTATION</h2>
        
        <div style="display: flex; justify-content: space-between; margin-bottom: 30px;">
            <div style="width: 48%;">
                <h3 style="font-size: 11px; color: #888; margin: 0 0 8px; text-transform: uppercase;">Bill To</h3>
                <p style="margin: 4px 0; font-weight: bold;">[[CLIENT_NAME]]</p>
                <p style="margin: 4px 0;">[[CLIENT_ADDRESS]]</p>
                <p style="margin: 4px 0;">[[CLIENT_CONTACT]]</p>
            </div>
            <div style="width: 48%; text-align: right;">
                <h3 style="font-size: 11px; color: #888; margin: 0 0 8px; text-transform: uppercase;">Quote Details</h3>
                <p style="margin: 4px 0;"><strong>Date:</strong> [[QUOTE_DATE]]</p>
                <p style="margin: 4px 0;"><strong>Quote #:</strong> BSQ-[[QUOTE_ID]]</p>
            </div>
        </div>
        
        <table>
            <thead>
                <tr>
                    <th style="width: 5%;">#</th>
                    <th style="width: 45%;">Item Description</th>
                    <th style="width: 12%; text-align: center;">Unit</th>
                    <th style="width: 8%; text-align: center;">GST%</th>
                    <th style="width: 15%; text-align: right;">Unit Price</th>
                    <th style="width: 15%; text-align: right;">Amount</th>
                </tr>
            </thead>
            <tbody>
                [[ITEMS_HTML]]
            </tbody>
        </table>
        
        <table class="totals">
            <tr>
                <td>Subtotal (Taxable):</td>
                <td style="text-align: right;">₹[[SUBTOTAL]]</td>
            </tr>
            <tr>
                <td>GST @5%:</td>
                <td style="text-align: right;">₹[[GST5]]</td>
            </tr>
            <tr>
                <td>GST @12%:</td>
                <td style="text-align: right;">₹[[GST12]]</td>
            </tr>
            <tr>
                <td>GST @18%:</td>
                <td style="text-align: right;">₹[[GST18]]</td>
            </tr>
            <tr>
                <td>Total GST:</td>
                <td style="text-align: right;">₹[[TOTAL_GST]]</td>
            </tr>
            <tr class="grand">
                <td>Grand Total:</td>
                <td style="text-align: right;">₹[[GRAND]]</td>
            </tr>
        </table>
        
        
        [[NOTES_HTML]]
        
        [[PAYMENT_HTML]]
        [[TRANSPORT_HTML]]
        [[INSTALL_HTML]]

        
        <div class="footer">
            <p>This is a computer-generated quotation. Prices are valid for 30 days from the date of issue.</p>
            <p>Terms: GST Extra | Delivery: As per agreement | Payment: As per terms</p>
        </div>
    
    <!-- Image Picker Modal -->
    <div id="image-modal" class="card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2000; width: 500px; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
        <h2>Pick Product Image</h2>
        <div id="existing-images" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; max-height: 200px; overflow-y: auto; padding: 10px; border: 1px solid #eee; border-radius: 8px;">
            <p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 16px;">
            <label style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px;">Upload New Image</label>
            <input type="file" id="image-upload-file" accept="image/*" style="font-size: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
                <button class="btn btn-primary" onclick="uploadNewImage()">Upload & Use</button>
                <button class="btn btn-secondary" onclick="closeImagePicker()">Cancel</button>
            </div>
        </div>
    </div>
    <div id="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1999; display: none;" onclick="closeImagePicker()"></div>

    <script>
        let currentPickerRow = null;

        async function openImagePicker(rowId) {
            currentPickerRow = rowId;
            const product = document.querySelector(`#item-row-${rowId} .product-input`).value.trim();
            if (!product) {
                showStatus('Enter product name first', true);
                return;
            }

            document.getElementById('image-modal').style.display = 'block';
            document.getElementById('modal-overlay').style.display = 'block';

            // Load existing images
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/images/${encodeURIComponent(product)}`);
            const images = await res.json();
            
            const container = document.getElementById('existing-images');
            if (images.length > 0) {
                container.innerHTML = images.map(img => `
                    <div style="cursor: pointer; border: 2px solid transparent;" onclick="selectExistingImage('${img.url}')">
                        <img src="${baseUrl}/${img.url}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;">
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>';
            }
        }

        function closeImagePicker() {
            document.getElementById('image-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentPickerRow = null;
        }

        function selectExistingImage(url) {
            const preview = document.getElementById(`image-preview-${currentPickerRow}`);
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            preview.querySelector('img').src = `${baseUrl}/${url}`;
            preview.style.display = 'block';
            document.getElementById(`image-url-${currentPickerRow}`).value = url;
            closeImagePicker();
        }

        async function uploadNewImage() {
            const fileInput = document.getElementById('image-upload-file');
            if (!fileInput.files[0]) {
                alert('Pick a file first');
                return;
            }

            const product = document.querySelector(`#item-row-${currentPickerRow} .product-input`).value.trim();
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('product_name', product);
            formData.append('category', 'uncategorized'); // Can be improved to use product cat

            showStatus('Uploading image...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/upload-image`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const img = await res.json();
                selectExistingImage(img.url);
                showStatus('Image uploaded!');
            } else {
                showStatus('Upload failed', true);
            }
        }
    </script>
</body>
    </html>
"""
    pdf_html = pdf_html.replace('[[BODY_MARGIN]]', body_margin)\
                       .replace('[[HEADER_STYLE]]', header_style)\
                       .replace('[[CLIENT_NAME]]', data.get('client_name', ''))\
                       .replace('[[CLIENT_ADDRESS]]', data.get('client_address', '').replace('\n', '<br>'))\
                       .replace('[[CLIENT_CONTACT]]', data.get('client_contact', ''))\
                       .replace('[[QUOTE_DATE]]', data.get('quote_date', ''))\
                       .replace('[[QUOTE_ID]]', datetime.now().strftime('%Y%m%d%H%M'))\
                       .replace('[[ITEMS_HTML]]', items_html)\
                       .replace('[[SUBTOTAL]]', f"{subtotal:,.2f}")\
                       .replace('[[GST5]]', f"{gst5:,.2f}")\
                       .replace('[[GST12]]', f"{gst12:,.2f}")\
                       .replace('[[GST18]]', f"{gst18:,.2f}")\
                       .replace('[[TOTAL_GST]]', f"{gst:,.2f}")\
                       .replace('[[GRAND]]', f"{grand:,.2f}")
    
    nl_br = '\n'
    notes_html = f'<div class="notes"><strong>Notes:</strong><br>{data.get("notes", "").replace(nl_br, "<br>")}</div>' if data.get("notes") else ''
    pdf_html = pdf_html.replace('[[NOTES_HTML]]', notes_html)
    
    pay_html = f'<div style="margin-top: 20px;"><strong>Payment Terms:</strong> {data.get("payment_terms")}</div>' if data.get("payment_terms") else ''
    pdf_html = pdf_html.replace('[[PAYMENT_HTML]]', pay_html)
    
    trans_html = f'<div style="margin-top: 10px;"><strong>Transportation:</strong> {data.get("transport_charges")}</div>' if data.get("transport_charges") else ''
    pdf_html = pdf_html.replace('[[TRANSPORT_HTML]]', trans_html)
    
    inst_html = f'<div style="margin-top: 10px;"><strong>Installation:</strong> {data.get("installation_charges")}</div>' if data.get("installation_charges") else ''
    pdf_html = pdf_html.replace('[[INSTALL_HTML]]', inst_html)

    
    # Try WeasyPrint, fallback to returning HTML
    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=pdf_html).write_pdf()
        
        from fastapi.responses import Response
        return Response(content=pdf_bytes, media_type="application/pdf")
    except ImportError:
        # WeasyPrint not installed - return HTML for now
        return HTMLResponse(pdf_html, headers={
            "Content-Disposition": f"attachment; filename=quote_{data.get('quote_date', 'draft')}.html"
        })

@app.get("/api/quotes/{quote_id}/pdf")
async def get_quote_pdf(quote_id: int):
    """Get PDF for a saved quote."""
    with db() as conn:
        row = conn.execute("SELECT pdf_path FROM quotes WHERE id = ?", (quote_id,)).fetchone()
        if not row or not row["pdf_path"]:
            raise HTTPException(404, "PDF not found")
        return FileResponse(row["pdf_path"], media_type="application/pdf")

@app.get("/source-pdf-page1/{filename}")
async def get_source_pdf_page1(filename: str):
    """Serve ONLY the first page of the original PDF as an image."""
    search_paths = [
        Path("/home/sachin/work/bajaj/data/pdf"),
        Path("/home/sachin/work/bajaj/extracted"),
        Path("/home/sachin/work/bajaj/data/pdf/more-pdf"),
        Path("/home/sachin/work/bajaj/data/pdf/2026/01")
    ]
    
    target_path = None
    for base in search_paths:
        target = base / filename
        if target.exists():
            target_path = target
            break
            
    if not target_path:
        all_pdfs = list(Path("/home/sachin/work/bajaj/data/pdf").rglob(filename))
        if all_pdfs:
            target_path = all_pdfs[0]

    if not target_path:
        raise HTTPException(404, "Source PDF not found")

    try:
        import fitz
        doc = fitz.open(str(target_path))
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2)) # 2x zoom for clarity
        img_data = pix.tobytes("png")
        doc.close()
        return Response(content=img_data, media_type="image/png")
    except Exception as e:
        print(f"Image conversion error: {e}")
        raise HTTPException(500, "Could not convert PDF page")

@app.get("/source-pdf/{filename}")
async def get_source_pdf(filename: str):
    """Serve original source PDFs for auditing."""
    # Search in all potential source directories
    search_paths = [
        Path("/home/sachin/work/bajaj/data/pdf"),
        Path("/home/sachin/work/bajaj/extracted"),
        Path("/home/sachin/work/bajaj/data/pdf/more-pdf"),
        Path("/home/sachin/work/bajaj/data/pdf/2026/01")
    ]
    
    for base in search_paths:
        target = base / filename
        if target.exists():
            return FileResponse(target, media_type="application/pdf")
            
    # Recursive search as fallback
    all_pdfs = Path("/home/sachin/work/bajaj/data/pdf").rglob(filename)
    for p in all_pdfs:
        return FileResponse(p, media_type="application/pdf")
        
    raise HTTPException(404, "Source PDF not found")

@app.get("/offline-export")
async def get_offline_export():
    path = Path("/home/sachin/work/bajaj/BAJAJ_OFFLINE_DATA.html")
    if not path.exists():
        raise HTTPException(404, "Export not found. Run generate_offline.py first.")
    return FileResponse(path)

DIRECTORY_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Bajaj - Client Directory</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #f2f2f7; color: #1c1c1e; padding-top: 120px; }
        
        .header-wrapper {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            z-index: 1000;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .nav-header { 
            background: #111; color: white; padding: 12px 16px; 
            border-bottom: 3px solid #c5a059; 
            display: flex; align-items: center; gap: 12px;
        }
        .nav-header img { height: 32px; max-width: 120px; object-fit: contain; }
        .nav-header h1 { font-size: 17px; font-weight: 700; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .nav-links { display: flex; gap: 10px; }
        .nav-links a { color: #c5a059; text-decoration: none; font-size: 12px; font-weight: 600; opacity: 0.8; }
        .nav-links a:hover { opacity: 1; }
        .nav-links a.active { opacity: 1; border-bottom: 2px solid #c5a059; }
        
        .search-container { 
            padding: 12px 16px; background: white; 
            border-bottom: 1px solid #d1d1d6; 
        }
        .search-bar { 
            width: 100%; padding: 10px 12px; background: #e9e9eb; 
            border: none; border-radius: 10px; font-size: 16px; outline: none; 
        }
        
        .client-list { padding: 12px; display: grid; gap: 12px; width: 100%; }
        .client-card { 
            background: white; border-radius: 12px; padding: 16px; 
            box-shadow: 0 1px 3px rgba(0,0,0,0.1); 
            border: 1px solid #e5e5ea; 
            position: relative;
            width: 100%;
            overflow: hidden;
        }
        .client-card:active { background: #f9f9f9; transform: scale(0.98); }
        .client-name { 
            font-size: 17px; font-weight: 700; color: #111; 
            margin-bottom: 4px; display: block;
            word-wrap: break-word; overflow-wrap: break-word;
        }
        .client-addr { 
            font-size: 13px; color: #666; line-height: 1.4; 
            display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; 
            overflow: hidden; margin-bottom: 8px;
            word-wrap: break-word;
        }
        .client-meta { 
            display: flex; justify-content: space-between; align-items: flex-end; 
            margin-top: 12px; padding-top: 12px; border-top: 1px solid #f2f2f7;
            gap: 8px;
        }
        .meta-group { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
        .meta-label { font-size: 10px; font-weight: 700; color: #8e8e93; text-transform: uppercase; }
        .meta-value { 
            font-size: 12px; font-weight: 600; color: #111; 
            white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
        }
        .last-quote { color: #c5a059; }
        
        .empty-state { padding: 40px; text-align: center; color: #8e8e93; font-size: 15px; }
        .badge { background: #f2f2f7; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; color: #111; }
    </style>
</head>
<body>
    <div class="header-wrapper">
        <div class="nav-header">
            <img src="static/logo.png" alt="Logo">
            <h1>Client Directory</h1>
            <div class="badge" id="total-count">0</div>
            <div class="nav-links" id="nav-links"></div>
            <script>
            (function(){
                const p = window.location.pathname.replace(/\/+$/, '');
                const b = p.replace(/\/(directory|products|audit)$/, '') || '';
                document.getElementById('nav-links').innerHTML =
                    '<a href="'+b+'/">Quotes</a>' +
                    '<a href="'+b+'/directory" class="active">Directory</a>' +
                    '<a href="'+b+'/products">Products</a>' +
                    '<a href="'+b+'/audit">Audit</a>';
            })();
            </script>
        </div>
        
        <div class="search-container">
            <input type="text" class="search-bar" id="search-input" placeholder="Search clients, address, phone..." autocomplete="off">
        </div>
    </div>
    
    <div class="client-list" id="client-list">
        <div class="empty-state">Loading directory...</div>
    </div>

    <div style="text-align: center; padding: 20px; font-size: 12px; color: #8e8e93;">
        Automated by <a href="https://bluepanda.in" target="_blank" style="color: #c5a059; text-decoration: none; font-weight: bold;">BluePanda</a>
    </div>

    <script>
        let allClients = [];
        const listEl = document.getElementById('client-list');
        const countEl = document.getElementById('total-count');
        const searchEl = document.getElementById('search-input');

        async function loadDirectory() {
            try {
                const apiPath = window.location.pathname.replace(/\/directory\/?$/, '') + '/api/directory';
                console.log('Fetching directory from:', apiPath);
                const res = await fetch(apiPath);
                allClients = await res.json();
                renderClients(allClients);
            } catch (e) {
                console.error(e);
                listEl.innerHTML = '<div class="empty-state">Error loading directory</div>';
            }
        }

        function renderClients(clients) {
            countEl.textContent = clients.length;
            if (clients.length === 0) {
                listEl.innerHTML = '<div class="empty-state">No clients found</div>';
                return;
            }
            
            listEl.innerHTML = clients.map(c => `
                <div class="client-card">
                    <span class="client-name">${escapeHtml(c.name)}</span>
                    <p class="client-addr">${escapeHtml(c.address || 'No address saved')}</p>
                    <div class="client-meta">
                        <div class="meta-group">
                            <span class="meta-label">Phone</span>
                            <span class="meta-value">${escapeHtml(c.phone || '--')}</span>
                        </div>
                        <div class="meta-group" style="text-align: right;">
                            <span class="meta-label">Last Quote</span>
                            <span class="meta-value last-quote">${escapeHtml(c.last_quote || 'Never')}</span>
                        </div>
                    </div>
                </div>
            `).join('');
        }

        function escapeHtml(str) {
            return String(str).replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":\"&#39;\"}[c]));
        }

        searchEl.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase().trim();
            const filtered = allClients.filter(c => 
                c.name.toLowerCase().includes(q) || 
                (c.address && c.address.toLowerCase().includes(q)) ||
                (c.phone && c.phone.includes(q))
            );
            renderClients(filtered);
        });

        loadDirectory();
    </script>

    <!-- Image Picker Modal -->
    <div id="image-modal" class="card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2000; width: 500px; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
        <h2>Pick Product Image</h2>
        <div id="existing-images" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; max-height: 200px; overflow-y: auto; padding: 10px; border: 1px solid #eee; border-radius: 8px;">
            <p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 16px;">
            <label style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px;">Upload New Image</label>
            <input type="file" id="image-upload-file" accept="image/*" style="font-size: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
                <button class="btn btn-primary" onclick="uploadNewImage()">Upload & Use</button>
                <button class="btn btn-secondary" onclick="closeImagePicker()">Cancel</button>
            </div>
        </div>
    </div>
    <div id="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1999; display: none;" onclick="closeImagePicker()"></div>

    <script>
        let currentPickerRow = null;

        async function openImagePicker(rowId) {
            currentPickerRow = rowId;
            const product = document.querySelector(`#item-row-${rowId} .product-input`).value.trim();
            if (!product) {
                showStatus('Enter product name first', true);
                return;
            }

            document.getElementById('image-modal').style.display = 'block';
            document.getElementById('modal-overlay').style.display = 'block';

            // Load existing images
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/images/${encodeURIComponent(product)}`);
            const images = await res.json();
            
            const container = document.getElementById('existing-images');
            if (images.length > 0) {
                container.innerHTML = images.map(img => `
                    <div style="cursor: pointer; border: 2px solid transparent;" onclick="selectExistingImage('${img.url}')">
                        <img src="${baseUrl}/${img.url}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;">
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>';
            }
        }

        function closeImagePicker() {
            document.getElementById('image-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentPickerRow = null;
        }

        function selectExistingImage(url) {
            const preview = document.getElementById(`image-preview-${currentPickerRow}`);
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            preview.querySelector('img').src = `${baseUrl}/${url}`;
            preview.style.display = 'block';
            document.getElementById(`image-url-${currentPickerRow}`).value = url;
            closeImagePicker();
        }

        async function uploadNewImage() {
            const fileInput = document.getElementById('image-upload-file');
            if (!fileInput.files[0]) {
                alert('Pick a file first');
                return;
            }

            const product = document.querySelector(`#item-row-${currentPickerRow} .product-input`).value.trim();
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('product_name', product);
            formData.append('category', 'uncategorized'); // Can be improved to use product cat

            showStatus('Uploading image...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/upload-image`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const img = await res.json();
                selectExistingImage(img.url);
                showStatus('Image uploaded!');
            } else {
                showStatus('Upload failed', true);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/directory", response_class=HTMLResponse)
async def client_directory():
    return HTMLResponse(DIRECTORY_HTML)

PRODUCTS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
    <title>Bajaj - Product Catalog</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; -webkit-tap-highlight-color: transparent; }
        body { font-family: -apple-system, system-ui, sans-serif; background: #f2f2f7; color: #1c1c1e; padding-top: 172px; }

        .header-wrapper {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            z-index: 1000;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }

        .nav-header {
            background: #111; color: white; padding: 12px 16px;
            border-bottom: 3px solid #c5a059;
            display: flex; align-items: center; gap: 12px;
        }
        .nav-header img { height: 32px; max-width: 120px; object-fit: contain; }
        .nav-header h1 { font-size: 17px; font-weight: 700; flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .nav-links { display: flex; gap: 10px; }
        .nav-links a { color: #c5a059; text-decoration: none; font-size: 12px; font-weight: 600; opacity: 0.8; }
        .nav-links a:hover { opacity: 1; }
        .nav-links a.active { opacity: 1; border-bottom: 2px solid #c5a059; }

        .badge { background: #f2f2f7; padding: 4px 8px; border-radius: 6px; font-size: 11px; font-weight: 700; color: #111; }

        .filters {
            padding: 12px 16px; background: white;
            border-bottom: 1px solid #d1d1d6;
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
        .search-bar {
            width: 100%; padding: 10px 12px; background: #e9e9eb;
            border: none; border-radius: 10px; font-size: 16px; outline: none;
        }
        .row {
            display: grid;
            grid-template-columns: 1fr;
            gap: 10px;
        }
        @media (min-width: 560px) {
            .row { grid-template-columns: 1fr 1fr 1fr; }
        }
        select {
            width: 100%;
            padding: 10px 12px;
            border-radius: 10px;
            border: 1px solid #d1d1d6;
            font-size: 15px;
            background: white;
            outline: none;
        }

        .list { padding: 12px; display: grid; gap: 12px; width: 100%; }
        .card {
            background: white; border-radius: 12px; padding: 16px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            border: 1px solid #e5e5ea;
            width: 100%;
            overflow: hidden;
        }
        .name { font-size: 16px; font-weight: 800; color: #111; margin-bottom: 6px; word-wrap: break-word; overflow-wrap: break-word; }
        .sub { font-size: 12px; color: #666; line-height: 1.4; word-wrap: break-word; overflow-wrap: break-word; }
        .meta {
            display: flex; justify-content: space-between; align-items: flex-end;
            margin-top: 12px; padding-top: 12px; border-top: 1px solid #f2f2f7;
            gap: 10px;
        }
        .meta-col { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
        .label { font-size: 10px; font-weight: 800; color: #8e8e93; text-transform: uppercase; letter-spacing: 0.6px; }
        .value { font-size: 12px; font-weight: 700; color: #111; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
        .value.price { color: #c5a059; }

        .chip-row { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
        .chip { background: #f2f2f7; color: #111; padding: 4px 8px; border-radius: 999px; font-size: 11px; font-weight: 700; }

        .empty { padding: 40px; text-align: center; color: #8e8e93; font-size: 15px; }
    </style>
</head>
<body>
    <div class="header-wrapper">
        <div class="nav-header">
            <img src="static/logo.png" alt="Logo">
            <h1>Products</h1>
            <div class="badge" id="total-count">0</div>
            <div class="nav-links" id="nav-links"></div>
            <script>
            (function(){
                const p = window.location.pathname.replace(/\/+$/, '');
                const b = p.replace(/\/(directory|products|audit)$/, '') || '';
                document.getElementById('nav-links').innerHTML =
                    '<a href="'+b+'/">Quotes</a>' +
                    '<a href="'+b+'/directory">Directory</a>' +
                    '<a href="'+b+'/products" class="active">Products</a>' +
                    '<a href="'+b+'/audit">Audit</a>';
            })();
            </script>
        </div>
        <div class="filters">
            <input type="text" class="search-bar" id="search" placeholder="Search product, brand, HSN..." autocomplete="off">
            <div class="row">
                <select id="category">
                    <option value="">All categories</option>
                </select>
                <select id="brand">
                    <option value="">All brands</option>
                </select>
                <select id="sort">
                    <option value="name_asc">Sort: Name (A→Z)</option>
                    <option value="price_asc">Sort: Price (Low→High)</option>
                    <option value="price_desc">Sort: Price (High→Low)</option>
                    <option value="quoted_desc">Sort: Times Quoted (High→Low)</option>
                </select>
            </div>
        </div>
    </div>

    <div class="list" id="list">
        <div class="empty">Loading products...</div>
    </div>

    <div style="text-align: center; padding: 20px; font-size: 12px; color: #8e8e93;">
        Automated by <a href="https://bluepanda.in" target="_blank" style="color: #c5a059; text-decoration: none; font-weight: bold;">BluePanda</a>
    </div>

    <script>
        let allProducts = [];
        let allCategories = [];
        let allBrands = [];

        const listEl = document.getElementById('list');
        const countEl = document.getElementById('total-count');
        const searchEl = document.getElementById('search');
        const catEl = document.getElementById('category');
        const brandEl = document.getElementById('brand');
        const sortEl = document.getElementById('sort');

        async function loadProducts() {
            try {
                const apiPath = window.location.pathname.replace(/\/products\/?$/, '') + '/api/products-list';
                const res = await fetch(apiPath);
                const data = await res.json();
                allProducts = data.products || [];
                allCategories = data.categories || [];
                allBrands = data.brands || [];
                renderCategoryOptions();
                renderBrandOptions();
                render(applyFilters());
            } catch (e) {
                console.error(e);
                listEl.innerHTML = '<div class="empty">Error loading products</div>';
            }
        }

        function renderCategoryOptions() {
            const opts = ['<option value="">All categories</option>']
                .concat(allCategories.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`));
            catEl.innerHTML = opts.join('');
        }

        function renderBrandOptions() {
            const opts = ['<option value="">All brands</option>']
                .concat(allBrands.map(b => `<option value="${escapeHtml(b)}">${escapeHtml(b)}</option>`));
            brandEl.innerHTML = opts.join('');
        }

        function applyFilters() {
            const q = (searchEl.value || '').toLowerCase().trim();
            const cat = (catEl.value || '').toLowerCase().trim();
            const b = (brandEl.value || '').toLowerCase().trim();
            const filtered = allProducts.filter(p => {
                const name = (p.product || '').toLowerCase();
                const brand = (p.brand || '').toLowerCase();
                const hsn = (p.hsn_code || '').toLowerCase();
                const cats = (p.categories || []).map(x => String(x).toLowerCase());
                const qOk = !q || name.includes(q) || brand.includes(q) || hsn.includes(q);
                const cOk = !cat || cats.some(x => x.toLowerCase() === cat);
                const bOk = !b || brand === b;
                return qOk && cOk && bOk;
            });
            return applySort(filtered);
        }

        function formatPrice(minP, maxP) {
            const a = Number(minP || 0);
            const b = Number(maxP || 0);
            if (!a && !b) return '--';
            if (a === b) return '₹' + a.toLocaleString('en-IN');
            return '₹' + a.toLocaleString('en-IN') + ' - ₹' + b.toLocaleString('en-IN');
        }

        function priceKey(p) {
            const a = Number(p.min_price || 0);
            const b = Number(p.max_price || 0);
            if (a > 0) return a;
            if (b > 0) return b;
            return null; // unknown
        }

        function applySort(items) {
            const mode = sortEl.value || 'name_asc';
            const arr = items.slice();

            if (mode === 'name_asc') {
                arr.sort((x, y) => String(x.product || '').localeCompare(String(y.product || ''), 'en', { sensitivity: 'base' }));
                return arr;
            }

            if (mode === 'quoted_desc') {
                arr.sort((x, y) => Number(y.times_quoted || 0) - Number(x.times_quoted || 0));
                return arr;
            }

            if (mode === 'price_asc' || mode === 'price_desc') {
                arr.sort((x, y) => {
                    const px = priceKey(x);
                    const py = priceKey(y);
                    // Unknown prices go to bottom
                    if (px == null && py == null) return 0;
                    if (px == null) return 1;
                    if (py == null) return -1;
                    return mode === 'price_asc' ? (px - py) : (py - px);
                });
                return arr;
            }

            return arr;
        }

        function render(products) {
            countEl.textContent = products.length;
            if (!products.length) {
                listEl.innerHTML = '<div class="empty">No products found</div>';
                return;
            }

            listEl.innerHTML = products.map(p => {
                const cats = p.categories || [];
                return `
                    <div class="card">
                        <div class="name">${escapeHtml(p.product)}</div>
                        <div class="sub">
                            ${p.brand ? `<b>Brand:</b> ${escapeHtml(p.brand)}&nbsp;&nbsp;` : ''}
                            ${p.hsn_code ? `<b>HSN:</b> ${escapeHtml(p.hsn_code)}` : ''}
                        </div>
                        <div class="chip-row">
                            ${cats.slice(0, 6).map(c => `<span class="chip">${escapeHtml(c)}</span>`).join('')}
                        </div>
                        <div class="meta">
                            <div class="meta-col">
                                <div class="label">Price Range</div>
                                <div class="value price">${escapeHtml(formatPrice(p.min_price, p.max_price))}</div>
                            </div>
                            <div class="meta-col" style="text-align:right;">
                                <div class="label">Times Quoted</div>
                                <div class="value">${escapeHtml(p.times_quoted ?? '--')}</div>
                            </div>
                        </div>
                    </div>
                `;
            }).join('');
        }

        function escapeHtml(str) {
            return String(str ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":"&#39;"}[c]));
        }

        searchEl.addEventListener('input', () => render(applyFilters()));
        catEl.addEventListener('change', () => render(applyFilters()));
        brandEl.addEventListener('change', () => render(applyFilters()));
        sortEl.addEventListener('change', () => render(applyFilters()));

        loadProducts();
    </script>

    <!-- Image Picker Modal -->
    <div id="image-modal" class="card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2000; width: 500px; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
        <h2>Pick Product Image</h2>
        <div id="existing-images" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; max-height: 200px; overflow-y: auto; padding: 10px; border: 1px solid #eee; border-radius: 8px;">
            <p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 16px;">
            <label style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px;">Upload New Image</label>
            <input type="file" id="image-upload-file" accept="image/*" style="font-size: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
                <button class="btn btn-primary" onclick="uploadNewImage()">Upload & Use</button>
                <button class="btn btn-secondary" onclick="closeImagePicker()">Cancel</button>
            </div>
        </div>
    </div>
    <div id="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1999; display: none;" onclick="closeImagePicker()"></div>

    <script>
        let currentPickerRow = null;

        async function openImagePicker(rowId) {
            currentPickerRow = rowId;
            const product = document.querySelector(`#item-row-${rowId} .product-input`).value.trim();
            if (!product) {
                showStatus('Enter product name first', true);
                return;
            }

            document.getElementById('image-modal').style.display = 'block';
            document.getElementById('modal-overlay').style.display = 'block';

            // Load existing images
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/images/${encodeURIComponent(product)}`);
            const images = await res.json();
            
            const container = document.getElementById('existing-images');
            if (images.length > 0) {
                container.innerHTML = images.map(img => `
                    <div style="cursor: pointer; border: 2px solid transparent;" onclick="selectExistingImage('${img.url}')">
                        <img src="${baseUrl}/${img.url}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;">
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>';
            }
        }

        function closeImagePicker() {
            document.getElementById('image-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentPickerRow = null;
        }

        function selectExistingImage(url) {
            const preview = document.getElementById(`image-preview-${currentPickerRow}`);
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            preview.querySelector('img').src = `${baseUrl}/${url}`;
            preview.style.display = 'block';
            document.getElementById(`image-url-${currentPickerRow}`).value = url;
            closeImagePicker();
        }

        async function uploadNewImage() {
            const fileInput = document.getElementById('image-upload-file');
            if (!fileInput.files[0]) {
                alert('Pick a file first');
                return;
            }

            const product = document.querySelector(`#item-row-${currentPickerRow} .product-input`).value.trim();
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('product_name', product);
            formData.append('category', 'uncategorized'); // Can be improved to use product cat

            showStatus('Uploading image...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/upload-image`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const img = await res.json();
                selectExistingImage(img.url);
                showStatus('Image uploaded!');
            } else {
                showStatus('Upload failed', true);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/products", response_class=HTMLResponse)
async def product_catalog_page():
    return HTMLResponse(PRODUCTS_HTML)

@app.get("/api/products-list")
async def get_products_list():
    categories_set = set()
    brands_set = set()
    products = []

    for p in CATALOG:
        name = (p.get("product") or "").strip()
        if not name:
            continue

        brand = (p.get("brand") or "").strip()
        if brand:
            brands_set.add(brand)

        # clean_catalog.json currently does not carry category info.
        # We keep this field for future enrichment.
        cats = p.get("categories") or []
        if isinstance(cats, str):
            cats = [cats]
        cats = [str(c).strip() for c in cats if str(c).strip()]
        if not cats:
            cats = ["Uncategorized"]

        for c in cats:
            categories_set.add(c)

        products.append({
            "product": name,
            "brand": brand,
            "hsn_code": (p.get("hsn_code") or "").strip(),
            "categories": cats,
            "min_price": p.get("min_price", 0),
            "max_price": p.get("max_price", 0),
            "times_quoted": p.get("times_quoted", 0),
        })

    products.sort(key=lambda x: x["product"])
    return {
        "categories": sorted(categories_set),
        "brands": sorted(brands_set),
        "products": products,
    }

AUDIT_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Bajaj - Data Audit</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: system-ui, sans-serif; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
        .header { background: #111; color: white; padding: 12px 20px; border-bottom: 3px solid #c5a059; display: flex; align-items: center; justify-content: space-between; }
        .header h1 { font-size: 18px; }
        
        .main-container { display: flex; flex: 1; overflow: hidden; }
        
        .sidebar { width: 450px; border-right: 1px solid #ddd; display: flex; flex-direction: column; background: #fafafa; }
        .search-area { padding: 12px; background: white; border-bottom: 1px solid #eee; }
        .search-input { width: 100%; padding: 8px 12px; border: 1px solid #ddd; border-radius: 6px; }
        
        .audit-list { flex: 1; overflow-y: auto; padding: 12px; }
        .audit-card { background: white; border-radius: 8px; padding: 12px; margin-bottom: 12px; border: 1px solid #e5e5ea; cursor: pointer; transition: all 0.2s; }
        .audit-card:hover { border-color: #c5a059; box-shadow: 0 4px 12px rgba(0,0,0,0.05); }
        .audit-card.active { border-color: #c5a059; background: #fff9f0; box-shadow: 0 0 0 2px #c5a059; }
        
        .pdf-name { font-size: 11px; color: #888; font-family: monospace; display: block; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; }
        .client-name { font-weight: 700; color: #111; display: block; margin-bottom: 4px; }
        .client-details { font-size: 12px; color: #666; line-height: 1.4; }
        
        .viewer { flex: 1; background: #525659; display: flex; justify-content: center; overflow-y: auto; padding: 20px; }
        .viewer img { max-width: 100%; height: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.5); background: white; align-self: flex-start; }
        
        .badge { font-size: 10px; padding: 2px 6px; border-radius: 4px; background: #eee; margin-left: 8px; }
    </style>
</head>
<body>
    <div class="header">
        <h1>Data Extraction Audit</h1>
        <div style="display: flex; align-items: center; gap: 16px;">
            <span class="badge" id="stat-count">0 Files</span>
            <div style="display: flex; gap: 10px;" id="nav-links"></div>
            <script>
            (function(){
                const p = window.location.pathname.replace(/\/+$/, '');
                const b = p.replace(/\/(directory|products|audit)$/, '') || '';
                const s = 'color:#c5a059;text-decoration:none;font-size:12px;font-weight:600;';
                document.getElementById('nav-links').innerHTML =
                    '<a href="'+b+'/" style="'+s+'">Quotes</a>' +
                    '<a href="'+b+'/directory" style="'+s+'">Directory</a>' +
                    '<a href="'+b+'/products" style="'+s+'">Products</a>' +
                    '<a href="'+b+'/audit" style="'+s+'border-bottom:2px solid #c5a059;">Audit</a>';
            })();
            </script>
        </div>
    </div>
    
    <div class="main-container">
        <div class="sidebar">
            <div class="search-area">
                <input type="text" class="search-input" id="audit-search" placeholder="Filter by PDF or Client...">
            </div>
            <div class="audit-list" id="audit-list">
                <div style="padding: 20px; text-align: center; color: #888;">Loading audit data...</div>
            </div>
        </div>
        <div class="viewer" id="viewer-pane">
            <div style="color: white; padding-top: 100px; text-align: center;">Select a document to verify</div>
        </div>
    </div>

    <script>
        let auditData = [];
        const listEl = document.getElementById('audit-list');
        const viewerEl = document.getElementById('viewer-pane');
        const searchEl = document.getElementById('audit-search');

        async function loadAudit() {
            try {
                const apiPath = window.location.pathname.replace(/\/audit\/?$/, '') + '/api/audit';
                const res = await fetch(apiPath);
                auditData = await res.json();
                renderList(auditData);
            } catch (e) {
                console.error(e);
                listEl.innerHTML = '<div style="padding: 20px; text-align: center; color: red;">Error loading audit data</div>';
            }
        }

        function renderList(items) {
            document.getElementById('stat-count').textContent = items.length + ' Files';
            if (items.length === 0) {
                listEl.innerHTML = '<div style="padding: 20px; text-align: center;">No matches</div>';
                return;
            }
            
            listEl.innerHTML = items.map((item, idx) => `
                <div class="audit-card" id="card-${idx}" onclick="viewPdf('${item.pdf}', ${idx})">
                    <span class="pdf-name">${item.pdf}</span>
                    <span class="client-name">${escapeHtml(item.client)}</span>
                    <div class="client-details">
                        ${item.invoice_no ? `<span class="badge" style="background:#fff3e0; color:#e65100; margin:0 0 8px 0; display:inline-block">Inv: ${escapeHtml(item.invoice_no)}</span><br>` : ''}
                        ${item.phone ? `<b>Ph:</b> ${escapeHtml(item.phone)}<br>` : ''}
                        ${item.address ? `${escapeHtml(item.address).replace(/\\n/g, '<br>')}` : '<i>No address extracted</i>'}
                    </div>
                </div>
            `).join('');
        }

        function viewPdf(filename, idx) {
            // Update UI
            document.querySelectorAll('.audit-card').forEach(c => c.classList.remove('active'));
            const card = document.getElementById('card-' + idx);
            if (card) card.classList.add('active');
            
            // Load First Page as Image
            const baseUrl = window.location.pathname.replace(/\/audit\/?$/, '');
            viewerEl.innerHTML = '<img src="' + baseUrl + '/source-pdf-page1/' + filename + '" alt="Verifying document...">';
        }

        function escapeHtml(str) {
            return String(str || '').replace(/[&<>\"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','\"':'&quot;',\"'\":\"&#39;\"}[c]));
        }

        searchEl.addEventListener('input', (e) => {
            const q = e.target.value.toLowerCase();
            const filtered = auditData.filter(item => 
                item.pdf.toLowerCase().includes(q) || 
                item.client.toLowerCase().includes(q)
            );
            renderList(filtered);
        });

        loadAudit();
    </script>

    <!-- Image Picker Modal -->
    <div id="image-modal" class="card" style="position: fixed; top: 50%; left: 50%; transform: translate(-50%, -50%); z-index: 2000; width: 500px; display: none; box-shadow: 0 20px 60px rgba(0,0,0,0.4);">
        <h2>Pick Product Image</h2>
        <div id="existing-images" style="display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 16px; max-height: 200px; overflow-y: auto; padding: 10px; border: 1px solid #eee; border-radius: 8px;">
            <p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>
        </div>
        <div style="border-top: 1px solid #eee; padding-top: 16px;">
            <label style="font-size: 13px; font-weight: 600; display: block; margin-bottom: 8px;">Upload New Image</label>
            <input type="file" id="image-upload-file" accept="image/*" style="font-size: 12px; margin-bottom: 12px;">
            <div style="display: flex; justify-content: space-between;">
                <button class="btn btn-primary" onclick="uploadNewImage()">Upload & Use</button>
                <button class="btn btn-secondary" onclick="closeImagePicker()">Cancel</button>
            </div>
        </div>
    </div>
    <div id="modal-overlay" style="position: fixed; top: 0; left: 0; right: 0; bottom: 0; background: rgba(0,0,0,0.5); z-index: 1999; display: none;" onclick="closeImagePicker()"></div>

    <script>
        let currentPickerRow = null;

        async function openImagePicker(rowId) {
            currentPickerRow = rowId;
            const product = document.querySelector(`#item-row-${rowId} .product-input`).value.trim();
            if (!product) {
                showStatus('Enter product name first', true);
                return;
            }

            document.getElementById('image-modal').style.display = 'block';
            document.getElementById('modal-overlay').style.display = 'block';

            // Load existing images
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/images/${encodeURIComponent(product)}`);
            const images = await res.json();
            
            const container = document.getElementById('existing-images');
            if (images.length > 0) {
                container.innerHTML = images.map(img => `
                    <div style="cursor: pointer; border: 2px solid transparent;" onclick="selectExistingImage('${img.url}')">
                        <img src="${baseUrl}/${img.url}" style="width: 80px; height: 80px; object-fit: cover; border-radius: 4px; border: 1px solid #ddd;">
                    </div>
                `).join('');
            } else {
                container.innerHTML = '<p style="color: #888; font-size: 12px;">No images uploaded for this product yet.</p>';
            }
        }

        function closeImagePicker() {
            document.getElementById('image-modal').style.display = 'none';
            document.getElementById('modal-overlay').style.display = 'none';
            currentPickerRow = null;
        }

        function selectExistingImage(url) {
            const preview = document.getElementById(`image-preview-${currentPickerRow}`);
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            preview.querySelector('img').src = `${baseUrl}/${url}`;
            preview.style.display = 'block';
            document.getElementById(`image-url-${currentPickerRow}`).value = url;
            closeImagePicker();
        }

        async function uploadNewImage() {
            const fileInput = document.getElementById('image-upload-file');
            if (!fileInput.files[0]) {
                alert('Pick a file first');
                return;
            }

            const product = document.querySelector(`#item-row-${currentPickerRow} .product-input`).value.trim();
            const formData = new FormData();
            formData.append('file', fileInput.files[0]);
            formData.append('product_name', product);
            formData.append('category', 'uncategorized'); // Can be improved to use product cat

            showStatus('Uploading image...');
            const baseUrl = window.location.pathname.replace(/\/+$/, '');
            const res = await fetch(`${baseUrl}/api/upload-image`, {
                method: 'POST',
                body: formData
            });

            if (res.ok) {
                const img = await res.json();
                selectExistingImage(img.url);
                showStatus('Image uploaded!');
            } else {
                showStatus('Upload failed', true);
            }
        }
    </script>
</body>
</html>
"""

@app.get("/audit", response_class=HTMLResponse)
async def audit_page():
    return HTMLResponse(AUDIT_HTML)

@app.get("/api/audit")
async def get_audit_data():
    # Load mapping
    mapping_path = Path("/home/sachin/work/bajaj/analysis/pdf_client_mapping.json")
    mapping = {}
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text())
        
    # Load client details
    cust_data = {c["customer"]: c for c in CUSTOMERS}
    
    audit_list = []
    for pdf, info in mapping.items():
        # Handle both old flat mapping and new object mapping
        client = info["client"] if isinstance(info, dict) else info
        inv_no = info.get("invoice_no") if isinstance(info, dict) else None
        
        details = cust_data.get(client, {})
        audit_list.append({
            "pdf": pdf,
            "client": client,
            "invoice_no": inv_no,
            "address": details.get("address", ""),
            "phone": details.get("phone", "")
        })
        
    # Sort by PDF name
    audit_list.sort(key=lambda x: x["pdf"])
    return audit_list

@app.get("/api/directory")
async def get_directory():
    # 1. Get last quote dates from DB
    db_quotes = {}
    with db() as conn:
        rows = conn.execute("SELECT client_name, MAX(quote_date) as last_date FROM quotes GROUP BY client_name").fetchall()
        for r in rows:
            db_quotes[r['client_name']] = r['last_date']
            
    # 2. Combine with catalog clients
    dir_list = []
    for c in CUSTOMERS:
        name = c.get("customer", "")
        if not name: continue
        
        # Get date from history or DB
        # Check if history has a date (placeholder was 2026-01-01)
        history_date = None
        if c.get("purchases"):
            history_date = c["purchases"][0].get("date")
            
        last_date = db_quotes.get(name) or history_date
        
        dir_list.append({
            "name": name,
            "address": c.get("address", ""),
            "phone": c.get("phone", ""),
            "gstin": c.get("gstin", ""),
            "purchase_count": len(c.get("purchases", [])),
            "last_quote": last_date
        })
        
    # Sort by name
    dir_list.sort(key=lambda x: x["name"])
    return dir_list

@app.get("/cleanup-report")
async def cleanup_report():
    path = ANALYSIS_DIR / "cleanup_report.html"
    if not path.exists():
        raise HTTPException(404, "Report not found")
    return FileResponse(path)

if __name__ == "__main__":
    import uvicorn
    print(f"Loaded {len(CATALOG)} products, {len(CUSTOMER_NAMES)} customers")
    uvicorn.run(app, host="100.91.37.16", port=8081)
