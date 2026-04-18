# QuoteQuery (v0.1 Contract)

QuoteQuery is a FastAPI + vanilla JS assistant for querying Bajaj quote history with deterministic, auditable behavior by default.

## Scope

- Mobile-friendly single-page UI served from `quotequery/static/index.html`.
- Deterministic intent routing in `quotequery/main.py` for core business questions.
- SQLite-backed analytics responses with explicit proof metadata.
- Optional (default-off) LLM resolver path for future expansion.

## Runtime and Data Ownership

QuoteQuery uses **two SQLite databases with distinct roles**:

1. **`quotes.db` (read-only)**
   - Source of truth for historical quotes and line items.
   - Opened in URI read-only mode (`mode=ro`) by QuoteQuery.
   - Queried for analytics and client lookup only.

2. **`qq_metadata.db` (owned by QuoteQuery)**
   - Created/managed by QuoteQuery in the app directory.
   - Stores query execution logs in `qq_query_log` (normalized text, resolved intent, routing source, latency, success/error, etc.).
   - This is the system of record for query telemetry and audit trails.

## API Contract

### `POST /api/query`

Accepts JSON:

```json
{ "text": "last quote for DPS" }
```

Returns a **structured response envelope** (shape may vary by `answer_type`, but keys are stable):

```json
{
  "ok": true,
  "intent": "last_quote_client",
  "answer_type": "quote_record",
  "title": "Last quote to DPS",
  "summary": "Sent on 2026-04-10 for ₹1,25,000.",
  "items": [],
  "proof": {
    "source": "quotes",
    "quote_id": 123
  },
  "suggestions": ["Recent quotes", "This month"],
  "needs_clarification": false,
  "candidates": []
}
```

#### Supported `answer_type` values (v0.1)
- `summary`
- `ranked_list`
- `quote_record`
- `clarification`
- `unsupported`

#### Clarification behavior
- If user text maps to `last_quote_client` but the client is ambiguous, response is `answer_type: "clarification"` with:
  - `needs_clarification: true`
  - `candidates: [ ... ]`
- UI renders candidates as chips; selecting a chip re-queries using the selected client.

### `GET /api/clients/search?q=<text>&limit=<n>`

- Used by the inline client-lookup panel.
- Returns candidate names for clarification assist.
- For short queries (`<2` chars), returns an empty candidate list.

Response shape:

```json
{ "candidates": ["Client A", "Client B"] }
```

## Deterministic Intent Registry (default path)

`/api/query` first evaluates a fixed intent registry (ordered rules + regex extraction). Current v0.1 intents:

1. `last_quote_client`
2. `month_summary`
3. `inactive_clients`
4. `top_clients`
5. `top_products`
6. `recent_quotes`

This deterministic registry is the primary contract for predictable and testable routing.

## Optional LLM Resolver (feature-flagged)

- Env flag: `ENABLE_LLM_RESOLVER`
- Default: **off** (`false`)
- Behavior:
  - If not enabled, unresolved inputs fall back to deterministic `unsupported` response.
  - If enabled (and key present), unresolved inputs are eligible for future LLM-based intent resolution.
- Current code keeps LLM fallback path stubbed and non-default.

## Local Development

### Prerequisites
- Python 3.8+
- Access to quote data at `../quotegen/quotes.db` (or a local `dev_quotes.db` fallback)

### Run

```bash
cd quotequery
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8082 --reload
```

Open: `http://localhost:8082`

### Environment Variables

```env
DATA_DIR=/home/sachin/work/bajaj
ENABLE_LLM_RESOLVER=false
AI_STUDIO_KEY=
ALLOWED_IPS=
```

## Manual Verification Checklist (v0.1)

Use this checklist after changes to routing/UX.

- [ ] **Intent: `month_summary`** — Ask “How much business this month?” and confirm `answer_type=summary` with proof period fields.
- [ ] **Intent: `inactive_clients`** — Ask “Which clients have gone quiet?” and confirm ranked list response.
- [ ] **Intent: `top_clients`** — Ask “Who are my top clients?” and confirm ranked list by value.
- [ ] **Intent: `top_products`** — Ask “What are my top products?” and confirm ranked list by frequency.
- [ ] **Intent: `recent_quotes`** — Ask “Show recent quotes” and confirm 5 latest entries returned.
- [ ] **Intent: `last_quote_client`** — Ask “Last quote for <known client>” and confirm quote record response.
- [ ] **Clarification-chip workflow** — Ask “last quote for school” (or another ambiguous stem), confirm clarification response with chips, tap a chip, and confirm resolved quote record.
- [ ] **Client search endpoint** — In the “Last Quote...” panel, type at least 2 characters and confirm `/api/clients/search` returns candidate chips.
- [ ] **Fallback behavior** — Ask unsupported query, confirm deterministic “I’m still learning” response when `ENABLE_LLM_RESOLVER=false`.

## Notes

- Keep API output structured and stable; frontend rendering assumes typed response contracts.
- Any expansion of intents should update this README and `PROGRESS.md` in the same change.
