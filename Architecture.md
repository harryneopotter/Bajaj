# Architecture

## Overview

Quote Vault ingests PDFs from a Google Workspace mailbox (Sent folder), extracts text, stores PDFs + text on disk, indexes metadata in SQLite FTS, and serves a lightweight web UI for search and PDF retrieval. It runs as a single FastAPI service in Docker.

## Requirements to Run

- Ubuntu or similar Linux host
- Docker + Docker Compose plugin
- Google Workspace mailbox with IMAP enabled and an app password
- Open inbound port (default 8080) or reverse proxy to 80/443

Configuration is via `.env` (see `.env.example`).

## Moving Parts

- **FastAPI app** (`app/main.py`)
  - IMAP poller thread (background)
  - PDF extraction via PyMuPDF
  - SQLite storage + FTS index
  - Web UI: search, list, PDF open
  - IMAP test UI for login + sample header fetch
- **SQLite DB** (`/data/quotevault.db`)
  - `emails`, `docs`, `docs_fts`, and `meta` tables
  - `meta` stores one-time backfill flag
- **Filesystem storage** (`/data/pdf`, `/data/text`)
  - PDFs and extracted text, organized by year/month
- **Docker Compose** (`docker-compose.yml`)
  - Single service container with `/data` volume

## Data Flow

1) IMAP poller connects to Gmail IMAP over SSL.
2) Sent folder is selected (handles quoted/UTF-7 variations).
3) New emails are fetched by UID.
4) PDF attachments are stored under `/data/pdf/YYYY/MM/`.
5) Text is extracted to `/data/text/YYYY/MM/`.
6) Metadata + FTS content is stored in SQLite.
7) Web UI reads from SQLite and serves PDF links.

## One-Time Backfill

Set `BACKFILL_ALL=true` to ingest all historical Sent mail once. The app records `backfill_done` in `meta` and then returns to incremental mode.

## Web UI Endpoints

- `/`: list latest 200 documents, search inputs at top
- `/search`: filtered search results
- `/pdf/{id}`: serves the stored PDF
- `/imap-test`: login/folder check and fetch 2 sample headers

## Diagram

```text
              +------------------------------+
              |        Web Browser           |
              |  /   /search   /imap-test    |
              +---------------+--------------+
                              |
                              v
                    +-------------------+
                    |  FastAPI Service  |
                    |  app/main.py      |
                    +---------+---------+
                              |
      +-----------------------+-----------------------+
      |                                               |
      v                                               v
+-------------+                                +-------------+
|  Gmail IMAP |                                |   SQLite    |
|  Sent Mail  |                                | quotevault  |
+------+------+                                +------+------+ 
       |                                                |
       v                                                v
 +-------------+                               +----------------+
 |   PDFs      |                               |  FTS Index     |
 | /data/pdf   |                               | docs_fts       |
 +------+------+\                              +----------------+
        |
        v
 +-------------+
 |   Text      |
 | /data/text  |
 +-------------+
```

## Operational Notes

- If ingest is idle, check logs: `docker logs -f quotevault`.
- Sent folder names can vary; common values are `Sent Messages` or `[Gmail]/Sent Mail`.
- The IMAP test UI is for validation and does not persist credentials.
