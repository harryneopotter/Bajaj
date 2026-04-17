# TEXTRACT INTEGRATION PLAN

## 1. Why Textract?
- **Spatial Accuracy:** The JSON sample Ken provided proves Textract is superior at maintaining row-level horizontal alignment in complex Bajaj "Block" layouts.
- **Handwriting Support:** If any of the 1000s of PDFs have handwritten notes or old typed characters, Textract will significantly outperform local engines.

## 2. Hybrid Execution Strategy
To optimize for both **Speed** and **Cost**, I will implement a "Smart Router":
1.  **Tier 1 (Local):** Process clean, text-based PDFs using `PyMuPDF`. (0 cost, instant).
2.  **Tier 2 (Textract):** If Tier 1 fails to find items or hits a "Block" layout pattern, the system will auto-route the PDF to Textract using the API credentials.

## 3. Preparation for Monday
- I have prepared a `textract_router.py` stub. 
- Once Ken provides `AWS_ACCESS_KEY` and `AWS_SECRET_KEY`, we can unblock the "Big Ingestion."

## 4. Current Database Cleanliness
- I am running a final `cleanup_catalog.py` to remove the date/header fragments (like "30 October") from the `clean_catalog.json` so the demo UI is surgical.
