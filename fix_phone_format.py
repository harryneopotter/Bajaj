import json
import re
from pathlib import Path

# Paths
CANDIDATE_FILE = Path("/home/sachin/work/bajaj/analysis/customer_purchases_cleaned.json")
REPORT_HTML = Path("/home/sachin/work/bajaj/analysis/cleanup_report.html")

def format_phone(phone):
    if not phone: return phone
    # If it's exactly 10 digits, add prefix
    if re.match(r"^\d{10}$", phone):
        return f"+91-{phone}"
    return phone

def main():
    if not CANDIDATE_FILE.exists():
        print("Candidate file not found")
        return

    data = json.loads(CANDIDATE_FILE.read_text())
    changed_count = 0

    for client in data:
        original = client.get("phone")
        if original:
            formatted = format_phone(original)
            if formatted != original:
                client["phone"] = formatted
                changed_count += 1

    # Save cleaned JSON
    CANDIDATE_FILE.write_text(json.dumps(data, indent=2))
    print(f"Updated {changed_count} phones in JSON.")

    # Now update the HTML report (Search & Replace in the HTML string for speed)
    if REPORT_HTML.exists():
        html = REPORT_HTML.read_text()
        # Regex to find the "new" value in the diff and update it
        # Look for <span class="new">9876543210</span>
        # Replace with <span class="new">+91-9876543210</span>
        
        def replace_phone(match):
            val = match.group(1)
            return f'<span class="new">+91-{val}</span>'
            
        new_html = re.sub(r'<span class="new">(\d{10})</span>', replace_phone, html)
        REPORT_HTML.write_text(new_html)
        print("Updated HTML report.")

if __name__ == "__main__":
    main()
