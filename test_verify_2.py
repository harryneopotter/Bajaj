"""
Quick test: Verify 2 extracted PDFs using BlackboxAI
"""
import json
import os
import sys
import time
from pathlib import Path
from openai import OpenAI

# Load env
env_paths = [Path(".env"), Path(os.path.expanduser("~/.openclaw/.env"))]
for p in env_paths:
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                os.environ.setdefault(key.strip(), val)

api_key = os.environ.get("BLACKBOX_API_KEY")
if not api_key:
    print("ERROR: BLACKBOX_API_KEY not found")
    sys.exit(1)

client = OpenAI(
    api_key=api_key,
    base_url="https://api.blackbox.ai",
)

EXTRACTIONS_DIR = Path("analysis/extractions")
OUTPUT_DIR = Path("analysis/verified")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

MODEL = "gpt-4"  # Standard model name

TIER1_PROMPT = """You are a data quality verifier for sports equipment business data.

Review this extracted JSON for data quality issues. Check each field:

1. **Product names**: Must be actual product names, NOT HSN codes, dates, accounting terms, or tax descriptions
2. **Prices**: Must be positive, reasonable for sports equipment (100-500000 INR)
3. **Brand**: Recognized sports brand or null
4. **Client name**: Actual organization name, not titles or "Unknown"

Return valid JSON only:
{
  "status": "verified" or "needs_review",
  "extraction": { /* corrected extraction with fixes applied */ },
  "fixes": [
    {
      "field": "items[2].product",
      "was": "95069990",
      "now": null,
      "action": "removed",
      "confidence": "high",
      "reason": "HSN code parsed as product name"
    }
  ],
  "flags": []
}

For high-confidence issues: apply the fix in "extraction" and log in "fixes".
If no issues: status="verified", fixes=[], flags=[].
"""

test_files = [
    "Scottish High Intl. School.json",
    "DPS Intl., Gurgaon.json"
]

for fname in test_files:
    ext_path = EXTRACTIONS_DIR / fname
    out_path = OUTPUT_DIR / fname
    
    if out_path.exists():
        print(f"SKIP: {fname} (already verified)")
        continue
    
    if not ext_path.exists():
        print(f"ERROR: {fname} extraction not found")
        continue
    
    extraction = json.loads(ext_path.read_text())
    print(f"Verifying: {fname}")
    
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": TIER1_PROMPT},
                {"role": "user", "content": json.dumps(extraction, indent=2)},
            ],
            temperature=0,
            response_format={"type": "json_object"},
        )
        text = resp.choices[0].message.content
        result = json.loads(text)
        
        # Ensure keys exist
        result.setdefault("fixes", [])
        result.setdefault("flags", [])
        result.setdefault("extraction", extraction)
        result.setdefault("status", "verified")
        result["source_file"] = extraction.get("source_file", fname.replace(".json", ".html"))
        
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        
        # Summary
        fixes_count = len(result.get("fixes", []))
        flags_count = len(result.get("flags", []))
        print(f"  ✓ {result['status']}: {fixes_count} fixes, {flags_count} flags")
        
        time.sleep(0.5)
        
    except Exception as e:
        print(f"  ERROR: {e}")

print("\nVerification complete.")
