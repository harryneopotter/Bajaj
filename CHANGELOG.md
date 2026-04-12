# CHANGELOG.md

## MVP (2026-02-04)
- **Quotation Generator UI** built at `/quotegen/` - full web interface for creating quotes
- Client autocomplete from parsed purchase history (9 clients)
- Product search with smart pricing suggestions (35 products):
  - Last price to specific client (blue highlight)
  - Price ranges from other clients (orange)
  - Standard pricing fallback
- Live GST (18%) calculation
- PDF generation with professional layout (WeasyPrint)
- SQLite storage for quotes
- Server: `python quotegen/main.py` → http://localhost:8081

## Earlier Work
- Initial docs and README created
- CLI parser concept outlined; SQLite MVP schema defined
- Verification plan drafted; OCR path deferred for MVP
- Document vault with IMAP ingestion (257 emails, 154 docs)
- Catalog parsed from invoices: `analysis/clean_catalog.json`

## Next
- Polish UI for demo
- Add quote editing
- Client address book integration
