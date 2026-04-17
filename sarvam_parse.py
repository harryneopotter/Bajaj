import os
import time
import json
import requests
from pathlib import Path
from sarvamai import SarvamAI

# Load config
# We'll expect SARVAM_API_KEY in .env
MISTRAL_KEY = "2ybpeZmsdS62Cr9vFYVM3DJtp7uHvt6R" # For reference

def parse_with_sarvam(pdf_path, output_dir, api_key):
    if not api_key:
        print("Error: SARVAM_API_KEY not found.")
        return None

    client = SarvamAI(api_subscription_key=api_key)
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Sarvam: Creating job for {pdf_path.name}...")
    
    max_retries = 5
    retry_delay = 5 # seconds
    
    for attempt in range(max_retries):
        try:
            # Step 1: Create Job
            job = client.document_intelligence.create_job(
                language="en-IN", 
                output_format="html"
            )
            job_id = job.job_id
            print(f"Job created: {job_id}")

            # Step 2: Upload File
            job.upload_file(str(pdf_path))
            print("File uploaded.")

            # Step 3: Start Job
            job.start()
            print("Job started. Polling for completion...")

            # Step 4: Wait for completion
            status = job.wait_until_complete()
            print(f"Job finished with state: {status.job_state}")

            if status.job_state == "Completed" or status.job_state == "PartiallyCompleted":
                # Step 5: Download Output
                output_zip = output_dir / f"{pdf_path.stem}_sarvam.zip"
                job.download_output(str(output_zip))
                print(f"Output saved to {output_zip}")
                return output_zip
            else:
                print(f"Job failed: {status}")
                return None

        except Exception as e:
            if "429" in str(e) or "Rate limit" in str(e):
                print(f"Rate limit hit. Retrying in {retry_delay}s... (Attempt {attempt+1}/{max_retries})")
                time.sleep(retry_delay)
                retry_delay *= 2 # Exponential backoff
                continue
            else:
                print(f"Sarvam API Error: {e}")
                return None
    
    print(f"Max retries reached for {pdf_path.name}")
    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf")
    parser.add_argument("--key")
    args = parser.parse_args()
    
    key = args.key or os.getenv("SARVAM_API_KEY")
    parse_with_sarvam(args.pdf, "/home/sachin/work/bajaj/extracted/sarvam", key)
