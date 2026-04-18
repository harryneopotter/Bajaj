Give Codex a **single tight implementation spec**, not a vague “improve QuoteQuery” prompt. The repo currently still has the older prototype path in `quotequery/main.py` and `quotequery/static/index.html` — raw HTML answers, `prompt()`, blocking `requests`, fragile routing, hardcoded IP whitelist, and narration LLM.  
Your newer local drafts already point in the right direction with structured responses, an intent registry, separate `qq_metadata.db`, clarification UI, and async `httpx`.   

So the spec to Codex should be something like this:

---

## Codex spec: QuoteQuery v0.1 hardening and polish

### Project context

This repo contains the Bajaj pipeline, QuoteGen, and QuoteQuery/Analytics Assistant. QuoteGen is the staff-facing operational app and QuoteQuery is the boss-facing retrieval/analytics tool. Do not disturb QuoteGen’s existing database schema or workflows. The repo structure and root docs already reflect the bigger system.  

### Goal

Refactor `quotequery/` into a reliable v0.1 **boss-facing search + light analytics assistant**.

Visible UI label should become **Analytics Assistant**, but keep folder names, URLs, and module names under `quotequery/` for now to avoid repo churn.

### Source of truth for direction

Do **not** preserve the current QuoteQuery prototype behavior from repo main. It must be refactored away from:

* backend HTML strings
* browser `prompt()`
* blocking `requests`
* narration LLM
* hardcoded IP whitelist
* fragile substring routing
  as seen in the current repo files.  

Target architecture should follow the newer local design direction:

* structured API responses
* intent registry
* separate metadata DB
* clarification state
* inline client lookup
* async HTTP for optional LLM resolver
* fixed inactive-client query  

---

## Hard constraints

1. **Do not modify QuoteGen schema**

   * `quotegen/quotes.db` is shared operational data.
   * QuoteQuery must treat it as read-only.
   * Any new tables/logging/aliases must live in a separate `qq_metadata.db`. This pattern already exists in the newer local setup script. 

2. **DB-only runtime by default for v0.1**

   * No runtime external dependency should be required for normal use.
   * LLM resolver may exist behind a feature flag, but must be **disabled by default**.
   * Remove narration LLM entirely.

3. **Keep stack simple**

   * Vanilla HTML/CSS/JS frontend
   * FastAPI backend
   * SQLite source DB + separate SQLite metadata DB

4. **No breaking repo churn**

   * Keep existing `quotequery/` folder
   * Keep `/api/query`
   * Keep current basic analytics/search endpoints unless explicitly improved

---

## Functional scope for v0.1

Support exactly these 6 intents:

1. `last_quote_client`
2. `recent_quotes`
3. `month_summary`
4. `top_clients`
5. `top_products`
6. `inactive_clients`

Visible quick actions should be only **3**:

* This Month
* Quiet Clients
* Last Quote for a Client

“Recent Quotes” should remain supported via query/suggestion chips, not a primary big button.

This is a **search-first tool with light analytics**, not a dashboard.

---

## Backend tasks

### 1. Replace current router with an intent registry

Refactor `quotequery/main.py` to use:

* ordered intent registry
* regex patterns per intent
* explicit parameter extractors
* handler map
* structured response builder

Routing order:

1. `last_quote_client`
2. `month_summary`
3. `inactive_clients`
4. `top_clients`
5. `top_products`
6. `recent_quotes`
7. optional feature-flagged LLM resolver
8. unsupported fallback

Do not use generic substring soup like the current repo version. 

### 2. Structured response contract

`/api/query` must return structured JSON, not raw HTML.

Use a response shape like:

```json
{
  "ok": true,
  "intent": "last_quote_client",
  "answer_type": "quote_record",
  "title": "Last quote to DPS R.K. Puram",
  "summary": "Sent on 2026-04-03 for ₹84,000.",
  "items": [],
  "proof": {
    "source": "quotes",
    "quote_id": 123,
    "client_name": "DPS R.K. Puram",
    "quote_date": "2026-04-03",
    "grand_total": 84000
  },
  "suggestions": ["Recent quotes", "Top clients"],
  "needs_clarification": false,
  "candidates": []
}
```

Supported `answer_type` values:

* `summary`
* `ranked_list`
* `quote_record`
* `clarification`
* `unsupported`

### 3. Add `/api/clients/search`

Add a dedicated endpoint:

* `GET /api/clients/search?q=...&limit=...`

Purpose:

* return candidate canonical client names for inline lookup and clarification chips
* do not fake this through `/api/query`

Response should include:

* client name
* maybe quote count / latest quote date if easy
* ordered relevance

### 4. Basic client normalization

Add lightweight normalization for client search:

* lowercase
* collapse multiple spaces
* strip punctuation where reasonable
* normalize `&` / dots / repeated whitespace

Do **not** overbuild FTS yet.
Do **not** require fuzzy libraries yet.
But do enough so obvious variants like `DPS`, `D.P.S.` behave less stupidly.

If needed, store aliases later in `qq_metadata.db`, not `quotes.db`.

### 5. Keep metadata isolated

Create/use `qq_metadata.db` for:

* `qq_query_log`
* later extensible tables like aliases/audit

Do not write anything into `quotes.db` other than reads.

### 6. Improve query logging

Current local draft has basic query logging. Extend it.

`qq_query_log` should include at least:

* `created_at`
* `raw_text`
* `normalized_text`
* `resolved_intent`
* `params_json`
* `route_source` (`rule`, `llm`, `unsupported`)
* `matched_pattern`
* `answer_type`
* `success`
* `clarification_required`
* `candidate_count`
* `latency_ms`
* `proof_present`
* `error_text`

### 7. Fix latency logging

Measure **end-to-end request latency**, not just routing time.

### 8. SQLite hardening

Since QuoteGen writes and QuoteQuery reads from the same DB:

* set `PRAGMA busy_timeout`
* keep queries short
* fail cleanly on lock errors
* use read-only connection mode for `quotes.db` if practical
* do not add WAL assumptions unless verified safe for the deployment

Traffic is low, so don’t overengineer.

### 9. Remove hardcoded IP whitelist

The repo currently has a hardcoded IP whitelist middleware in `quotequery/main.py`. Replace it with one of these:

* env-configurable allowlist, disabled by default
* or remove it entirely from QuoteQuery

Do not leave hardcoded IPs in app logic. 

### 10. Remove narration LLM

Delete runtime narration LLM completely.
Use deterministic templates for all 6 intents.

### 11. LLM resolver feature flag

Keep optional resolver support, but only if:

* behind `ENABLE_LLM_RESOLVER=false` by default
* async via `httpx`
* strict schema validation
* never used for narration
* clean fallback if unavailable

If disabled or failing, unsupported queries should return a guided message, not vague filler.

### 12. Fix inactive clients query

Keep the corrected version that gets the actual latest row/value per client, not grouped nonsense. The newer local draft already fixes this. 

---

## Frontend tasks

### 1. Rename visible product label

In UI only:

* change visible title from `QuoteQuery` to `Analytics Assistant`

Do not rename folder structure or backend module names yet.

### 2. Remove prototype smell

Refactor `quotequery/static/index.html` away from:

* emoji-heavy buttons
* `prompt()`
* direct trust in backend HTML
* alert-based voice fallback
  as seen in repo main. 

### 3. Keep the newer layout direction

Use a clean mobile-first layout with:

* header
* single answer card
* inline client lookup panel
* main text input
* optional mic
* 3 quick actions

### 4. Use 4 UI render states

Frontend must render:

* summary
* ranked list
* quote record
* clarification
* unsupported

Yes, that is 5 render states if counting unsupported separately. Keep it explicit.

### 5. Add real client search flow

For “Last Quote for a Client”:

* tap button
* show inline client lookup panel
* user types
* query `/api/clients/search`
* show candidate chips or minimal suggestions
* tap candidate
* run `last quote for <canonical client>`

Do not just turn this into “type and pray.”

### 6. Safe rendering

Do **not** interpolate raw DB text into `innerHTML` with inline `onclick` strings.

Requirements:

* escape or sanitize all user/DB text
* attach listeners programmatically
* apostrophes and special chars in client names must not break chips/buttons

This is one of the biggest remaining cracks in the newer local draft.

### 7. Font and visual polish

For v0.1:

* use system font stack, not Google Fonts
* no external font dependency
* remove emojis from core UI
* keep calm premium iPhone-like spacing
* no flashy gradients or fake luxury styling

### 8. Voice UX

Voice remains optional.
If unsupported:

* no alert
* show subtle inline note or hide/disable mic affordance
* text input must remain first-class

### 9. Loading UX

Since v0.1 is DB-only by default:

* simple loading state only
* do not implement slow-path LLM traffic messaging yet

That belongs in later external-call iterations.

---

## Docs and cleanup tasks

Update:

* `quotequery/README.md`
* root `PROGRESS.md`

Docs must reflect the new architecture:

* structured responses
* metadata DB separation
* DB-only v0.1 default
* optional feature-flagged resolver
* new client search endpoint
* Analytics Assistant naming in the UI

The current progress doc is behind the new design. 

---

## Tests Codex must add

### Backend tests

Add tests for:

* intent routing
* parameter extraction
* unsupported fallback
* clarification path
* proof object presence
* inactive-clients correctness
* `/api/clients/search`

### Frontend/manual checks

Document or verify:

* no browser `prompt()`
* no raw HTML answer blobs
* client names with apostrophes don’t break UI
* unsupported query returns guided suggestions
* app works with `ENABLE_LLM_RESOLVER=false`

### Regression query set

Include at least these:

* `last quote for DPS`
* `last quote to IIT Delhi`
* `show me recent quotes`
* `how much business this month`
* `which clients have gone quiet`
* `who are my top clients`
* `what products are quoted most`
* ambiguous client input producing clarification
* unsupported free-text producing clean fallback

---

## Acceptance criteria

Codex should consider the task done only if:

1. `quotequery/main.py` no longer returns backend HTML answer blobs.
2. `quotequery/static/index.html` no longer uses `prompt()`.
3. `qq_metadata.db` is used for all QuoteQuery-owned writes.
4. `quotes.db` is treated as read-only by QuoteQuery.
5. All 6 intents work without runtime LLM dependency.
6. `/api/clients/search` exists and powers the client lookup UX.
7. Frontend no longer injects unsafe strings into inline `onclick`.
8. Narration LLM is removed.
9. Hardcoded IP allowlist is removed or env-gated.
10. `PROGRESS.md` and QuoteQuery docs are updated.

---

## What Codex should not do

* do not rename the `quotequery/` directory
* do not touch QuoteGen schema
* do not add React/Vue/build tooling
* do not add full-text search engines or external dependencies unless clearly necessary
* do not build email/mailbox features yet
* do not add dashboard-heavy UI
* do not make live LLM calls required for core usage

---

## Short instruction to prepend for Codex

Use the existing repo as baseline, but implement the newer hardened QuoteQuery architecture: structured responses, deterministic intent registry, separate `qq_metadata.db`, real client search endpoint, safe frontend rendering, no narration LLM, and visible UI rename to “Analytics Assistant”. Preserve QuoteGen and shared DB compatibility.

---

That’s the spec I’d hand Codex.

The short truth: **tell Codex to stop beautifying the prototype and instead turn it into a strict, boring, trustworthy retrieval tool with slightly nicer clothes.**
