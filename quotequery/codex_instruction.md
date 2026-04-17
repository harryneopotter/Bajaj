You are executing a strict, surgical refactor of the QuoteQuery prototype into a hardened, deterministic v0.1 Analytics Assistant.

Read the attached spec (`quoteq-final---fdf4465a-48bf-4f02-ab7a-d6b4106434c7.md`) thoroughly. Do not deviate from its constraints.

Critical priorities:
1. RIP OUT the HTML-string backend in `main.py`. Replace it with a Python Intent Registry returning the exact structured JSON contract (with the `proof` object).
2. RIP OUT the `prompt()` hack in `index.html`. Build the `/api/clients/search` endpoint and create a clean inline UI for the "Last Quote" button.
3. ISOLATE all logging. Create `qq_metadata.db` for the `qq_query_log` table. `quotes.db` is strictly READ-ONLY for you.
4. REMOVE the hardcoded IP whitelist in `main.py`.
5. REMOVE the narration LLM completely.

Do not touch `quotegen/`. Do not add React/Vue. Use vanilla JS.

Execute the refactor across `main.py` and `static/index.html`. When you are confident the 6 intents work and the tests pass, exit.
