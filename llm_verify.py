"""
Step 3: Two-tier verification using Kimi-K2 via Synthetic.new (Anthropic-compatible API).

Tier 1: Syntactic verification (JSON only, all files)
Tier 2: Semantic verification (JSON + HTML, only when flagged)

Output: analysis/verified/{filename}.json
"""

import json
import os
import re
import sys
import time
import logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(message)s",
    datefmt="%H:%M:%S",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

try:
    import anthropic
except ImportError:
    log.info("ERROR: anthropic package required. Install with: pip install anthropic")
    sys.exit(1)

# --- Config ---
EXTRACTIONS_DIR = Path("analysis/extractions")
SARVAM_DIR = Path("extracted/sarvam")
OUTPUT_DIR = Path("analysis/verified")
ENV_PATHS = [Path(".env"), Path(os.path.expanduser("~/.openclaw/.env"))]

SYNTHETIC_BASE_URL = "https://api.synthetic.new/anthropic"
KIMI_MODEL = "hf:moonshotai/Kimi-K2-Instruct-0905"
MAX_RETRIES = 3
RETRY_DELAY = 5


def load_env():
    for p in ENV_PATHS:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip('"').strip("'")
                    os.environ.setdefault(key.strip(), val)


TIER1_PROMPT = """You are a data quality verifier for sports equipment business data.

Review this extracted JSON for data quality issues. Check each field:

1. **Product names**: Must be actual product names, NOT:
   - HSN codes (8-digit numbers like 95069990)
   - Accounting terms (Amount, Total, Grand Total, Sub Total, Taxable Value)
   - Dates or date-like strings
   - Bank names or account numbers
   - GST rates or tax descriptions (CGST, SGST, IGST)
   - State names used alone (TELENGANA, HARYANA)

2. **Prices**: Must be positive, reasonable for sports equipment (typically 100-500000 INR)

3. **Brand**: Should be a recognized sports brand (Cosco, Nivia, SG, SS, Yonex, Li-Ning, Stag, etc.) or null. NOT a place name or code.

4. **HSN codes**: Valid 8-digit format or null

5. **GSTIN**: Valid 15-char format (2-digit state code + 10-char PAN + 3 chars) or null

6. **Client name**: Must be an actual organization name. NOT an IRN hash, NOT "Unknown", NOT just a title like "The Admin Officer"

7. **Date**: Valid YYYY-MM-DD or null

8. **Quantity**: Positive integer or null

Return valid JSON only:
{
  "status": "verified" or "needs_review",
  "extraction": { /* the corrected extraction, with fixes applied */ },
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
  "flags": [
    {
      "field": "client.name",
      "value": "The Admin Officer",
      "confidence": "low",
      "reason": "Appears to be a title, not organization name",
      "needs_html": true
    }
  ]
}

For high-confidence issues: apply the fix in "extraction" and log in "fixes".
For low-confidence issues: don't change "extraction", just log in "flags" with needs_html=true.
If items should be removed, remove them from the extraction's items array.
If no issues found: status="verified", fixes=[], flags=[].
"""

TIER2_PROMPT = """You are a data quality verifier. You have the extracted JSON AND the original HTML source.

Compare the extraction against the HTML to verify:
1. Is the client name correct? Is it the actual recipient or was the wrong entity picked?
2. Are product-price pairings correct (right price on the right row)?
3. Are there products in the HTML that the extraction missed?
4. Is the date correct?

Return valid JSON only:
{
  "status": "verified" or "needs_review",
  "extraction": { /* corrected extraction */ },
  "fixes": [ /* any corrections made */ ],
  "flags": [ /* remaining unresolvable issues */ ]
}

Same format as before. Apply high-confidence fixes. Flag low-confidence issues.
"""


def extract_body_text(html_path):
    """Get body content from HTML for Tier 2."""
    from bs4 import BeautifulSoup
    content = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup.find_all(["style", "script"]):
        tag.decompose()
    body = soup.find("body")
    return str(body) if body else soup.get_text()


def call_kimi(client, prompt, content):
    """Call Kimi via Synthetic Anthropic-compatible API."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = client.messages.create(
                model=KIMI_MODEL,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": f"{prompt}\n\n---\n\n{content}"}
                ],
            )
            text = resp.content[0].text

            # Extract JSON from response
            # Try direct parse first
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Find JSON block
                match = re.search(r'\{[\s\S]*\}', text)
                if match:
                    return json.loads(match.group())
                raise ValueError("No valid JSON in response")

        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                log.info(f"    Retry {attempt + 1}: {e}")
                time.sleep(RETRY_DELAY)
            else:
                log.info(f"    FAILED: {e}")
                return None


def main():
    load_env()

    api_key = os.environ.get("SYNTHETIC_API_KEY") or os.environ.get("KILO_API_KEY")
    if not api_key:
        log.info("ERROR: No API key found for Synthetic.new")
        log.info("Set SYNTHETIC_API_KEY or KILO_API_KEY in .env or ~/.openclaw/.env")
        sys.exit(1)

    client = anthropic.Anthropic(
        api_key=api_key,
        base_url=SYNTHETIC_BASE_URL,
    )

    if not EXTRACTIONS_DIR.exists():
        log.info(f"ERROR: {EXTRACTIONS_DIR} not found. Run llm_extract.py first.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    extraction_files = sorted(EXTRACTIONS_DIR.glob("*.json"))
    log.info(f"Verifying {len(extraction_files)} extractions...")

    tier1_done = 0
    tier2_done = 0
    errors = 0
    skipped = 0

    for ext_path in extraction_files:
        out_path = OUTPUT_DIR / ext_path.name

        if out_path.exists():
            skipped += 1
            continue

        extraction = json.loads(ext_path.read_text())
        fname = extraction.get("source_file", ext_path.stem + ".html")

        log.info(f"  [{tier1_done + 1}] {ext_path.name}")

        # --- Tier 1: Syntactic verification (JSON only) ---
        result = call_kimi(client, TIER1_PROMPT, json.dumps(extraction, indent=2))
        if result is None:
            errors += 1
            continue

        tier1_done += 1

        # --- Tier 2: Semantic verification (if flagged) ---
        # Ensure expected keys exist
        result.setdefault("fixes", [])
        result.setdefault("flags", [])
        result.setdefault("extraction", extraction)

        needs_html = any(f.get("needs_html") for f in result.get("flags", []))
        if needs_html:
            html_path = SARVAM_DIR / fname
            if html_path.exists():
                body = extract_body_text(html_path)
                tier2_content = (
                    f"Extracted JSON:\n{json.dumps(result.get('extraction', extraction), indent=2)}"
                    f"\n\n---\n\nOriginal HTML body:\n{body}"
                )
                tier2_result = call_kimi(client, TIER2_PROMPT, tier2_content)
                if tier2_result:
                    # Merge tier 2 results
                    result["extraction"] = tier2_result.get("extraction", result.get("extraction"))
                    result["fixes"].extend(tier2_result.get("fixes", []))
                    result["flags"] = tier2_result.get("flags", [])
                    result["status"] = tier2_result.get("status", result.get("status"))
                    tier2_done += 1
                    log.info(f"    Tier 2 applied")

        # Save
        result["source_file"] = fname
        out_path.write_text(json.dumps(result, indent=2, ensure_ascii=False))

        time.sleep(0.3)

    log.info(f"\nDone. Tier 1: {tier1_done}, Tier 2: {tier2_done}, Skipped: {skipped}, Errors: {errors}")
    log.info(f"Output: {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()
