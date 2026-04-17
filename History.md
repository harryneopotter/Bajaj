# History

## 2026-01-20

- Created repository layout with `app/`, `data/`, `docker-compose.yml`, and `.env.example`.
- Implemented FastAPI service with IMAP polling, PDF extraction, SQLite + FTS indexing, and PDF serving.
- Added IMAP test UI for login validation, folder listing, and fetching two sample headers.
- Added one-time backfill mode controlled by `BACKFILL_ALL=true`.
- Improved folder selection logic to handle quoting and modified UTF-7.
- Added ingest logging with timestamps and per-UID status.
- Updated home page to list latest 200 documents by default.
- Documented common Sent folder names in `AGENTS.md`.
