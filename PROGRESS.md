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

## 2. QuoteQuery - Conversational Query App (Port 8082)

### Current v0.1 Contract (Implemented)
- ✅ Deterministic intent routing via ordered registry (regex + explicit handlers)
- ✅ Structured `/api/query` JSON responses (`ok`, `intent`, `answer_type`, `title`, `summary`, `items`, `proof`, optional clarification/suggestions)
- ✅ Six supported intents:
  1. `last_quote_client`
  2. `month_summary`
  3. `inactive_clients`
  4. `top_clients`
  5. `top_products`
  6. `recent_quotes`
- ✅ Clarification workflow for ambiguous client queries (`needs_clarification` + candidate chips)
- ✅ Client assist endpoint: `GET /api/clients/search?q=...`
- ✅ Query telemetry persisted to `qq_metadata.db` (`qq_query_log`)
- ✅ Read-only access to shared `quotes.db` for analytics/query execution
- ✅ `ENABLE_LLM_RESOLVER` feature flag exists and is default-off

### UX Reality (Current)
- Mobile-first single-page UI with text input, quick actions, and client lookup panel
- Clarification chips are shown inline in the answer card when disambiguation is required
- Response rendering is based on backend `answer_type` (`summary`, `ranked_list`, `quote_record`, `clarification`, `unsupported`)

### Target v0.1 Stability Goals
- Keep deterministic routing and structured payload shape stable for UI compatibility
- Preserve auditable query logging in `qq_metadata.db`
- Maintain strict read-only behavior against `quotes.db`
- Keep LLM fallback optional until deterministic coverage is intentionally expanded

---

## 3. System Status Snapshot

| Component | Status | Port |
|-----------|--------|------|
| Quote Generator | ✅ Active | 8081 |
| QuoteQuery API/UI | ✅ Active | 8082 |
| Shared Quote DB (`quotes.db`) | ✅ Read-only from QuoteQuery | - |
| QuoteQuery Metadata DB (`qq_metadata.db`) | ✅ Write-enabled | - |

---

## 4. Next Steps

1. Add tests under `tests/` for deterministic intent routing and response schemas
2. Add regression checks for clarification-chip flows
3. Expand deterministic patterns before enabling any default LLM resolution path
4. Add lightweight auth/rate controls if external exposure increases

---

*End of Progress Report*
