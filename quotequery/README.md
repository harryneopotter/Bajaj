# QuoteQuery (v0.2 Deterministic Contract)

QuoteQuery is a FastAPI + vanilla JS Analytics Assistant for querying Bajaj quote history with deterministic, auditable behavior by default.

## Scope

- Mobile-friendly single-page UI served from `quotequery/static/index.html`.
- Deterministic intent routing in `quotequery/main.py`.
- SQLite-backed analytics responses with explicit proof metadata.
- Optional (default-off) LLM resolver path for future expansion.

## Runtime and Data Ownership

1. **`quotes.db` (read-only)**
   - Source of truth for historical quotes and quote line-items.
   - Opened in URI read-only mode (`mode=ro`) by QuoteQuery.
   - Queried for analytics and deterministic search only.

2. **`qq_metadata.db` (owned by QuoteQuery)**
   - Created/managed by QuoteQuery in the app directory.
   - Stores query execution logs in `qq_query_log` (normalized text, resolved intent, route source, latency, success/failure, proof marker, etc.).
   - Stores deterministic client alias memory in `qq_client_alias` (canonical name + aliases), without changing `quotes.db`.

### `qq_client_alias` schema (QuoteQuery-owned)

```sql
CREATE TABLE IF NOT EXISTS qq_client_alias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canonical_name TEXT NOT NULL,
    canonical_norm TEXT NOT NULL,
    alias_name TEXT NOT NULL,
    alias_norm TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active INTEGER NOT NULL DEFAULT 1
);
```

- One canonical client can have multiple aliases (multiple rows with same `canonical_name`/`canonical_norm`).
- Alias resolution is deterministic because each `alias_norm` maps to only one canonical client.

## Deterministic Capabilities

### Core v0.1 intents (preserved)
1. `last_quote_client`
2. `month_summary`
3. `inactive_clients`
4. `top_clients`
5. `top_products`
6. `recent_quotes`

### New deterministic capability
7. `quote_search`

`quote_search` supports deterministic combinations of:
- `client_name`
- `product_name`
- `from_date`
- `to_date`
- `limit`

It can return:
- `quote_record` (single strong result)
- `ranked_list` (multiple results)
- `clarification` (client disambiguation required)
- `unsupported` (filters could not be safely extracted)

## Supported deterministic period parsing

`quote_search` supports:
- Relative phrases: `this month`, `last week`, `last month`, `this year`, `last year`
- Month phrases: `in March`, `in March 2024`
- Year phrases: `in 2024`, `from 2024`

## API Contract

### `POST /api/query`

Accepts:
```json
{ "text": "quotes for IIT in March" }
```

Returns the same structured envelope contract:
- `ok`
- `intent`
- `answer_type`
- `title`
- `summary`
- `items`
- `proof`
- optional `suggestions`, `needs_clarification`, `candidates`

For `quote_search`, proof includes fields such as:
- `source`
- extracted `filters`
- `result_count`
- `returned_quote_ids`
- `route_source`

### `GET /api/clients/search?q=<text>&limit=<n>`

- Deterministic client candidate lookup.
- Uses direct client-name matching first, then alias-assisted matching from `qq_client_alias`.
- For short input (`<2` chars), returns empty candidates.

### `GET /api/quotes/search`

Deterministic SQLite-backed filter endpoint used by `quote_search`.

Query params:
- `client_name`
- `product_name`
- `from_date` (`YYYY-MM-DD`)
- `to_date` (`YYYY-MM-DD`)
- `limit` (1..50)

Response includes:
- applied filters
- client resolution audit (`direct` / `alias` / `none`)
- result count
- returned quote ids
- typed quote records (`quote_id`, `client_name`, `quote_date`, `grand_total`, `product_preview`)

## Deterministic alias resolution behavior

When a client-like term is provided (for `/api/clients/search`, `last_quote_client`, and `quote_search`):

1. Normalize query text deterministically (`normalize_search_text`).
2. Rank direct client-name matches from `quotes.db`.
3. Rank alias matches from `qq_client_alias` and map to canonical client names.
4. Resolve in deterministic order:
   - exact direct match
   - exact alias match
   - single remaining candidate
   - otherwise clarification
5. Log/proof indicates whether the match was:
   - `direct`
   - `alias` (with `matched_alias`)
   - `ambiguous` / `none`

Example: searching `DPS RK Puram` can resolve via alias to canonical `Delhi Public School R.K. Puram`.

## Optional LLM Resolver (feature-flagged)

- Env flag: `ENABLE_LLM_RESOLVER`
- Default: **off** (`false`)
- Unresolved queries remain deterministic `unsupported` when disabled.

## Local Development

```bash
cd quotequery
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8082 --reload
```

## Manual Verification Checklist (v0.2)

### New `quote_search` checks
- [ ] `quotes for IIT`
- [ ] `quotes for DPS RK Puram` (when alias exists for `Delhi Public School R.K. Puram`)
- [ ] `football quotes`
- [ ] `quotes for IIT in March`
- [ ] `basketball poles this month`
- [ ] `quotes to DPS last week`
- [ ] `quotes for football in 2024`
- [ ] `show DPS quotes from last year`

### Existing v0.1 checks
- [ ] `How much business this month?`
- [ ] `Which clients have gone quiet?`
- [ ] `Who are my top clients?`
- [ ] `What are my top products?`
- [ ] `Show recent quotes`
- [ ] `Last quote for DPS`

## Notes

- Keep deterministic routing as default.
- Keep `quotes.db` read-only and `qq_metadata.db` as QuoteQuery-owned metadata.
- Any intent expansion must update this README and `PROGRESS.md` in the same change.
