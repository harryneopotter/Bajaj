import os
import sqlite3
import json
import re
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/home/sachin/work/bajaj"))

PROD_DB = DATA_DIR / "quotegen" / "quotes.db"
DEV_DB = BASE_DIR / "dev_quotes.db"
DB_PATH = PROD_DB if PROD_DB.exists() else DEV_DB
META_DB_PATH = BASE_DIR / "qq_metadata.db"

AI_STUDIO_KEY = os.getenv("AI_STUDIO_KEY", "")
ENABLE_LLM_RESOLVER = os.getenv("ENABLE_LLM_RESOLVER", "false").lower() == "true"

app = FastAPI(title="Analytics Assistant API")

# Optional IP Whitelist via ENV
ALLOWED_IPS = os.getenv("ALLOWED_IPS", "")
if ALLOWED_IPS:
    allowed_set = set(ip.strip() for ip in ALLOWED_IPS.split(","))
    import fastapi
    @app.middleware("http")
    async def ip_whitelist_middleware(request: fastapi.Request, call_next):
        if request.client.host not in allowed_set:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": f"Access denied. IP not authorized."})
        return await call_next(request)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def init_metadata_db():
    conn = sqlite3.connect(META_DB_PATH)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS qq_query_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT,
            raw_text TEXT,
            normalized_text TEXT,
            resolved_intent TEXT,
            params_json TEXT,
            route_source TEXT,
            answer_type TEXT,
            success BOOLEAN,
            clarification_required BOOLEAN,
            candidate_count INTEGER,
            latency_ms REAL,
            proof_present BOOLEAN,
            error_text TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_metadata_db()

def get_db():
    # Read-only connection to shared DB
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 3000")
    return conn

def log_query(log_data: dict):
    try:
        conn = sqlite3.connect(META_DB_PATH)
        conn.execute('''
            INSERT INTO qq_query_log 
            (created_at, raw_text, normalized_text, resolved_intent, params_json, route_source, answer_type, success, clarification_required, candidate_count, latency_ms, proof_present, error_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            datetime.now().isoformat(),
            log_data.get("raw_text", ""),
            log_data.get("normalized_text", ""),
            log_data.get("resolved_intent", ""),
            json.dumps(log_data.get("params", {})),
            log_data.get("route_source", ""),
            log_data.get("answer_type", ""),
            log_data.get("success", False),
            log_data.get("clarification_required", False),
            log_data.get("candidate_count", 0),
            log_data.get("latency_ms", 0.0),
            log_data.get("proof_present", False),
            log_data.get("error_text", "")
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to log query: {e}")

# --- INTENT HANDLERS ---

def handle_last_quote_client(params: dict) -> dict:
    client_name = params.get("client_name", "").strip()
    if not client_name or client_name.lower() in ["a client", "the client", "client"]:
        return {
            "ok": False,
            "intent": "last_quote_client",
            "answer_type": "clarification",
            "title": "Which client?",
            "summary": "Please specify the client name.",
            "items": [],
            "proof": {},
            "needs_clarification": True,
            "candidates": []
        }
    
    with get_db() as conn:
        candidates = conn.execute("SELECT DISTINCT client_name FROM quotes WHERE client_name LIKE ? LIMIT 6", [f"%{client_name}%"]).fetchall()
        if len(candidates) > 1 and client_name.lower() not in [c["client_name"].lower() for c in candidates]:
            return {
                "ok": False,
                "intent": "last_quote_client",
                "answer_type": "clarification",
                "title": "Multiple clients found",
                "summary": f"Which '{client_name}' did you mean?",
                "items": [],
                "proof": {},
                "needs_clarification": True,
                "candidates": [c["client_name"] for c in candidates[:5]]
            }
        
        row = conn.execute("SELECT id, client_name, quote_date, grand_total FROM quotes WHERE client_name LIKE ? ORDER BY quote_date DESC, id DESC LIMIT 1", [f"%{client_name}%"]).fetchone()
        
        if row:
            return {
                "ok": True,
                "intent": "last_quote_client",
                "answer_type": "quote_record",
                "title": f"Last quote to {row['client_name']}",
                "summary": f"Sent on {row['quote_date']} for ₹{row['grand_total']:,.0f}.",
                "items": [],
                "proof": {
                    "source": "quotes",
                    "quote_id": row["id"],
                    "client_name": row["client_name"],
                    "quote_date": row["quote_date"],
                    "grand_total": row["grand_total"]
                },
                "suggestions": ["Recent quotes", "This month"]
            }
        return {
            "ok": False,
            "intent": "last_quote_client",
            "answer_type": "unsupported",
            "title": "No quotes found",
            "summary": f"I couldn't find any quotes for '{client_name}'.",
            "items": [],
            "proof": {}
        }

def handle_month_summary(params: dict) -> dict:
    start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as c, SUM(grand_total) as t FROM quotes WHERE quote_date >= ?", [start]).fetchone()
        c = row["c"] or 0
        t = row["t"] or 0
        return {
            "ok": True,
            "intent": "month_summary",
            "answer_type": "summary",
            "title": "This Month's Business",
            "summary": f"{c} quotes generated totaling ₹{t:,.0f}.",
            "items": [],
            "proof": {
                "source": "quotes",
                "period_start": start,
                "count": c,
                "total_value": t
            },
            "suggestions": ["Recent quotes", "Top clients"]
        }

def handle_inactive_clients(params: dict) -> dict:
    days = params.get("days", 60)
    cutoff = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    with get_db() as conn:
        query = """
            SELECT client_name, MAX(quote_date) as last_quote_date
            FROM quotes 
            GROUP BY client_name 
            HAVING last_quote_date < ? 
            ORDER BY last_quote_date DESC 
            LIMIT 5
        """
        rows = conn.execute(query, [cutoff]).fetchall()
        items = [{"label": r["client_name"], "meta": f"Last quote: {r['last_quote_date']}", "value": None} for r in rows]
        
        return {
            "ok": True,
            "intent": "inactive_clients",
            "answer_type": "ranked_list",
            "title": f"Quiet Clients (> {days} days)",
            "summary": "These clients haven't received a quote recently.",
            "items": items,
            "proof": {
                "source": "quotes",
                "cutoff_date": cutoff,
                "count": len(items)
            },
            "suggestions": ["Top clients", "This month"]
        }

def handle_top_clients(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT client_name, COUNT(*) as quote_count, SUM(grand_total) as total_value FROM quotes GROUP BY client_name ORDER BY total_value DESC LIMIT 5").fetchall()
        items = [{"label": r["client_name"], "meta": f"{r['quote_count']} quotes", "value": r["total_value"]} for r in rows]
        
        return {
            "ok": True,
            "intent": "top_clients",
            "answer_type": "ranked_list",
            "title": "Top Clients",
            "summary": "Your highest value clients historically.",
            "items": items,
            "proof": {
                "source": "quotes",
                "sort_by": "value",
                "limit": 5
            },
            "suggestions": ["Quiet clients", "Top products"]
        }

def handle_top_products(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT product_name, COUNT(*) as freq FROM quote_items GROUP BY product_name ORDER BY freq DESC LIMIT 5").fetchall()
        items = [{"label": r["product_name"], "meta": f"Quoted {r['freq']} times", "value": None} for r in rows]
        
        return {
            "ok": True,
            "intent": "top_products",
            "answer_type": "ranked_list",
            "title": "Top Products",
            "summary": "Your most frequently quoted items.",
            "items": items,
            "proof": {
                "source": "quote_items",
                "sort_by": "frequency",
                "limit": 5
            },
            "suggestions": ["This month", "Recent quotes"]
        }

def handle_recent_quotes(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT id, client_name, quote_date, grand_total FROM quotes ORDER BY quote_date DESC, id DESC LIMIT 5").fetchall()
        items = [{"label": r["client_name"], "meta": r["quote_date"], "value": r["grand_total"]} for r in rows]
        
        return {
            "ok": True,
            "intent": "recent_quotes",
            "answer_type": "ranked_list",
            "title": "Recent Quotes",
            "summary": "The latest 5 quotes generated.",
            "items": items,
            "proof": {
                "source": "quotes",
                "sort_by": "date",
                "limit": 5,
                "quote_ids": [r["id"] for r in rows]
            },
            "suggestions": ["This month", "Quiet clients"]
        }

# --- INTENT REGISTRY ---

INTENT_REGISTRY = [
    {
        "intent": "last_quote_client",
        "patterns": [r"last quote to (.+)", r"last quote for (.+)", r"quotes? for (.+)"],
        "handler": handle_last_quote_client,
        "extract": lambda m: {"client_name": m.group(1).strip(" ?.")}
    },
    {
        "intent": "month_summary",
        "patterns": [r"this month", r"month summary", r"how much business"],
        "handler": handle_month_summary,
        "extract": lambda m: {}
    },
    {
        "intent": "inactive_clients",
        "patterns": [r"quiet", r"inactive", r"haven'?t quoted"],
        "handler": handle_inactive_clients,
        "extract": lambda m: {}
    },
    {
        "intent": "top_clients",
        "patterns": [r"top client", r"best client"],
        "handler": handle_top_clients,
        "extract": lambda m: {}
    },
    {
        "intent": "top_products",
        "patterns": [r"top product", r"most quoted", r"what product"],
        "handler": handle_top_products,
        "extract": lambda m: {}
    },
    {
        "intent": "recent_quotes",
        "patterns": [r"recent", r"latest quotes?"],
        "handler": handle_recent_quotes,
        "extract": lambda m: {}
    }
]

# --- API ENDPOINTS ---

@app.get("/api/clients/search")
async def search_clients(q: str = "", limit: int = 5):
    q = re.sub(r'[^a-zA-Z0-9 ]', '', q).strip().lower()
    if len(q) < 2:
        return {"candidates": []}
    with get_db() as conn:
        rows = conn.execute("SELECT DISTINCT client_name FROM quotes WHERE LOWER(REPLACE(client_name, '.', '')) LIKE ? LIMIT ?", [f"%{q}%", limit]).fetchall()
        return {"candidates": [r["client_name"] for r in rows]}

@app.post("/api/query")
async def process_query(request: Request):
    start_time = datetime.now()
    data = await request.json()
    raw_text = data.get("text", "")
    text = raw_text.lower().strip()
    
    log_record = {
        "raw_text": raw_text,
        "normalized_text": text,
        "route_source": "unsupported",
        "success": False
    }

    response = None

    # 1. Deterministic Router
    for route in INTENT_REGISTRY:
        for pattern in route["patterns"]:
            match = re.search(pattern, text)
            if match:
                params = route["extract"](match)
                log_record["resolved_intent"] = route["intent"]
                log_record["params"] = params
                log_record["route_source"] = "rule"
                log_record["matched_pattern"] = pattern
                
                try:
                    response = route["handler"](params)
                    log_record["success"] = response.get("ok", False)
                    log_record["answer_type"] = response.get("answer_type", "")
                    log_record["clarification_required"] = response.get("needs_clarification", False)
                    log_record["proof_present"] = bool(response.get("proof", {}))
                except Exception as e:
                    log_record["error_text"] = str(e)
                    response = {
                        "ok": False,
                        "intent": route["intent"],
                        "answer_type": "unsupported",
                        "title": "Error",
                        "summary": "Something went wrong fetching that data.",
                        "proof": {}
                    }
                break
        if response:
            break

    # 2. LLM Fallback (Feature Flagged)
    if not response and ENABLE_LLM_RESOLVER and AI_STUDIO_KEY:
        pass # To be implemented with httpx

    # 3. Unsupported Fallback
    if not response:
        response = {
            "ok": False,
            "intent": "unknown",
            "answer_type": "unsupported",
            "title": "I'm still learning",
            "summary": "I can currently help with recent quotes, top clients, top products, this month's totals, and quiet clients.",
            "items": [],
            "proof": {},
            "suggestions": ["Recent quotes", "This month", "Quiet clients"]
        }

    log_record["latency_ms"] = (datetime.now() - start_time).total_seconds() * 1000
    log_query(log_record)
    
    return response

app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Bound to tailscale IP
    uvicorn.run(app, host="100.91.37.16", port=8082)
