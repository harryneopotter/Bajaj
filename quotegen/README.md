# Bajaj Sports - Quotation Generator MVP

A web-based quotation generator with smart pricing suggestions.

## Features

- **Client Autocomplete**: Search clients from past purchase history
- **Product Search**: Find products with pricing suggestions:
  - Shows last price to this specific client (highlighted blue)
  - Shows price ranges from other clients (highlighted orange)
  - Shows standard pricing if no history
- **Live Calculations**: Real-time subtotal, GST (18%), and grand total
- **PDF Generation**: Professional quotation PDFs with WeasyPrint
- **Quote Storage**: SQLite database for all quotes

## Quick Start

```bash
cd /home/sachin/work/bajaj/quotegen
source venv/bin/activate
python main.py
```

Server runs on: http://localhost:8081

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Main UI |
| `/api/clients?q=` | GET | Search clients |
| `/api/products?q=&client=` | GET | Search products with pricing |
| `/api/quotes` | GET | List saved quotes |
| `/api/quotes` | POST | Save a quote |
| `/api/quotes/pdf` | POST | Generate PDF |

## Data Sources

- Product catalog: `/home/sachin/work/bajaj/analysis/clean_catalog.json`
- Customer history: `/home/sachin/work/bajaj/analysis/customer_purchases.json`
- Quotes database: `./quotes.db`

## Dependencies

```
fastapi
uvicorn
weasyprint
```

## Demo Flow

1. Type client name → autocomplete shows matches with purchase count
2. Add items → product search shows pricing hints
3. Adjust quantities/prices → totals update live
4. Click "Generate PDF" → downloads professional quotation

## Next Steps (Post-MVP)

- [ ] Edit existing quotes
- [ ] Email quotation to client
- [ ] Product categories filter
- [ ] Client address book
- [ ] Quote templates
