# Bajaj Sports - Development Progress

**Last Updated:** April 18, 2026

---

## 1. Quote Generator (Port 8081)

### Features Implemented
- ✅ Product autocomplete with pricing suggestions
- ✅ Client autocomplete with contact/address
- ✅ Line items with GST calculation (5%/12%/18%)
- ✅ PDF generation with WeasyPrint
- ✅ Product image upload + picker
- ✅ PDF line-item thumbnails
- ✅ Optional sections (payment, transport, installation)
- ✅ GST auto-fill from verified HSN/GST data

### Data Files
- `/home/sachin/work/bajaj/analysis/product_images.json`
- `/home/sachin/work/bajaj/analysis/product_hsn_gst_verified.json`
- `/home/sachin/work/bajaj/quotegen/static/images/spec_sheets/`

---

## 2. QuoteQuery - Analytics Assistant (Port 8082)

### Deterministic contract baseline (preserved)
- ✅ Structured `POST /api/query` response envelope with typed payloads (`summary`, `ranked_list`, `quote_record`, `clarification`, `unsupported`).
- ✅ Existing 6 deterministic v0.1 intents remain active:
  1. `last_quote_client`
  2. `month_summary`
  3. `inactive_clients`
  4. `top_clients`
  5. `top_products`
  6. `recent_quotes`
- ✅ Read-only shared analytics DB (`quotes.db`) remains the data source.
- ✅ QuoteQuery-owned metadata DB (`qq_metadata.db`) remains the query telemetry store.
- ✅ `ENABLE_LLM_RESOLVER` remains default-off and non-required.

### New deterministic capability implemented
- ✅ Added first-class `quote_search` capability in `quotequery/main.py`.
- ✅ Deterministic filter extraction added for combinations of:
  - `client_name`
  - `product_name`
  - `from_date`
  - `to_date`
  - `limit`
- ✅ Deterministic period parsing added for:
  - `this month`
  - `last week`
  - `last month`
  - `this year`
  - `last year`
  - month names (`in March`, `in March 2024`)
  - year phrases (`in 2024`, `from 2024`)
- ✅ Added deterministic `GET /api/quotes/search` endpoint for backend filter search reuse.

### `quote_search` response behavior
- ✅ Returns `quote_record` when exactly one strong result is found.
- ✅ Returns `ranked_list` when multiple results are found.
- ✅ Returns `clarification` when client disambiguation is required.
- ✅ Returns `unsupported` when safe filters cannot be extracted or no results are found.
- ✅ Adds proof metadata with extracted filters, result count, route source, and returned quote IDs.

### Logging/telemetry updates
- ✅ Extended query processing flow to log:
  - resolved capability/intent
  - extracted params
  - route source
  - success/failure
  - clarification candidate count
  - proof present marker
  - latency

### Frontend updates (`quotequery/static/index.html`)
- ✅ Kept the same single-page UI shape and existing 3 quick actions.
- ✅ Preserved safe DOM rendering approach (`textContent`, element creation).
- ✅ Improved typed rendering support for quote-search responses:
  - ranked list entries continue to show client/date/amount
  - quote record now shows lightweight quote metadata
  - clarification chips now support query template from proof for `quote_search`

### Files changed in this update
- `quotequery/main.py`
- `quotequery/static/index.html`
- `quotequery/README.md`
- `PROGRESS.md`

---

## 3. System Status Snapshot

| Component | Status | Port |
|-----------|--------|------|
| Quote Generator | ✅ Running | 8081 |
| QuoteQuery App | ✅ Running | 8082 |
| PDF Generation | ✅ Working (WeasyPrint) | - |
| Image Upload/Picker | ✅ Working | - |
| GST Auto-fill | ✅ Working | - |
| Shared Quote DB (`quotes.db`) | ✅ Read-only from QuoteQuery | - |
| QuoteQuery Deterministic Intents | ✅ Working | - |
| QuoteQuery Deterministic Quote Search | ✅ Working | - |
| QuoteQuery Metadata DB (`qq_metadata.db`) | ✅ Write-enabled | - |

---

## 4. Next Steps

1. Add deterministic API contract tests for quote_search extraction and filter SQL.
2. Add deterministic frontend smoke tests for clarification-chip query-template behavior.
3. Evaluate optional LLM fallback path behind `ENABLE_LLM_RESOLVER` only after deterministic test coverage is stable.
4. Add authentication/authorization if external access expands.

---

*End of Progress Report*
