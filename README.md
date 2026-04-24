# Bajaj Sports — Quotation Intelligence MVP

## 1) Original Problem
Bajaj Sports needed a practical quote-generation workflow that could be demonstrated quickly, but their historical data lived in messy PDFs and inconsistent records.

### Core pain points
- Quotation creation was manual and slow.
- Historical pricing was hard to trust or retrieve quickly.
- OCR outputs from complex invoices/quotes often broke table structure (multi-line rows, column drift).
- Client and product data had noise (IRNs, GST fragments, address leakage into names).
- Team needed a **demo-ready system** without risking production data integrity.

## 2) Proposed Solution
Build an MVP that combines:
1. **Data extraction + verification pipeline** for historical documents.
2. **Clean, queryable pricing memory** (client/product history).
3. **Fast quote-generation UI/API** with intelligent suggestions.
4. **Auditability and safety** (verify-first workflow, production data freeze).

### Solution principles
- **Data Truth first**: verify extracted data before using it for quoting.
- **Human-usable speed**: autocomplete and pricing hints at quote time.
- **Low-risk rollout**: keep production dataset read-only during pre-demo phase.

## 3) Implementation

### A) System architecture
- **Pipeline (agentic):** `Classify -> Extract -> Verify -> Merge`
- **Runtime stack:** FastAPI + SQLite + HTML/JS frontend
- **Operational posture:** pre-demo freeze with controlled candidate cleaned dataset

### B) Document intelligence and extraction
- Migrated OCR workflow to **Sarvam AI Vision (VLM)** for better structural fidelity.
- Added reliability tooling around extraction:
  - provider orchestration/fallback pattern
  - validation before acceptance
  - provenance/logging mindset for traceability

### C) Data cleanup and quality controls
- Processed historical source PDFs into a structured purchase history layer.
- Applied cleaning logic to remove non-name artifacts from client fields.
- Consolidated and curated client/product records for usable autocomplete + price references.

### D) Quote generator MVP
Implemented a quotation MVP with:
- Client autocomplete from history
- Product search/autocomplete
- Suggested pricing logic:
  - show last sold price for same client (+ recency context)
  - otherwise show broader historical range/reference
- GST/totals computation
- Quote persistence in SQLite
- PDF generation path for shareable quotes

### E) Audit and reporting surfaces
- Main app endpoint: `/bajaj`
- Data cleanup report endpoint: `/bajaj/cleanup-report`
- Audit-style verification workflow for checking extracted values against source docs

## 4) Current Status
- **State:** ❄️ Frozen / on hold (pre-demo)
- **Why frozen:** waiting on client-side availability for MVP demo/review
- **Data policy:** production file remains read-only until approval to promote cleaned candidate data

## 5) Verified Live Data Snapshot (checked on 2026-02-25)
> These numbers were validated directly from project files/DB, not memory notes.

### A) Production-safe snapshot (demo-safe references)
- `analysis/customer_purchases.json`: **134** customer records
- `quotegen/quotes.db` (UI quote store): tables `quotes`, `quote_items`
  - current rows: **2 quotes**, **3 quote_items**

### B) Candidate / working snapshot (in-progress, not yet promoted)
- `analysis/customer_purchases_cleaned.json`: **134** cleaned customer records
- Total purchase rows in cleaned history: **1,686**
- Unique products from purchase history: **956**
- `analysis/clean_catalog.json`: **1,250** catalog rows (**956** unique products)
- PDFs currently present under `data/`: **491** (`data/Bills/`: **103**)

## 6) Key Lessons Learned
- “**Verify First**” is non-negotiable for document-heavy workflows.
- Extraction quality alone is not enough; verification + cleanup determine business trust.
- A focused MVP (autocomplete + pricing intelligence + PDF output) delivers immediate operational value.

---

If needed, this README can be expanded into:
- setup/deployment instructions,
- API reference,
- schema docs,
- post-demo promotion checklist (`candidate -> production`).
