# Bajaj Sports - Development Progress

**Last Updated:** April 15, 2026

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

### Purpose
Simple voice/text chatbot for the "Oldman of Bajaj Sports" to query quotes without dashboards.

### Features Implemented
- ✅ **Big Button UI** - 6 large tap targets (Recent Quotes, This Month, Top Clients, etc.)
- ✅ **Voice Input** - Web Speech API (works on iPhone Safari)
- ✅ **Analytics Endpoints:**
  - `GET /api/analytics/quotes/summary` - Total quotes, value, average
  - `GET /api/analytics/clients/top` - Rank clients by count/value
  - `GET /api/analytics/products/top` - Most quoted products
  - `GET /api/quotes/search` - Full-text search across quotes
  - `GET /api/analytics/quotes/inactive-clients` - Clients with no recent quotes
- ✅ **Heuristic Resolver** - Handles common queries without LLM
- ✅ **LLM Intent Resolver** - Uses Google AI Studio (Gemma 3-31B) to resolve complex queries
- ✅ **Response Narration** - Converts API results to plain English

### Configuration
- API Key: Loaded from `/home/sachin/work/bajaj/quotequery/.env` (AI_STUDIO_KEY)
- Model: `gemma-3-31b` via Google Generative Language API

### Files Created
- `/home/sachin/work/bajaj/quotequery/main.py` - FastAPI backend
- `/home/sachin/work/bajaj/quotequery/static/index.html` - Frontend UI
- `/home/sachin/work/bajaj/quotequery/static/manifest.json` - PWA manifest

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
| LLM Resolver | ✅ Configured | - |

---

## 5. Next Steps (If Needed)

1. Add more heuristic patterns to QuoteQuery
2. Wire up PDF download button in QuoteQuery for "last quote to X"
3. Add client picker UI for "Last Quote to..." button
4. Cache heavy analytics queries
5. Add authentication if needed

---

*End of Progress Report*
