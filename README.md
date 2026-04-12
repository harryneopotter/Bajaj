# Bajaj Sports - Retail Quote Automation & Vault

This project digitizes 70+ years of legacy business history for Bajaj Sports, converting physical and digital PDF archives into a searchable digital twin and an automated quotation generator.

---

## 🏗️ System Architecture

The system consists of two primary layers:
1.  **The Brain (Data Engine):** A pipeline that converts raw PDFs into structured business intelligence (Clients, Products, Pricing History).
2.  **The Tool (Quotation Generator):** A web interface for the staff to build, save, and share professional quotes using the "Brain's" historical data.

---

## ⚙️ The Data Pipeline Process

### Step 1: PDF to Structured HTML (OCR via Sarvam AI)
*   **Script:** `batch_sarvam.py` or `sarvam_parse.py`
*   **Action:** Source PDFs are uploaded to the **Sarvam AI Vision API (VLM)**.
*   **Return:** A ZIP archive containing a high-fidelity `document.html` and page-level metadata.
*   **Storage:** The HTML files are extracted to `/home/sachin/work/bajaj/extracted/sarvam/`.

### Step 2: HTML to JSON (Information Extraction)
*   **Script:** `parse_html.py`
*   **Action:** Uses BeautifulSoup to surgically extract:
    *   **Entity:** Client Name, full address, and phone numbers.
    *   **Context:** Date of quotation/invoice and Invoice Numbers.
    *   **Items:** Detailed product names, brands, technical specs, and unit prices.
*   **Storage:** Data is merged into `analysis/customer_purchases.json` and `analysis/clean_catalog.json`.

### Step 3: Cleaning & Deduping (Surgical Scrubbing)
*   **Script:** `final_production_scrub.py`
*   **Action:** Uses high-reasoning logic and regex to:
    *   Vaporize "Junk" entries (IRNs, GST numbers, header fragments).
    *   Clean designations (e.g., converts "The Principal, ABC School" to "ABC School").
    *   Deduplicate clients with varying names into single, clean records.
*   **Partitioning:** `partition_data.py` separates remaining "noise" into `noise_catalog.json` to keep the production UI clean.

### Step 4: Visual Audit & Verification
*   **Interface:** `https://ltn0nharv1-1.tailb8a9a6.ts.net/bajaj/audit`
*   **Action:** A side-by-side view allows a VLM agent or human user to verify the extracted JSON data against a PNG image of the original PDF page.

---

## 📂 Directory & File Inventory

### 🧠 Data & Analysis
| Path | Purpose |
| :--- | :--- |
| `data/pdf/` | Storage for the original 285+ source PDF documents. |
| `extracted/sarvam/` | High-fidelity HTML reconstructions from Sarvam AI. |
| `analysis/customer_purchases.json` | **Master Client List** (62 verified institutional clients). |
| `analysis/clean_catalog.json` | **Master Product Catalog** (2,400+ historical price points). |
| `analysis/pdf_client_mapping.json` | Audit file linking every PDF to its extracted type and fidelity. |

### 🚀 Application (FastAPI)
| Path | Purpose |
| :--- | :--- |
| `quotegen/` | Main application folder. |
| `quotegen/main.py` | The core server (UI, APIs, PDF & Image generation). |
| `quotegen/quotes.db` | SQLite database storing all **newly created** quotes. |
| `quotegen/static/logo.png` | Production logo for Bajaj & Company. |

### 🛠️ Key Scripts
| Script | Usage |
| :--- | :--- |
| `batch_sarvam.py` | Runs bulk PDF-to-HTML conversion via Sarvam AI. |
| `parse_html.py` | Extracts structured data from Sarvam HTML files. |
| `final_production_scrub.py` | Performs the final cleaning pass on the client list. |
| `generate_mapping.py` | Generates the metadata for the Audit tool. |

---

## 🌐 Endpoints (Production)

*   **Main Generator:** `https://ltn0nharv1-1.tailb8a9a6.ts.net/bajaj`
*   **Client Directory:** `https://ltn0nharv1-1.tailb8a9a6.ts.net/bajaj/directory`
*   **Audit Tool:** `https://ltn0nharv1-1.tailb8a9a6.ts.net/bajaj/audit`

---

## 🏗️ Setup & Ingestion

To ingest a new batch of PDFs:
1.  Place PDFs in `data/pdf/`.
2.  Run `batch_sarvam.py` (Ensure `SARVAM_API_KEY` is set in `.env`).
3.  Run `parse_html.py` to sync the new data to the catalog.
4.  Run `final_production_scrub.py` to clean the new entries.
