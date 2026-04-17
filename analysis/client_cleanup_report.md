# Client Cleanup Report

- **Source file:** `/home/sachin/work/bajaj/analysis/customer_purchases.json`
- **Cleaned output:** `/home/sachin/work/bajaj/analysis/customer_purchases_cleaned.json`
- **Total records audited:** **134**

## 1) Name Cleanup
- Names changed (overall): **20**
- Prefixes removed (`M/s`, `Messrs`, `The Principal`): **1**
- Leading/trailing whitespace fixes: **0**
- ALL CAPS → Title Case conversions: **19**

## 2) Phone Cleanup
- Phone fields changed (overall): **35**
- Normalized to standard format: **31**
- Labels removed (`Mob:`, `Ph-`, etc.): **0**
- Invalid non-empty phone entries removed: **4**
- Originally empty/missing phone entries: **55**
- Valid phones after cleanup: **75 / 134**

### Invalid Phone Entries Removed (sample/all)
| # | Customer | Original Phone |
|---:|---|---|
| 11 | Apeejay Education Society | `92890101061` |
| 19 | Bajaj Sports | `+91 98141470` |
| 40 | Fédération Internationale de Football Association | `+41(0)43 222 7777` |
| 128 | Uesaka T.E Co.,Ltd | `81-3-3622-8171` |

## 3) GSTIN Validation
- Valid GSTINs: **34**
- Invalid GSTINs flagged: **1**
- Missing/blank GSTINs: **99**

### Invalid GSTIN Records
| # | Customer | GSTIN |
|---:|---|---|
| 94 | Syncotts International(Gurgaon) | `07AAFPB24879ZY` |

## Notes
- Original source file was **not modified**.
- Phone normalization preference used: best available 10-digit number (mobile-preferred when multiple candidates present).
- GSTIN validation regex used: `\d{2}[A-Z]{5}\d{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}`.
