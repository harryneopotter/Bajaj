import os
import argparse
import base64
import json
from pathlib import Path
from mistralai import Mistral

# Configuration
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
MODEL = "mistral-ocr-latest"

def parse_pdf_to_markdown(pdf_path, output_dir):
    if not MISTRAL_API_KEY:
        print("Error: MISTRAL_API_KEY environment variable not set.")
        return None

    client = Mistral(api_key=MISTRAL_API_KEY)
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Uploading and parsing: {pdf_path.name}")
    
    # Upload file
    uploaded_file = client.files.upload(
        file={
            "file_name": pdf_path.name,
            "content": pdf_path.read_bytes(),
        },
        purpose="ocr"
    )

    # Get signed URL
    signed_url = client.files.get_signed_url(file_id=uploaded_file.id)

    # Run OCR
    ocr_response = client.ocr.process(
        model=MODEL,
        document={
            "type": "document_url",
            "document_url": signed_url.url,
        }
    )

    # Convert response to markdown
    # Note: Mistral OCR response structure may vary, usually it contains pages with markdown
    full_markdown = ""
    for page in ocr_response.pages:
        full_markdown += page.markdown + "\n\n---\n\n"

    output_path = output_dir / f"{pdf_path.stem}_mistral.md"
    output_path.write_text(full_markdown, encoding="utf-8")
    
    print(f"Successfully saved markdown to: {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Parse PDF using Mistral OCR API")
    parser.add_argument("pdf", help="Path to the PDF file")
    parser.add_argument("--out", default="/home/sachin/work/bajaj/extracted/mistral", help="Output directory")
    
    args = parser.parse_args()
    
    if not os.getenv("MISTRAL_API_KEY"):
        print("Please set MISTRAL_API_KEY environment variable.")
    else:
        parse_pdf_to_markdown(args.pdf, args.out)
