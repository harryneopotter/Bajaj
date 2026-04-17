#!/usr/bin/env python3
"""Local rule-based verifier for extraction JSONs.
Writes output to analysis/verified/*.json with status/fixes/flags similar to llm_verify.
"""
import json
import re
from pathlib import Path

EX_DIR = Path("analysis/extractions")
OUT_DIR = Path("analysis/verified")
OUT_DIR.mkdir(parents=True, exist_ok=True)

HSN_RE = re.compile(r'^\d{8}$')
GSTIN_RE = re.compile(r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$', re.I)

files = sorted(EX_DIR.glob('*.json'))
print(f'Found {len(files)} extraction files')

summary = {'processed':0,'verified':0,'needs_review':0,'fixes':0,'flags':0}

for f in files:
    data = json.loads(f.read_text())
    extraction = data
    fixes = []
    flags = []
    status = 'verified'

    # Client name checks
    client = extraction.get('client',{})
    cname = (client.get('name') or '').strip()
    if not cname or len(cname) < 3 or any(x in cname.lower() for x in ['admin','officer','unknown','the']):
        flags.append({'field':'client.name','value':cname,'confidence':'low','reason':'suspicious client name','needs_html':True})
        status = 'needs_review'

    # GSTIN
    gst = client.get('gstin')
    if gst:
        if not GSTIN_RE.match(gst.strip()):
            fixes.append({'field':'client.gstin','was':gst,'now':None,'action':'removed','confidence':'high','reason':'invalid GSTIN format'})
            extraction.setdefault('client',{})['gstin']=None

    # Date
    date = extraction.get('date')
    if date:
        if not re.match(r'^\d{4}-\d{2}-\d{2}$', str(date)):
            flags.append({'field':'date','value':date,'confidence':'low','reason':'date not in YYYY-MM-DD','needs_html':True})
            status = 'needs_review'

    # Items
    items = extraction.get('items',[])
    new_items = []
    for idx,item in enumerate(items):
        prod = (item.get('product') or '').strip()
        brand = item.get('brand')
        qty = item.get('quantity')
        price = item.get('unit_price')
        # If product is purely 8-digit number, treat as HSN and remove
        if HSN_RE.match(prod):
            fixes.append({'field':f'items[{idx}].product','was':prod,'now':None,'action':'removed','confidence':'high','reason':'HSN code parsed as product name'})
            continue
        # Price sanity
        if price is None:
            flags.append({'field':f'items[{idx}].unit_price','value':price,'confidence':'low','reason':'missing price','needs_html':True})
            status='needs_review'
        else:
            try:
                p = float(price)
                if p<=0 or p>10000000:
                    flags.append({'field':f'items[{idx}].unit_price','value':price,'confidence':'low','reason':'price out of expected range','needs_html':True})
                    status='needs_review'
            except Exception:
                flags.append({'field':f'items[{idx}].unit_price','value':price,'confidence':'low','reason':'price parse error','needs_html':True})
                status='needs_review'
        # Quantity sanity
        if qty is not None:
            try:
                q = int(qty)
                if q<=0 or q>10000:
                    flags.append({'field':f'items[{idx}].quantity','value':qty,'confidence':'low','reason':'quantity out of range','needs_html':True})
                    status='needs_review'
            except Exception:
                flags.append({'field':f'items[{idx}].quantity','value':qty,'confidence':'low','reason':'quantity parse error','needs_html':True})
                status='needs_review'
        new_items.append(item)

    extraction['items']=new_items

    out = {'status':status,'extraction':extraction,'fixes':fixes,'flags':flags,'source_file':extraction.get('source_file')}
    out_path = OUT_DIR / f.name
    out_path.write_text(json.dumps(out,indent=2,ensure_ascii=False))

    summary['processed']+=1
    if status=='verified': summary['verified']+=1
    else: summary['needs_review']+=1
    summary['fixes']+=len(fixes)
    summary['flags']+=len(flags)

print('Done. Summary:')
print(json.dumps(summary,indent=2))
