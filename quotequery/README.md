# QuoteQuery (v0.1 Contract)

QuoteQuery is a FastAPI + vanilla JS assistant for querying historical quote data with deterministic, auditable behavior.

## Runtime Architecture

- **Backend:** `quotequery/main.py` (FastAPI, port `8082`).
- **Frontend:** `quotequery/static/index.html` (single-page mobile UI).
- **Primary quote database:** `quotes.db` opened as **read-only** via SQLite URI (`mode=ro`).
- **Metadata/query log database:** `qq_metadata.db` in `quotequery/`, owned by QuoteQuery for query telemetry.

## Data Ownership and Access Model

### `quotes.db` (shared data source)

- Source-of-truth quote and quote item records.
- QuoteQuery opens this DB in **read-only** mode and does not write business records.
- Used for analytics and lookup intents (`quotes`, `quote_items`).

### `qq_metadata.db` (QuoteQuery-owned)

- Created and managed by QuoteQuery at startup.
- Stores `qq_query_log` rows for each `/api/query` request (normalized text, resolved intent, route source, latency, success flags, etc.).
- This is the only database QuoteQuery writes to in normal operation.

## Deterministic Intent Registry

`/api/query` routes requests through an ordered `INTENT_REGISTRY` of regex patterns and handler functions.

Supported v0.1 intents:
1. `last_quote_client`
2. `month_summary`
3. `inactive_clients`
4. `top_clients`
5. `top_products`
6. `recent_quotes`

Behavioral contract:
- First matching pattern in registry order wins.
- Handler output is returned directly as structured JSON.
- If no deterministic match exists, QuoteQuery returns an `unsupported` response.
- Optional LLM fallback is feature-flagged and off by default (see below).

## API Contract

## `POST /api/query`

Request body:

```json
{ "text": "last quote for DPS" }
```

Structured response envelope (shape varies by `answer_type`):

```json
{
  "ok": true,
  "intent": "last_quote_client",
  "answer_type": "quote_record",
  "title": "Last quote to DPS",
  "summary": "Sent on 2026-04-01 for ₹125,000.",
  "items": [],
  "proof": {
    "source": "quotes"
  },
  "needs_clarification": false,
  "candidates": [],
  "suggestions": ["Recent quotes", "This month"]
}
```

Key fields:
- `ok` (`boolean`): whether the intent resolved successfully.
- `intent` (`string`): resolved deterministic intent or `unknown`.
- `answer_type` (`string`): one of `quote_record | summary | ranked_list | clarification | unsupported`.
- `title` / `summary` (`string`): display-ready response text.
- `items` (`array`): ranked/list payload for list-style answers.
- `proof` (`object`): lightweight provenance payload from the underlying query.
- `needs_clarification` (`boolean`, optional): whether UI should prompt disambiguation.
- `candidates` (`array`, optional): clarification chip candidates.
- `suggestions` (`array`, optional): quick follow-up prompts.

## `GET /api/clients/search`

Client-name lookup endpoint used by the “Last Quote…” workflow.

Query parameters:
- `q` (string): client search text (minimum 2 characters after normalization).
- `limit` (int, optional): max candidates (default `5`).

Response:

```json
{ "candidates": ["Client A", "Client B"] }
```

## Optional LLM Resolver (default OFF)

`ENABLE_LLM_RESOLVER` controls whether unresolved queries may go to an LLM resolver path.

- Default: `false` (disabled).
- Current v0.1 behavior: deterministic registry + unsupported fallback remain the active contract.
- Even when enabled, deterministic routing runs first.

Example `.env`:

```env
AI_STUDIO_KEY=your_key_here
ENABLE_LLM_RESOLVER=false
```

## Manual Verification Checklist (v0.1)

Run the app, then verify these flows in UI or via API:

1. **`last_quote_client` success path**  
   Ask: `last quote for <known client>` → returns `answer_type=quote_record` with `proof.quote_id`.
2. **`last_quote_client` clarification path**  
   Ask with ambiguous client substring (e.g., short shared token) → returns `needs_clarification=true` + `candidates[]`; clicking a candidate chip should re-query and resolve to a quote record.
3. **`month_summary`**  
   Ask: `how much business this month` → returns `answer_type=summary`.
4. **`inactive_clients`**  
   Ask: `which clients have gone quiet` → returns `answer_type=ranked_list`.
5. **`top_clients`**  
   Ask: `top clients` → returns ranked list with values.
6. **`top_products`**  
   Ask: `most quoted products` → returns ranked list.
7. **`recent_quotes`**  
   Ask: `recent quotes` → returns latest quote list.
8. **Unsupported fallback**  
   Ask unrelated text → returns `answer_type=unsupported` with guidance suggestions.

## Local Development

```bash
cd quotequery
pip install fastapi uvicorn python-dotenv
uvicorn main:app --host 0.0.0.0 --port 8082 --reload
```

Open `http://localhost:8082`.
