import os
import sqlite3
import json
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", "/home/sachin/work/bajaj"))
# Use production DB if available, otherwise fallback to local dev DB
PROD_DB = DATA_DIR / "quotegen" / "quotes.db"
DEV_DB = Path(__file__).parent / "dev_quotes.db"
DB_PATH = PROD_DB if PROD_DB.exists() else DEV_DB
AI_STUDIO_KEY = os.getenv("AI_STUDIO_KEY", "")

app = FastAPI(title="QuoteQuery API")

ALLOWED_IPS = {"100.84.92.33", "100.119.13.60"}
import fastapi
@app.middleware("http")
async def ip_whitelist_middleware(request: fastapi.Request, call_next):
    if request.client.host not in ALLOWED_IPS:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=403, content={"detail": f"Access denied. Your IP ({request.client.host}) is not authorized."})
    return await call_next(request)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.get("/api/analytics/quotes/summary")
async def get_quote_summary(from_date: Optional[str] = None, to_date: Optional[str] = None, client_name: Optional[str] = None):
    query = "SELECT COUNT(*) as count, SUM(grand_total) as total, AVG(grand_total) as avg FROM quotes WHERE 1=1"
    params = []
    if from_date:
        query += " AND quote_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND quote_date <= ?"
        params.append(to_date)
    if client_name:
        query += " AND client_name LIKE ?"
        params.append(f"%{client_name}%")
    with get_db() as conn:
        row = conn.execute(query, params).fetchone()
        return {"total_quotes": row["count"] or 0, "total_value": row["total"] or 0, "avg_quote_value": row["avg"] or 0, "period": {"from": from_date, "to": to_date}}

@app.get("/api/analytics/clients/top")
async def get_top_clients(sort_by: str = "value", limit: int = 5):
    order_col = "total_value" if sort_by == "value" else "quote_count"
    query = f"SELECT client_name, COUNT(*) as quote_count, SUM(grand_total) as total_value FROM quotes GROUP BY client_name ORDER BY {order_col} DESC LIMIT ?"
    with get_db() as conn:
        rows = conn.execute(query, [limit]).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/analytics/products/top")
async def get_top_products(sort_by: str = "frequency", limit: int = 5):
    order_col = "total_value" if sort_by == "value" else "quote_count"
    query = f"SELECT product_name as name, COUNT(*) as quote_count, SUM(line_total) as total_value FROM quote_items GROUP BY product_name ORDER BY {order_col} DESC LIMIT ?"
    with get_db() as conn:
        rows = conn.execute(query, [limit]).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/quotes/search")
async def search_quotes(client_name: Optional[str] = None, product_name: Optional[str] = None, from_date: Optional[str] = None, to_date: Optional[str] = None, limit: int = 10):
    query = "SELECT DISTINCT q.id, q.client_name, q.quote_date, q.grand_total FROM quotes q LEFT JOIN quote_items i ON q.id = i.quote_id WHERE 1=1"
    params = []
    if client_name:
        query += " AND q.client_name LIKE ?"
        params.append(f"%{client_name}%")
    if product_name:
        query += " AND i.product_name LIKE ?"
        params.append(f"%{product_name}%")
    if from_date:
        query += " AND q.quote_date >= ?"
        params.append(from_date)
    if to_date:
        query += " AND q.quote_date <= ?"
        params.append(to_date)
    query += " ORDER BY q.quote_date DESC LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

@app.get("/api/analytics/quotes/inactive-clients")
async def get_inactive_clients(days_inactive: int = 60):
    cutoff = (datetime.now() - timedelta(days=days_inactive)).strftime('%Y-%m-%d')
    query = "SELECT client_name, MAX(quote_date) as last_quote_date, grand_total as last_value FROM quotes GROUP BY client_name HAVING last_quote_date < ? ORDER BY last_quote_date ASC"
    with get_db() as conn:
        rows = conn.execute(query, [cutoff]).fetchall()
        return [dict(r) for r in rows]

ENDPOINT_SCHEMA = """Available endpoints:
- GET /api/analytics/quotes/summary?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD
- GET /api/analytics/clients/top?sort_by=value|count&limit=N
- GET /api/analytics/products/top?sort_by=value|frequency&limit=N  
- GET /api/quotes/search?client_name=XYZ&product_name=ABC&from_date=YYYY-MM-DD&to_date=YYYY-MM-DD&limit=N
- GET /api/analytics/quotes/inactive-clients?days_inactive=N"""

SYSTEM_PROMPT_TEMPLATE = """You are an API call resolver.
%s
Today is 2026-04-15. Return ONLY JSON with "endpoint" and "params" keys."""

async def call_llm_resolver(user_text: str) -> Optional[dict]:
    if not AI_STUDIO_KEY:
        return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-3-31b:generateContent?key={AI_STUDIO_KEY}"
    prompt = SYSTEM_PROMPT_TEMPLATE % ENDPOINT_SCHEMA + "\n\nQuery: " + user_text
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500}}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.ok:
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                return json.loads(match.group())
    except Exception as e:
        print(f"LLM error: {e}")
    return None

async def narrate(api_data: dict, query: str) -> str:
    if not AI_STUDIO_KEY:
        return str(api_data)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemma-3-31b:generateContent?key={AI_STUDIO_KEY}"
    prompt = f"Convert to ONE simple sentence for a 65-year-old. Use INR. Query: {query}\nData: {json.dumps(api_data)}"
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.3, "maxOutputTokens": 200}}
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.ok:
            return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    except:
        pass
    return str(api_data)

@app.post("/api/query")
async def process_query(request: Request):
    data = await request.json()
    text = data.get("text", "").lower().strip()
    
    # Heuristic resolvers
    if "recent" in text or ("last" in text and "month" not in text and "to" not in text):
        with get_db() as conn:
            rows = conn.execute("SELECT client_name, quote_date, grand_total FROM quotes ORDER BY created_at DESC LIMIT 5").fetchall()
            items = [f"{r['client_name']} (INR{r['grand_total']:,.0f} on {r['quote_date']})" for r in rows]
            return {"answer": "Your 5 most recent quotes:<br><br>" + "<br>".join(items)}
    
    if "this month" in text:
        start = datetime.now().replace(day=1).strftime('%Y-%m-%d')
        with get_db() as conn:
            row = conn.execute("SELECT COUNT(*) as c, SUM(grand_total) as t FROM quotes WHERE quote_date >= ?", [start]).fetchone()
            return {"answer": "This month: " + str(row["c"] or 0) + " quotes, ₹ <b>" + "{:,.0f}".format(row["t"] or 0) + "</b>"}
    
    if "top client" in text or "best client" in text:
        rows = await get_top_clients(sort_by="value", limit=5)
        items = [str(i+1) + ". " + str(r["client_name"]) + " - ₹ <b>" + "{:,.0f}".format(float(r["total_value"] or 0)) + "</b>" for i,r in enumerate(rows)]
        return {"answer": "Top clients:<br><br>" + "<br>".join(items)}
    
    if "top product" in text or "most quoted" in text or ("product" in text and "most" in text) or "what products" in text:
        rows = await get_top_products(sort_by="frequency", limit=5)
        items = [f"{i+1}. {r['name']} ({r['quote_count']} times)" for i,r in enumerate(rows)]
        return {"answer": "Top products:<br><br>" + "<br>".join(items)}
    
    if "quiet" in text or "inactive" in text:
        rows = await get_inactive_clients(days_inactive=60)
        items = [f"{r['client_name']} (last: {r['last_quote_date']})" for r in rows[:5]]
        return {"answer": "Clients with no recent quotes:<br><br>" + "<br>".join(items)}
    
    # Last Quote to specific client
    if "last quote to" in text or "last quote for" in text:
        # Extract client name from query
        import re
        match = re.search(r"last quote to (.+?)(?:$|\?)", text)
        if not match:
            match = re.search(r"last quote for (.+?)(?:$|\?)", text)
        if match:
            client_name = match.group(1).strip()
            # Skip generic phrases
            if client_name.lower() in ["a client", "the client", "client", "some client"]:
                return {"answer": "Which client do you want the last quote for? (e.g., 'Last quote to IIT')"}
            rows = await search_quotes(client_name=client_name, limit=1)
            if rows:
                r = rows[0]
                return {"answer": f"Last quote to {r['client_name']} was on {r['quote_date']} for ₹ <b>{r['grand_total']:,.0f}</b>"}
            return {"answer": f"I couldn't find a recent quote for {client_name}"}
        return {"answer": "Which client's last quote do you want to see?"}
    
    # LLM fallback
    llm_result = await call_llm_resolver(text)
    if llm_result:
        endpoint = llm_result.get("endpoint", "")
        params = llm_result.get("params", {})
        if "summary" in endpoint:
            api_data = await get_quote_summary(**params)
        elif "clients/top" in endpoint:
            api_data = await get_top_clients(**params)
        elif "products/top" in endpoint:
            api_data = await get_top_products(**params)
        elif "search" in endpoint:
            api_data = await search_quotes(**params)
        elif "inactive" in endpoint:
            api_data = await get_inactive_clients(**params)
        else:
            api_data = {"note": "Not implemented"}
        answer = await narrate(api_data, text)
        return {"answer": answer}
    
    return {"answer": "I'm looking into that for you..."}

app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="100.91.37.16", port=8082)
