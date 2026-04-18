# Bajaj Sports - Development Progress

**Last Updated:** April 18, 2026

---

## 1. Quote Generator (Port 8081)

### Features Implemented
- ✅ Product autocomplete with pricing suggestions
- ✅ Client autocomplete with contact/address
- ✅ Line items with GST calculation (5%/12%/18%)
- ✅ PDF generation with WeasyPrint
- ✅ **Product Images** - Upload & pick images for products
- ✅ **Image Thumbnails in PDF** - 60x60px thumbnails next to line items
- ✅ **Optional Sections** - Payment Terms, Transportation, Installation (checkbox-enabled)
- ✅ **GST Auto-fill** - Auto-selects GST slab from verified HSN/GST data
- ✅ **Image Picker UI** - Modal for selecting/uploading product images

### Data Files
- `/home/sachin/work/bajaj/analysis/product_images.json` - Image registry (153 images)
- `/home/sachin/work/bajaj/analysis/product_hsn_gst_verified.json` - HSN/GST lookup (1120 products)
- `/home/sachin/work/bajaj/quotegen/static/images/spec_sheets/` - Extracted product images

### Files Modified
- `/home/sachin/work/bajaj/quotegen/main.py` - Core app

---

## 2. QuoteQuery - Conversational Query App (Port 8082)

### Current v0.1 Contract (Implemented)
- ✅ **Structured `POST /api/query` envelope** with stable fields (`ok`, `intent`, `answer_type`, `title`, `summary`, `items`, `proof`, optional `suggestions`/clarification keys).
- ✅ **Deterministic intent registry** (ordered regex routes) for 6 intents:
  1. `last_quote_client`
  2. `month_summary`
  3. `inactive_clients`
  4. `top_clients`
  5. `top_products`
  6. `recent_quotes`
- ✅ **Clarification flow for ambiguous client matches** (`needs_clarification=true` + candidate chips).
- ✅ **Client lookup endpoint**: `GET /api/clients/search` for inline client search.
- ✅ **Read-only analytics DB access**: QuoteQuery opens shared `quotes.db` in read-only mode.
- ✅ **Owned query telemetry DB**: QuoteQuery creates/writes `qq_metadata.db` (`qq_query_log`) for query logs and audit metadata.
- ✅ **Feature-flagged LLM resolver switch**: `ENABLE_LLM_RESOLVER` exists and is default-off.

### UX Status (Current)
- ✅ Mobile-friendly, single-page UI with:
  - text input
  - voice input button (browser-supported)
  - action buttons for common flows
  - clarification chips and inline client-lookup panel
- ✅ UI renders typed response shapes (`summary`, `ranked_list`, `quote_record`, `clarification`, `unsupported`) rather than free-form narration assumptions.

### Target v0.1 UX/Contract Guardrails
- Keep deterministic routing as the default path for reliability and testability.
- Keep unsupported fallback explicit when LLM resolver is disabled.
- Maintain strict separation of data responsibilities:
  - `quotes.db`: read-only analytics source
  - `qq_metadata.db`: query log ownership
- Preserve chip-based disambiguation workflow for client-specific asks.

### Outdated Assumptions Removed
- ❌ QuoteQuery is **not** documented as a prototype narration-first flow.
- ❌ UI is **not** assumed to be only “6 big tap targets” without typed API-state rendering.
- ❌ LLM path is **not** baseline-required for normal operation.

### Files
- `/home/sachin/work/bajaj/quotequery/main.py` - FastAPI backend, intent routing, DB access, query log writes
- `/home/sachin/work/bajaj/quotequery/static/index.html` - UI rendering and clarification/client-search UX
- `/home/sachin/work/bajaj/quotequery/README.md` - v0.1 contract and manual verification checklist

---

## 3. Test PDFs Generated

- `/home/sachin/work/bajaj/quotegen/static/test_final_quote.pdf` - Full test with images & optional sections

---

## 4. What's Working

| Component | Status | Port |
|-----------|--------|------|
| Quote Generator | ✅ Running | 8081 |
| QuoteQuery App | ✅ Running | 8082 |
| PDF Generation | ✅ Working (WeasyPrint) | - |
| Image Upload/Picker | ✅ Working | - |
| GST Auto-fill | ✅ Working | - |
| QuoteQuery Deterministic Intents | ✅ Working | - |
| QuoteQuery Query Logging (`qq_metadata.db`) | ✅ Working | - |

---

## 5. Next Steps (If Needed)

1. Implement and evaluate gated LLM fallback path behind `ENABLE_LLM_RESOLVER`
2. Add explicit API contract tests for the 6 intent handlers and unsupported fallback
3. Add lightweight frontend smoke tests for clarification-chip flow
4. Cache heavy analytics queries if response times regress
5. Add authentication/authorization if external access expands

---

*End of Progress Report*
