import os
import sqlite3
import json
import re
import httpx
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Tuple, Dict
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).parent
DATA_DIR = Path(os.getenv("DATA_DIR", str(BASE_DIR.parent)))
QQ_QUOTES_DB_PATH = os.getenv("QQ_QUOTES_DB_PATH", "").strip()

PROD_DB = Path(QQ_QUOTES_DB_PATH) if QQ_QUOTES_DB_PATH else (DATA_DIR / "quotegen" / "quotes.db")
DEV_DB = BASE_DIR / "dev_quotes.db"
DB_PATH = PROD_DB if PROD_DB.exists() else DEV_DB
META_DB_PATH = BASE_DIR / "qq_metadata.db"

AI_STUDIO_KEY = os.getenv("AI_STUDIO_KEY", "")
ENABLE_LLM_RESOLVER = os.getenv("ENABLE_LLM_RESOLVER", "false").lower() == "true"
APP_HOST = os.getenv("QQ_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("QQ_PORT", "8082"))

app = FastAPI(title="Analytics Assistant API")

MONTH_NAME_TO_NUM = {
    "january": 1,
    "february": 2,
    "march": 3,
    "april": 4,
    "may": 5,
    "june": 6,
    "july": 7,
    "august": 8,
    "september": 9,
    "october": 10,
    "november": 11,
    "december": 12,
}

NOISE_PREFIX_RE = re.compile(r"^(show|find|give|list|tell|please|me|all)\s+")

# Optional IP Whitelist via ENV
ALLOWED_IPS = os.getenv("ALLOWED_IPS", "")
if ALLOWED_IPS:
    allowed_set = set(ip.strip() for ip in ALLOWED_IPS.split(","))
    import fastapi

    @app.middleware("http")
    async def ip_whitelist_middleware(request: fastapi.Request, call_next):
        if request.client.host not in allowed_set:
            from fastapi.responses import JSONResponse
            return JSONResponse(status_code=403, content={"detail": "Access denied. IP not authorized."})
        return await call_next(request)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def normalize_search_text(value: str) -> str:
    text = (value or "").lower()
    text = re.sub(r"[’`]", "'", text)
    text = text.replace("&", " and ")
    text = re.sub(r"[/_,.;:!?()\[\]{}\"\\\-]+", " ", text)
    text = re.sub(r"[^a-z0-9'\s]", " ", text)
    text = re.sub(r"\band\b", " and ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def iso_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def month_bounds(year: int, month: int):
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = datetime(year, month + 1, 1) - timedelta(days=1)
    return start, end


def parse_period_filters(text: str) -> Tuple[dict, str]:
    now = datetime.now()
    filters = {}
    cleaned = text

    def apply_period(start: datetime, end: datetime, label: str, pattern: str):
        nonlocal cleaned
        filters["from_date"] = iso_date(start)
        filters["to_date"] = iso_date(end)
        filters["period_label"] = label
        cleaned = re.sub(pattern, " ", cleaned).strip()

    if re.search(r"\bthis month\b", cleaned):
        start = now.replace(day=1)
        apply_period(start, now, "this_month", r"\bthis month\b")
    elif re.search(r"\blast week\b", cleaned):
        this_week_start = now - timedelta(days=now.weekday())
        start = this_week_start - timedelta(days=7)
        end = start + timedelta(days=6)
        apply_period(start, end, "last_week", r"\blast week\b")
    elif re.search(r"\blast month\b", cleaned):
        if now.month == 1:
            year, month = now.year - 1, 12
        else:
            year, month = now.year, now.month - 1
        start, end = month_bounds(year, month)
        apply_period(start, end, "last_month", r"\blast month\b")
    elif re.search(r"\bthis year\b", cleaned):
        start = datetime(now.year, 1, 1)
        apply_period(start, now, "this_year", r"\bthis year\b")
    elif re.search(r"\blast year\b", cleaned):
        start = datetime(now.year - 1, 1, 1)
        end = datetime(now.year - 1, 12, 31)
        apply_period(start, end, "last_year", r"\blast year\b")
    else:
        month_pattern = r"\b(?:in|from)\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+(\d{4}))?\b"
        match = re.search(month_pattern, cleaned)
        if match:
            month_name = match.group(1)
            month_num = MONTH_NAME_TO_NUM[month_name]
            if match.group(2):
                parsed_year = int(match.group(2))
                start, end = month_bounds(parsed_year, month_num)
                filters["from_date"] = iso_date(start)
                filters["to_date"] = iso_date(end)
                filters["period_label"] = f"month:{month_name}:{parsed_year}"
            else:
                filters["month"] = month_num
                filters["period_label"] = f"month:{month_name}:any_year"
            cleaned = re.sub(month_pattern, " ", cleaned).strip()
        else:
            year_match = re.search(r"\b(?:in|from)?\s*(20\d{2}|19\d{2})\b", cleaned)
            if year_match:
                year = int(year_match.group(1))
                filters["from_date"] = f"{year}-01-01"
                filters["to_date"] = f"{year}-12-31"
                filters["period_label"] = f"year:{year}"
                cleaned = re.sub(rf"\b(?:in|from)?\s*{year}\b", " ", cleaned).strip()

    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return filters, cleaned


def trim_noise_tokens(text: str) -> str:
    result = (text or "").strip()
    while True:
        updated = NOISE_PREFIX_RE.sub("", result).strip()
        if updated == result:
            break
        result = updated
    result = re.sub(r"\b(?:in|from|for|to)\s*$", "", result).strip()
    return result


def init_metadata_db():
    conn = sqlite3.connect(META_DB_PATH)
    conn.execute(
        """
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
            matched_pattern TEXT,
            error_text TEXT
        )
    """
    )

    existing_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(qq_query_log)").fetchall()
    }
    if "matched_pattern" not in existing_columns:
        conn.execute("ALTER TABLE qq_query_log ADD COLUMN matched_pattern TEXT")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qq_client_alias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            canonical_name TEXT NOT NULL,
            canonical_norm TEXT NOT NULL,
            alias_name TEXT NOT NULL,
            alias_norm TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qq_client_alias_canonical_norm ON qq_client_alias(canonical_norm)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_qq_client_alias_is_active ON qq_client_alias(is_active)"
    )

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
        conn.execute(
            """
            INSERT INTO qq_query_log
            (created_at, raw_text, normalized_text, resolved_intent, params_json, route_source, answer_type, success, clarification_required, candidate_count, latency_ms, proof_present, matched_pattern, error_text)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
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
                log_data.get("matched_pattern", ""),
                log_data.get("error_text", ""),
            ),
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Failed to log query: {e}")


# --- INTENT HANDLERS ---

def build_response(
    *,
    ok: bool,
    intent: str,
    answer_type: str,
    title: str,
    summary: str,
    items: Optional[list] = None,
    proof: Optional[dict] = None,
    suggestions: Optional[list] = None,
    needs_clarification: bool = False,
    candidates: Optional[list] = None,
) -> dict:
    return {
        "ok": ok,
        "intent": intent,
        "answer_type": answer_type,
        "title": title,
        "summary": summary,
        "items": items or [],
        "proof": proof or {},
        "suggestions": suggestions or [],
        "needs_clarification": needs_clarification,
        "candidates": candidates or [],
    }


def rank_name_match(normalized_query: str, candidate_name: str) -> Tuple[int, int, int, str]:
    normalized_name = normalize_search_text(candidate_name)
    query_tokens = normalized_query.split()
    compact_query = normalized_query.replace(" ", "")

    if normalized_name == normalized_query:
        return 0, 0, len(normalized_name), normalized_name
    if normalized_name.startswith(normalized_query):
        return 1, normalized_name.find(normalized_query), len(normalized_name), normalized_name
    if normalized_query in normalized_name:
        return 2, normalized_name.find(normalized_query), len(normalized_name), normalized_name

    compact_name = normalized_name.replace(" ", "")
    if compact_query and compact_query in compact_name:
        return 3, compact_name.find(compact_query), len(normalized_name), normalized_name

    if query_tokens and all(any(name_token.startswith(token) for name_token in normalized_name.split()) for token in query_tokens):
        return 4, len(normalized_name), len(normalized_name), normalized_name

    return 9, len(normalized_name), len(normalized_name), normalized_name


def get_alias_rows(active_only: bool = True) -> List[sqlite3.Row]:
    with sqlite3.connect(META_DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        if active_only:
            return conn.execute(
                """
                SELECT canonical_name, canonical_norm, alias_name, alias_norm
                FROM qq_client_alias
                WHERE is_active = 1
                """
            ).fetchall()
        return conn.execute(
            "SELECT canonical_name, canonical_norm, alias_name, alias_norm FROM qq_client_alias"
        ).fetchall()


def resolve_client_name(raw_term: str, limit: int = 6) -> Dict[str, object]:
    normalized_query = normalize_search_text(raw_term)
    if not normalized_query:
        return {"status": "unresolved", "resolution_mode": "none", "candidates": []}

    with get_db() as conn:
        quote_rows = conn.execute(
            """
            SELECT client_name, COUNT(*) AS quote_count, MAX(quote_date) AS latest_quote_date
            FROM quotes
            GROUP BY client_name
            """
        ).fetchall()

    direct_ranked = []
    canonical_info: Dict[str, dict] = {}
    for row in quote_rows:
        score = rank_name_match(normalized_query, row["client_name"])
        canonical_info[row["client_name"]] = {
            "name": row["client_name"],
            "quote_count": row["quote_count"],
            "latest_quote_date": row["latest_quote_date"],
            "match_type": "direct",
            "matched_alias": None,
            "match_score": score,
        }
        if score[0] <= 4:
            direct_ranked.append((score, row["client_name"]))

    alias_rows = get_alias_rows(active_only=True)
    alias_ranked = []
    for alias_row in alias_rows:
        alias_score = rank_name_match(normalized_query, alias_row["alias_name"])
        canonical_score = rank_name_match(normalized_query, alias_row["canonical_name"])
        score = alias_score if alias_score[0] <= canonical_score[0] else canonical_score
        if score[0] > 4:
            continue
        canonical_name = alias_row["canonical_name"]
        if canonical_name in canonical_info:
            current = canonical_info[canonical_name]
            if current["match_type"] == "direct":
                continue
            if score < current["match_score"]:
                current["match_score"] = score
                current["matched_alias"] = alias_row["alias_name"]
        else:
            canonical_info[canonical_name] = {
                "name": canonical_name,
                "quote_count": 0,
                "latest_quote_date": None,
                "match_type": "alias",
                "matched_alias": alias_row["alias_name"],
                "match_score": score,
            }
        if canonical_info[canonical_name]["match_type"] != "direct":
            canonical_info[canonical_name]["match_type"] = "alias"
            canonical_info[canonical_name]["matched_alias"] = alias_row["alias_name"]
            alias_ranked.append((score, canonical_name))

    ranked_keys = []
    for score, name in sorted(direct_ranked, key=lambda item: item[0]):
        ranked_keys.append((0, score, name))
    for score, name in sorted(alias_ranked, key=lambda item: item[0]):
        if any(existing[2] == name for existing in ranked_keys):
            continue
        ranked_keys.append((1, score, name))

    ranked_keys.sort(key=lambda item: (item[0], item[1]))
    selected = []
    for _, _, name in ranked_keys[:limit]:
        item = canonical_info[name]
        selected.append(
            {
                "name": item["name"],
                "quote_count": item["quote_count"],
                "latest_quote_date": item["latest_quote_date"],
                "match_type": item["match_type"],
                "matched_alias": item["matched_alias"],
            }
        )

    if not selected:
        return {"status": "unresolved", "resolution_mode": "none", "candidates": []}

    exact_direct = [
        c
        for c in selected
        if c["match_type"] == "direct" and normalize_search_text(c["name"]) == normalized_query
    ]
    if exact_direct:
        return {
            "status": "resolved",
            "resolution_mode": "direct",
            "client_name": exact_direct[0]["name"],
            "matched_alias": None,
            "candidates": selected,
        }

    exact_alias = [
        c
        for c in selected
        if c["match_type"] == "alias" and normalize_search_text(c["matched_alias"] or "") == normalized_query
    ]
    if exact_alias:
        return {
            "status": "resolved",
            "resolution_mode": "alias",
            "client_name": exact_alias[0]["name"],
            "matched_alias": exact_alias[0]["matched_alias"],
            "candidates": selected,
        }

    if len(selected) == 1:
        only = selected[0]
        return {
            "status": "resolved",
            "resolution_mode": only["match_type"],
            "client_name": only["name"],
            "matched_alias": only["matched_alias"],
            "candidates": selected,
        }

    return {
        "status": "clarify",
        "resolution_mode": "ambiguous",
        "candidates": selected,
    }


def lookup_client_candidates(raw_term: str, limit: int = 6) -> List[dict]:
    resolved = resolve_client_name(raw_term, limit=limit)
    return resolved.get("candidates", [])


def lookup_product_candidates(raw_term: str, limit: int = 6) -> List[dict]:
    normalized_query = normalize_search_text(raw_term)
    if not normalized_query:
        return []

    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT product_name, COUNT(*) AS freq
            FROM quote_items
            GROUP BY product_name
            """
        ).fetchall()

    ranked = []
    for row in rows:
        score = rank_name_match(normalized_query, row["product_name"])
        if score[0] <= 4:
            ranked.append((score, {"name": row["product_name"], "frequency": row["freq"]}))

    ranked.sort(key=lambda item: item[0])
    return [item[1] for item in ranked[:limit]]


def canonicalize_client_filter(raw_client: str) -> dict:
    return resolve_client_name(raw_client, limit=6)


def run_quote_search(params: dict) -> dict:
    filters = {
        "client_name": (params.get("client_name") or "").strip(),
        "product_name": (params.get("product_name") or "").strip(),
        "from_date": (params.get("from_date") or "").strip(),
        "to_date": (params.get("to_date") or "").strip(),
        "month": int(params.get("month", 0) or 0),
        "limit": max(1, min(int(params.get("limit", 10) or 10), 50)),
    }

    where = []
    values = []
    product_clause = ""

    if filters["client_name"]:
        where.append("q.client_name = ?")
        values.append(filters["client_name"])

    if filters["from_date"]:
        where.append("q.quote_date >= ?")
        values.append(filters["from_date"])

    if filters["to_date"]:
        where.append("q.quote_date <= ?")
        values.append(filters["to_date"])

    if filters["month"]:
        where.append("CAST(strftime('%m', q.quote_date) AS INTEGER) = ?")
        values.append(filters["month"])

    if filters["product_name"]:
        product_clause = "AND qi.product_name LIKE ?"
        values.append(f"%{filters['product_name']}%")

    where_clause = " AND ".join(where) if where else "1=1"

    with get_db() as conn:
        count_sql = f"""
            SELECT COUNT(*) AS c
            FROM quotes q
            WHERE {where_clause}
            {'AND EXISTS (SELECT 1 FROM quote_items qi WHERE qi.quote_id = q.id ' + product_clause + ')' if filters['product_name'] else ''}
        """
        total_count = conn.execute(count_sql, values).fetchone()["c"]

        sql = f"""
            SELECT
                q.id,
                q.client_name,
                q.quote_date,
                q.grand_total,
                (
                    SELECT GROUP_CONCAT(DISTINCT qi2.product_name)
                    FROM quote_items qi2
                    WHERE qi2.quote_id = q.id
                    LIMIT 1
                ) AS product_preview
            FROM quotes q
            WHERE {where_clause}
            {'AND EXISTS (SELECT 1 FROM quote_items qi WHERE qi.quote_id = q.id ' + product_clause + ')' if filters['product_name'] else ''}
            ORDER BY q.quote_date DESC, q.id DESC
            LIMIT ?
        """

        rows = conn.execute(sql, values + [filters["limit"]]).fetchall()

    return {
        "result_count": total_count,
        "rows": rows,
        "returned_quote_ids": [r["id"] for r in rows],
    }


def extract_quote_search_params(normalized_text: str) -> Optional[dict]:
    if not normalized_text:
        return None

    if re.search(r"\b(how much business|top clients?|top products?|recent quotes?|quiet|inactive|last quote)\b", normalized_text):
        return None

    has_quote_trigger = bool(re.search(r"\bquote|quotes\b", normalized_text))
    period_filters, text_without_period = parse_period_filters(normalized_text)

    if not has_quote_trigger and not period_filters:
        return None

    cleaned = trim_noise_tokens(text_without_period)
    route_source = "quote_search:deterministic"
    client_candidate = ""
    product_candidate = ""

    cp_match = re.search(r"\bquotes?\s+(?:for|to)\s+(.+?)\s+(?:for|with)\s+(.+)$", cleaned)
    if cp_match:
        client_candidate = trim_noise_tokens(cp_match.group(1))
        product_candidate = trim_noise_tokens(cp_match.group(2).replace("quotes", "").strip())
    else:
        for_to_match = re.search(r"\bquotes?\s+(?:for|to)\s+(.+)$", cleaned)
        trailing_quote_match = re.search(r"^(.+?)\s+quotes?$", cleaned)

        if for_to_match:
            entity_text = trim_noise_tokens(for_to_match.group(1))
            client_res = canonicalize_client_filter(entity_text)
            if client_res["status"] == "clarify":
                return {
                    "intent": "quote_search",
                    "clarification": True,
                    "clarification_for": "client_name",
                    "candidate_names": [c["name"] for c in client_res["candidates"][:5]],
                    "filters": {
                        **period_filters,
                        "client_name": entity_text,
                        "product_name": "",
                        "client_resolution_mode": "ambiguous",
                    },
                    "route_source": route_source,
                    "matched_pattern": "quotes_for_to",
                }
            if client_res["status"] == "resolved":
                client_candidate = client_res["client_name"]
            else:
                product_matches = lookup_product_candidates(entity_text, limit=1)
                if product_matches:
                    product_candidate = entity_text
                else:
                    client_candidate = entity_text
        elif trailing_quote_match:
            entity_text = trim_noise_tokens(trailing_quote_match.group(1))
            product_matches = lookup_product_candidates(entity_text, limit=3)
            client_matches = lookup_client_candidates(entity_text, limit=3)
            if product_matches:
                product_candidate = entity_text
            elif client_matches:
                client_candidate = entity_text
            else:
                product_candidate = entity_text

    if not client_candidate and not product_candidate:
        # Support product-only with period phrases, e.g. "basketball poles this month"
        period_only_phrase = cleaned
        period_only_phrase = re.sub(r"\bquotes?\b", " ", period_only_phrase).strip()
        period_only_phrase = trim_noise_tokens(period_only_phrase)
        if period_only_phrase and period_filters:
            product_candidate = period_only_phrase

    if not client_candidate and not product_candidate:
        return None

    params = {
        "client_name": client_candidate,
        "product_name": product_candidate,
        "limit": 10,
        **period_filters,
        "route_source": route_source,
        "client_resolution_mode": client_res.get("resolution_mode", "none") if "client_res" in locals() else "none",
        "matched_alias": client_res.get("matched_alias") if "client_res" in locals() else None,
        "raw_client_term": entity_text if "entity_text" in locals() else "",
    }

    params["matched_pattern"] = (
        "quotes_for_to"
        if re.search(r"\bquotes?\s+(?:for|to)\b", normalized_text)
        else "entity_quotes_or_period"
    )

    return params


def handle_quote_search(params: dict) -> dict:
    if params.get("clarification"):
        return build_response(
            ok=False,
            intent="quote_search",
            answer_type="clarification",
            title="Multiple clients found",
            summary="Please choose the client to continue the quote search.",
            needs_clarification=True,
            candidates=params.get("candidate_names", []),
            proof={
                "source": "quotes",
                "filters": params.get("filters", {}),
                "route_source": params.get("route_source", "quote_search:deterministic"),
                "clarification_for": params.get("clarification_for", "client_name"),
                "query_template": "quotes for {client}",
            },
        )

    query_filters = {
        "client_name": params.get("client_name", ""),
        "product_name": params.get("product_name", ""),
        "from_date": params.get("from_date", ""),
        "to_date": params.get("to_date", ""),
        "month": params.get("month", 0),
        "limit": params.get("limit", 10),
    }

    if not query_filters["client_name"] and not query_filters["product_name"]:
        return build_response(
            ok=False,
            intent="quote_search",
            answer_type="unsupported",
            title="Could not resolve search filters",
            summary="Please mention a client or product for quote search.",
            proof={
                "source": "quotes",
                "filters": query_filters,
                "result_count": 0,
                "returned_quote_ids": [],
            },
        )

    search_result = run_quote_search(query_filters)
    rows = search_result["rows"]
    result_count = search_result["result_count"]
    returned_quote_ids = search_result["returned_quote_ids"]

    if result_count == 0:
        return build_response(
            ok=False,
            intent="quote_search",
            answer_type="unsupported",
            title="No matching quotes",
            summary="I couldn't find quotes for those filters.",
            proof={
                "source": "quotes",
                "filters": query_filters,
                "result_count": result_count,
                "returned_quote_ids": returned_quote_ids,
                "route_source": params.get("route_source", "quote_search:deterministic"),
            },
            suggestions=["Show recent quotes", "How much business this month?"],
        )

    proof = {
        "source": "quotes",
        "filters": query_filters,
        "result_count": result_count,
        "returned_quote_ids": returned_quote_ids,
        "route_source": params.get("route_source", "quote_search:deterministic"),
        "client_resolution": {
            "raw_client_term": params.get("raw_client_term", ""),
            "resolved_client_name": params.get("client_name", ""),
            "mode": params.get("client_resolution_mode", "none"),
            "matched_alias": params.get("matched_alias"),
        },
    }

    if result_count == 1:
        row = rows[0]
        return build_response(
            ok=True,
            intent="quote_search",
            answer_type="quote_record",
            title=f"Quote #{row['id']} · {row['client_name']}",
            summary=f"{row['quote_date']} · ₹{row['grand_total']:,.0f}",
            proof={**proof, "quote_id": row["id"]},
            suggestions=["Show recent quotes", "Who are my top clients?"],
        )

    items = []
    for row in rows:
        meta = row["quote_date"]
        if row["product_preview"]:
            meta = f"{meta} • {row['product_preview'][:90]}"
        items.append(
            {
                "label": row["client_name"],
                "meta": meta,
                "value": row["grand_total"],
            }
        )

    return build_response(
        ok=True,
        intent="quote_search",
        answer_type="ranked_list",
        title="Matching Quotes",
        summary=f"Found {result_count} matching quotes (showing {len(items)}).",
        items=items,
        proof=proof,
        suggestions=["Show recent quotes", "What are my top products?"],
    )


def handle_last_quote_client(params: dict) -> dict:
    client_name = params.get("client_name", "").strip()
    if not client_name or client_name.lower() in ["a client", "the client", "client"]:
        return build_response(
            ok=False,
            intent="last_quote_client",
            answer_type="clarification",
            title="Which client?",
            summary="Please specify the client name.",
            needs_clarification=True,
        )

    client_resolution = canonicalize_client_filter(client_name)
    if client_resolution["status"] == "clarify":
        return build_response(
            ok=False,
            intent="last_quote_client",
            answer_type="clarification",
            title="Multiple clients found",
            summary=f"Which '{client_name}' did you mean?",
            needs_clarification=True,
            candidates=[c["name"] for c in client_resolution["candidates"][:5]],
            proof={
                "source": "quotes",
                "client_resolution": {
                    "raw_client_term": client_name,
                    "mode": "ambiguous",
                },
            },
        )

    if client_resolution["status"] == "unresolved":
        return build_response(
            ok=False,
            intent="last_quote_client",
            answer_type="unsupported",
            title="No quotes found",
            summary=f"I couldn't find any quotes for '{client_name}'.",
            proof={
                "source": "quotes",
                "client_resolution": {
                    "raw_client_term": client_name,
                    "mode": "none",
                },
            },
        )

    canonical_client = client_resolution["client_name"]
    with get_db() as conn:
        candidates = conn.execute("SELECT DISTINCT client_name FROM quotes WHERE client_name = ? LIMIT 6", [canonical_client]).fetchall()
        if len(candidates) > 1:
            return build_response(
                ok=False,
                intent="last_quote_client",
                answer_type="clarification",
                title="Multiple clients found",
                summary=f"Which '{canonical_client}' did you mean?",
                needs_clarification=True,
                candidates=[c["client_name"] for c in candidates[:5]],
            )

        row = conn.execute(
            "SELECT id, client_name, quote_date, grand_total FROM quotes WHERE client_name = ? ORDER BY quote_date DESC, id DESC LIMIT 1",
            [canonical_client],
        ).fetchone()

        if row:
            return build_response(
                ok=True,
                intent="last_quote_client",
                answer_type="quote_record",
                title=f"Last quote to {row['client_name']}",
                summary=f"Sent on {row['quote_date']} for ₹{row['grand_total']:,.0f}.",
                proof={
                    "source": "quotes",
                    "quote_id": row["id"],
                    "client_name": row["client_name"],
                    "quote_date": row["quote_date"],
                    "grand_total": row["grand_total"],
                    "client_resolution": {
                        "raw_client_term": client_name,
                        "mode": client_resolution.get("resolution_mode", "direct"),
                        "matched_alias": client_resolution.get("matched_alias"),
                    },
                },
                suggestions=["Recent quotes", "This month"],
            )
        return build_response(
            ok=False,
            intent="last_quote_client",
            answer_type="unsupported",
            title="No quotes found",
            summary=f"I couldn't find any quotes for '{client_name}'.",
        )


def handle_month_summary(params: dict) -> dict:
    start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    with get_db() as conn:
        row = conn.execute("SELECT COUNT(*) as c, SUM(grand_total) as t FROM quotes WHERE quote_date >= ?", [start]).fetchone()
        c = row["c"] or 0
        t = row["t"] or 0
        return build_response(
            ok=True,
            intent="month_summary",
            answer_type="summary",
            title="This Month's Business",
            summary=f"{c} quotes generated totaling ₹{t:,.0f}.",
            proof={
                "source": "quotes",
                "period_start": start,
                "count": c,
                "total_value": t,
            },
            suggestions=["Recent quotes", "Top clients"],
        )


def handle_inactive_clients(params: dict) -> dict:
    days = params.get("days", 60)
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
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

        return build_response(
            ok=True,
            intent="inactive_clients",
            answer_type="ranked_list",
            title=f"Quiet Clients (> {days} days)",
            summary="These clients haven't received a quote recently.",
            items=items,
            proof={
                "source": "quotes",
                "cutoff_date": cutoff,
                "count": len(items),
            },
            suggestions=["Top clients", "This month"],
        )


def handle_top_clients(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT client_name, COUNT(*) as quote_count, SUM(grand_total) as total_value FROM quotes GROUP BY client_name ORDER BY total_value DESC LIMIT 5"
        ).fetchall()
        items = [{"label": r["client_name"], "meta": f"{r['quote_count']} quotes", "value": r["total_value"]} for r in rows]

        return build_response(
            ok=True,
            intent="top_clients",
            answer_type="ranked_list",
            title="Top Clients",
            summary="Your highest value clients historically.",
            items=items,
            proof={
                "source": "quotes",
                "sort_by": "value",
                "limit": 5,
            },
            suggestions=["Quiet clients", "Top products"],
        )


def handle_top_products(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT product_name, COUNT(*) as freq FROM quote_items GROUP BY product_name ORDER BY freq DESC LIMIT 5").fetchall()
        items = [{"label": r["product_name"], "meta": f"Quoted {r['freq']} times", "value": None} for r in rows]

        return build_response(
            ok=True,
            intent="top_products",
            answer_type="ranked_list",
            title="Top Products",
            summary="Your most frequently quoted items.",
            items=items,
            proof={
                "source": "quote_items",
                "sort_by": "frequency",
                "limit": 5,
            },
            suggestions=["This month", "Recent quotes"],
        )


def handle_recent_quotes(params: dict) -> dict:
    with get_db() as conn:
        rows = conn.execute("SELECT id, client_name, quote_date, grand_total FROM quotes ORDER BY quote_date DESC, id DESC LIMIT 5").fetchall()
        items = [{"label": r["client_name"], "meta": r["quote_date"], "value": r["grand_total"]} for r in rows]

        return build_response(
            ok=True,
            intent="recent_quotes",
            answer_type="ranked_list",
            title="Recent Quotes",
            summary="The latest 5 quotes generated.",
            items=items,
            proof={
                "source": "quotes",
                "sort_by": "date",
                "limit": 5,
                "quote_ids": [r["id"] for r in rows],
            },
            suggestions=["This month", "Quiet clients"],
        )


# --- INTENT REGISTRY ---

INTENT_REGISTRY = [
    {
        "intent": "quote_search",
        "patterns": [
            r"\bquotes?\s+(?:for|to)\b",
            r"\bquotes?$",
            r"\b(this month|last week|last month|this year|last year)\b",
            r"\bin\s+(january|february|march|april|may|june|july|august|september|october|november|december)(?:\s+\d{4})?\b",
            r"\b(?:in|from)\s+(20\d{2}|19\d{2})\b",
        ],
        "handler": handle_quote_search,
        "extract": lambda m, text=None: extract_quote_search_params(text or ""),
    },
    {
        "intent": "last_quote_client",
        "patterns": [r"last quote to (.+)", r"last quote for (.+)"],
        "handler": handle_last_quote_client,
        "extract": lambda m, text=None: {"client_name": normalize_search_text(m.group(1))},
    },
    {
        "intent": "month_summary",
        "patterns": [r"this month", r"month summary", r"how much business"],
        "handler": handle_month_summary,
        "extract": lambda m, text=None: {},
    },
    {
        "intent": "inactive_clients",
        "patterns": [r"quiet", r"inactive", r"haven'?t quoted"],
        "handler": handle_inactive_clients,
        "extract": lambda m, text=None: {},
    },
    {
        "intent": "top_clients",
        "patterns": [r"top client", r"best client"],
        "handler": handle_top_clients,
        "extract": lambda m, text=None: {},
    },
    {
        "intent": "top_products",
        "patterns": [r"top product", r"most quoted", r"what product"],
        "handler": handle_top_products,
        "extract": lambda m, text=None: {},
    },
    {
        "intent": "recent_quotes",
        "patterns": [r"recent", r"latest quotes?"],
        "handler": handle_recent_quotes,
        "extract": lambda m, text=None: {},
    },
]


# --- API ENDPOINTS ---

@app.get("/api/clients/search")
async def search_clients(q: str = "", limit: int = 5):
    normalized_query = normalize_search_text(q)
    if len(normalized_query) < 2:
        return {"candidates": [], "candidate_objects": []}

    safe_limit = max(1, min(limit, 25))
    selected = lookup_client_candidates(normalized_query, limit=safe_limit)
    return {
        "candidates": [c["name"] for c in selected],
        "candidate_objects": selected,
    }


@app.get("/api/quotes/search")
async def search_quotes(
    client_name: str = "",
    product_name: str = "",
    from_date: str = "",
    to_date: str = "",
    limit: int = 10,
):
    client_resolution = canonicalize_client_filter(client_name) if client_name.strip() else {
        "status": "unresolved",
        "resolution_mode": "none",
        "client_name": "",
        "matched_alias": None,
    }
    resolved_client_name = client_resolution["client_name"] if client_resolution.get("status") == "resolved" else ""

    filters = {
        "client_name": resolved_client_name,
        "product_name": normalize_search_text(product_name),
        "from_date": from_date.strip(),
        "to_date": to_date.strip(),
        "month": 0,
        "limit": max(1, min(limit, 50)),
    }
    search_result = run_quote_search(filters)

    records = [
        {
            "quote_id": row["id"],
            "client_name": row["client_name"],
            "quote_date": row["quote_date"],
            "grand_total": row["grand_total"],
            "product_preview": row["product_preview"],
        }
        for row in search_result["rows"]
    ]

    return {
        "filters": filters,
        "client_resolution": {
            "raw_client_term": client_name,
            "mode": client_resolution.get("resolution_mode", "none"),
            "resolved_client_name": resolved_client_name,
            "matched_alias": client_resolution.get("matched_alias"),
        },
        "result_count": search_result["result_count"],
        "returned_quote_ids": search_result["returned_quote_ids"],
        "records": records,
    }


@app.post("/api/query")
async def process_query(request: Request):
    start_time = datetime.now()
    data = await request.json()
    raw_text = data.get("text", "")
    text = normalize_search_text(raw_text)

    log_record = {
        "raw_text": raw_text,
        "normalized_text": text,
        "route_source": "unsupported",
        "success": False,
    }

    response = None

    # 1. Deterministic Router
    for route in INTENT_REGISTRY:
        for pattern in route["patterns"]:
            match = re.search(pattern, text)
            if match:
                params = route["extract"](match, text)
                if params is None:
                    continue

                log_record["resolved_intent"] = route["intent"]
                log_record["params"] = params
                log_record["route_source"] = params.get("route_source", "rule")
                log_record["matched_pattern"] = params.get("matched_pattern", pattern)

                try:
                    response = route["handler"](params)
                    log_record["success"] = response.get("ok", False)
                    log_record["answer_type"] = response.get("answer_type", "")
                    log_record["clarification_required"] = response.get("needs_clarification", False)
                    log_record["candidate_count"] = len(response.get("candidates", []))
                    log_record["proof_present"] = bool(response.get("proof", {}))
                except Exception as e:
                    log_record["error_text"] = str(e)
                    response = build_response(
                        ok=False,
                        intent=route["intent"],
                        answer_type="unsupported",
                        title="Error",
                        summary="Something went wrong fetching that data.",
                    )
                break
        if response:
            break

    # 2. LLM Fallback (Feature Flagged)
    if not response and ENABLE_LLM_RESOLVER and AI_STUDIO_KEY:
        pass  # To be implemented with httpx

    # 3. Unsupported Fallback
    if not response:
        response = build_response(
            ok=False,
            intent="unknown",
            answer_type="unsupported",
            title="I'm still learning",
            summary="I can currently help with quote search, recent quotes, top clients, top products, this month's totals, and quiet clients.",
            suggestions=["Recent quotes", "This month", "Quiet clients"],
        )

    log_record["latency_ms"] = (datetime.now() - start_time).total_seconds() * 1000
    log_query(log_record)

    return response


app.mount("/", StaticFiles(directory=BASE_DIR / "static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn

    # Bound to tailscale IP
    uvicorn.run(app, host=APP_HOST, port=APP_PORT)
