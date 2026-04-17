# DATA CLEANING & OCR UPGRADE PLAN

## 1. The "Noise" Problem (Status: Logic-Based Partitioning)
- **Current Fix:** I'm using a `JUNK_KEYWORDS` filter to move footer/header text (GST, ISO, Address fragments) into a `noise_catalog.json`.
- **Next Step:** Implement **Category Clustering**. By grouping similar products (e.g., all "Stag" tables), we can spot outliers. If 90% of items in a cluster have a price, and 10% look like text fragments, we auto-flag the fragments as noise.

## 2. PaddleOCR Upgrade (The "Heavy Lifting")
- **The Issue:** `PyMuPDF` (current) extracts text based on document layers. If a scan is slightly tilted or has complex borders, the text flows together, making "Price" sit 5 lines below "Product."
- **The Solution:** Use **PaddleOCR** with the **Layout Analysis** engine. 
- **Plan:**
  1. **Spatial Mapping:** PaddleOCR gives us (x, y) coordinates for every word. 
  2. **Table Reconstruction:** We can "draw" imaginary boxes around tables. If a price is in the same horizontal row as a product name, they are linked—even if the text extraction order is messy.
  3. **Implementation:** I will write a `paddle_parser.py` that processes the original PDFs and generates a high-fidelity spatial map of every quote.

## 3. Monday Prep (The "Confidence" Pass)
- I'm running a script to verify the **Top 20 most frequent products** to ensure their price ranges aren't being skewed by noise.
- I'll provide a "Scrub UI" next week where the owner can click "Delete" on any junk items they see, which will "teach" the parser to avoid similar patterns in the next 1000 PDFs.

## 4. Environment Check
- I am currently installing `paddleocr` and `paddlepaddle-gpu` on the VM to see if we have the GPU horsepower to run this at scale.
