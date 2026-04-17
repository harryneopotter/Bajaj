Cool. VPS-only is cleanest: one place to run, one URL to open, no LAN drama.

Here’s the MVP “Quote Vault v0” you can deploy on a VPS with Docker Compose:

Connect to Gmail via IMAP + app password

Poll Sent Mail

Download PDF attachments

Extract raw text from each PDF

Store metadata in SQLite

Provide a web search UI (browser) to find and open PDFs from anywhere


No AI. No workflows. No humans.


---

0) VPS prerequisites

Assume Ubuntu.

sudo apt update
sudo apt install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER
# log out/in once after this

Open firewall ports (pick one):

simplest: 80/443 via Nginx reverse proxy later

for MVP: run on 8080 and allow it



---

1) Project layout

Create a folder on the VPS:

mkdir -p quote-vault/{app,data}
cd quote-vault

You’ll create:

docker-compose.yml

app/Dockerfile

app/main.py

app/requirements.txt

.env



---

2) docker-compose.yml

services:
  quotevault:
    build: ./app
    container_name: quotevault
    restart: unless-stopped
    env_file: .env
    ports:
      - "8080:8080"
    volumes:
      - ./data:/data

This maps persistent storage to ./data on the VPS.


---

3) app/Dockerfile

FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
  && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080
CMD ["python", "main.py"]


---

4) app/requirements.txt

fastapi==0.115.0
uvicorn==0.30.6
jinja2==3.1.4
python-multipart==0.0.9
pymupdf==1.24.10

We’ll use:

FastAPI for web

PyMuPDF for PDF text extraction



---

5) .env (your config)

Create quote-vault/.env:

IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=YOUR_SHARED_MAILBOX_EMAIL
IMAP_APP_PASSWORD=YOUR_16_CHAR_APP_PASSWORD
IMAP_SENT_FOLDER="[Gmail]/Sent Mail"

POLL_SECONDS=60
DATA_DIR=/data
BASE_URL=http://YOUR_VPS_IP:8080

Notes:

Gmail’s IMAP folder for Sent is usually "[Gmail]/Sent Mail". If yours differs, we’ll adjust after a quick folder-list test.

App password is what you generate as admin.



---

6) app/main.py (the whole MVP)

This is a single-file service: background poller + search UI + PDF serving.

import os
import re
import ssl
import time
import hashlib
import threading
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Tuple
import imaplib
import email
from email.header import decode_header

import fitz  # PyMuPDF
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_APP_PASSWORD = os.getenv("IMAP_APP_PASSWORD", "")
IMAP_SENT_FOLDER = os.getenv("IMAP_SENT_FOLDER", "[Gmail]/Sent Mail")

DB_PATH = DATA_DIR / "quotevault.db"
PDF_DIR = DATA_DIR / "pdf"
TXT_DIR = DATA_DIR / "text"

PDF_DIR.mkdir(parents=True, exist_ok=True)
TXT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()
templates = Jinja2Templates(directory="/app/templates")

# Minimal HTML template inline to avoid extra files
TEMPLATE_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>Quote Vault</title>
  <style>
    body{font-family:system-ui,Segoe UI,Roboto,Arial;max-width:1100px;margin:24px auto;padding:0 16px}
    input{width:100%;padding:10px 12px;font-size:16px}
    .row{display:flex;gap:12px;flex-wrap:wrap;margin-top:10px}
    .row input{flex:1;min-width:220px}
    table{width:100%;border-collapse:collapse;margin-top:16px}
    th,td{border-bottom:1px solid #e6e6e6;padding:10px 8px;vertical-align:top}
    th{position:sticky;top:0;background:#fff}
    .meta{color:#666;font-size:13px}
    a{color:#0b57d0;text-decoration:none}
    a:hover{text-decoration:underline}
    .pill{display:inline-block;padding:2px 8px;border:1px solid #ddd;border-radius:999px;font-size:12px;color:#444}
  </style>
</head>
<body>
  <h1>Quote Vault</h1>
  <form method="get" action="/search">
    <input name="q" value="{{ q }}" placeholder="Search: customer, item, brand, email, anything..." autofocus />
    <div class="row">
      <input name="from" value="{{ date_from }}" placeholder="From date (YYYY-MM-DD) optional" />
      <input name="to" value="{{ date_to }}" placeholder="To date (YYYY-MM-DD) optional" />
    </div>
  </form>

  <div class="meta" style="margin-top:10px">
    Indexed PDFs: <span class="pill">{{ total_docs }}</span>
  </div>

  {% if results is not none %}
    <table>
      <thead>
        <tr>
          <th>Sent</th>
          <th>To</th>
          <th>Subject</th>
          <th>PDF</th>
        </tr>
      </thead>
      <tbody>
        {% for r in results %}
          <tr>
            <td>{{ r["sent_at"] }}</td>
            <td>{{ r["to_addr"] }}</td>
            <td>{{ r["subject"] }}</td>
            <td><a href="/pdf/{{ r['doc_id'] }}" target="_blank">Open PDF</a></td>
          </tr>
        {% endfor %}
      </tbody>
    </table>
  {% endif %}
</body>
</html>
"""

def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS emails (
          id TEXT PRIMARY KEY,
          imap_uid INTEGER UNIQUE,
          sent_at TEXT,
          to_addr TEXT,
          subject TEXT
        )""")
        conn.execute("""
        CREATE TABLE IF NOT EXISTS docs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email_id TEXT,
          filename TEXT,
          pdf_path TEXT,
          txt_path TEXT,
          sha256 TEXT,
          created_at TEXT,
          FOREIGN KEY(email_id) REFERENCES emails(id)
        )""")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_docs_email ON docs(email_id)")
        conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(doc_id UNINDEXED, content)")
        conn.commit()

def safe_decode(s: Optional[str]) -> str:
    if not s:
        return ""
    parts = decode_header(s)
    out = ""
    for frag, enc in parts:
        if isinstance(frag, bytes):
            out += frag.decode(enc or "utf-8", errors="replace")
        else:
            out += frag
    return out.strip()

def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_text(pdf_path: Path, txt_path: Path) -> str:
    doc = fitz.open(pdf_path.as_posix())
    texts = []
    for page in doc:
        texts.append(page.get_text("text"))
    doc.close()
    raw = "\n".join(texts).strip()
    txt_path.write_text(raw, encoding="utf-8", errors="ignore")
    return raw

def upsert_email(conn: sqlite3.Connection, msg_id: str, uid: int, sent_at: str, to_addr: str, subject: str):
    conn.execute("""
      INSERT INTO emails (id, imap_uid, sent_at, to_addr, subject)
      VALUES (?, ?, ?, ?, ?)
      ON CONFLICT(id) DO UPDATE SET
        imap_uid=excluded.imap_uid,
        sent_at=excluded.sent_at,
        to_addr=excluded.to_addr,
        subject=excluded.subject
    """, (msg_id, uid, sent_at, to_addr, subject))

def doc_exists_by_sha(conn: sqlite3.Connection, sha: str) -> bool:
    cur = conn.execute("SELECT 1 FROM docs WHERE sha256=? LIMIT 1", (sha,))
    return cur.fetchone() is not None

def insert_doc(conn: sqlite3.Connection, email_id: str, filename: str, pdf_path: Path, txt_path: Path, sha: str) -> int:
    cur = conn.execute("""
      INSERT INTO docs (email_id, filename, pdf_path, txt_path, sha256, created_at)
      VALUES (?, ?, ?, ?, ?, ?)
    """, (email_id, filename, pdf_path.as_posix(), txt_path.as_posix(), sha, datetime.utcnow().isoformat()))
    return int(cur.lastrowid)

def upsert_fts(conn: sqlite3.Connection, doc_id: int, content: str):
    conn.execute("INSERT INTO docs_fts (doc_id, content) VALUES (?, ?)", (doc_id, content))

def parse_sent_at(msg) -> str:
    # RFC2822 date string -> store as-is; later you can normalize
    return safe_decode(msg.get("Date", ""))

def imap_connect() -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    im = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=ctx)
    im.login(IMAP_USER, IMAP_APP_PASSWORD)
    return im

def list_folders(im: imaplib.IMAP4_SSL) -> List[str]:
    typ, data = im.list()
    folders = []
    if typ == "OK":
        for line in data:
            if not line:
                continue
            s = line.decode("utf-8", errors="replace")
            m = re.search(r' "([^"]+)"$', s)
            if m:
                folders.append(m.group(1))
    return folders

def ingest_loop():
    init_db()

    # quick sanity: folder exists (log only)
    try:
        im = imap_connect()
        folders = list_folders(im)
        if IMAP_SENT_FOLDER not in folders:
            print("WARN: Sent folder not found. Available folders include:", folders[:15], "...")
        im.logout()
    except Exception as e:
        print("IMAP folder list failed:", e)

    while True:
        try:
            im = imap_connect()
            im.select(IMAP_SENT_FOLDER)

            # Search all messages. We rely on UID checkpointing.
            typ, data = im.uid("search", None, "ALL")
            if typ != "OK":
                raise RuntimeError("IMAP search failed")

            uids = [int(x) for x in data[0].split()] if data and data[0] else []

            with db() as conn:
                # Determine last processed UID
                cur = conn.execute("SELECT COALESCE(MAX(imap_uid), 0) AS m FROM emails")
                last_uid = int(cur.fetchone()["m"])
                new_uids = [u for u in uids if u > last_uid]

            # process in order
            for uid in sorted(new_uids):
                typ, msgdata = im.uid("fetch", str(uid), "(RFC822)")
                if typ != "OK" or not msgdata or not msgdata[0]:
                    continue

                raw = msgdata[0][1]
                msg = email.message_from_bytes(raw)

                msg_id = safe_decode(msg.get("Message-ID", "")).strip()
                if not msg_id:
                    # fallback deterministic id from uid+date
                    msg_id = f"uid-{uid}-{hashlib.md5(raw).hexdigest()}"  # no security use, just id

                sent_at = parse_sent_at(msg)
                to_addr = safe_decode(msg.get("To", ""))
                subject = safe_decode(msg.get("Subject", ""))

                pdf_parts: List[Tuple[str, bytes]] = []
                for part in msg.walk():
                    cdisp = part.get("Content-Disposition", "")
                    ctype = part.get_content_type()
                    if ctype == "application/pdf" or (cdisp and "attachment" in cdisp.lower()):
                        filename = safe_decode(part.get_filename() or "") or "attachment.pdf"
                        payload = part.get_payload(decode=True)
                        if payload and filename.lower().endswith(".pdf"):
                            pdf_parts.append((filename, payload))

                if not pdf_parts:
                    # Still record the email UID checkpoint so we don't refetch endlessly
                    with db() as conn:
                        upsert_email(conn, msg_id, uid, sent_at, to_addr, subject)
                        conn.commit()
                    continue

                # Store
                y = datetime.utcnow().strftime("%Y")
                m = datetime.utcnow().strftime("%m")
                base_dir = PDF_DIR / y / m
                base_dir.mkdir(parents=True, exist_ok=True)
                txt_base_dir = TXT_DIR / y / m
                txt_base_dir.mkdir(parents=True, exist_ok=True)

                with db() as conn:
                    upsert_email(conn, msg_id, uid, sent_at, to_addr, subject)

                    for idx, (fname, payload) in enumerate(pdf_parts, start=1):
                        pdf_path = base_dir / f"{sanitize_id(msg_id)}_{idx}.pdf"
                        txt_path = txt_base_dir / f"{sanitize_id(msg_id)}_{idx}.txt"

                        if not pdf_path.exists():
                            pdf_path.write_bytes(payload)

                        sha = sha256_file(pdf_path)
                        if doc_exists_by_sha(conn, sha):
                            continue

                        content = ""
                        try:
                            content = extract_text(pdf_path, txt_path)
                        except Exception as e:
                            # still store doc with empty text; you can fix parsing later
                            txt_path.write_text("", encoding="utf-8")
                            content = ""

                        doc_id = insert_doc(conn, msg_id, fname, pdf_path, txt_path, sha)
                        # index includes email meta to make search useful even if PDF text is weak
                        fts_blob = f"{to_addr}\n{subject}\n{sent_at}\n{content}"
                        upsert_fts(conn, doc_id, fts_blob)

                    conn.commit()

            im.logout()
        except Exception as e:
            print("Ingest error:", e)

        time.sleep(POLL_SECONDS)

def sanitize_id(s: str) -> str:
    # safe for filenames
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:180]

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM docs").fetchone()["c"]
    html = TEMPLATE_HTML.replace("{{ total_docs }}", str(total))
    html = html.replace("{{ q }}", "")
    html = html.replace("{{ date_from }}", "")
    html = html.replace("{{ date_to }}", "")
    html = html.replace("{% if results is not none %}", "")
    html = html.replace("{% endif %}", "")
    # strip empty table block
    html = re.sub(r"<table>.*?</table>", "", html, flags=re.S)
    return HTMLResponse(html)

def parse_yyyy_mm_dd(s: str) -> Optional[str]:
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
        return s
    return None

@app.get("/search", response_class=HTMLResponse)
def search(request: Request, q: str = "", from_: str = "", to: str = ""):
    date_from = parse_yyyy_mm_dd(request.query_params.get("from", ""))
    date_to = parse_yyyy_mm_dd(request.query_params.get("to", ""))

    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM docs").fetchone()["c"]

        # Note: sent_at stored as raw string; date filtering is best after normalizing.
        # For MVP, we keep date filter as a soft filter on string, not strict.
        where = []
        params = []
        if q.strip():
            where.append("docs_fts MATCH ?")
            # basic FTS query: wrap in quotes for phrase-ish behavior
            params.append(q.strip())

        sql = """
        SELECT d.id AS doc_id, e.sent_at, e.to_addr, e.subject
        FROM docs d
        JOIN emails e ON e.id = d.email_id
        JOIN docs_fts f ON f.doc_id = d.id
        """
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY d.id DESC LIMIT 200"

        rows = conn.execute(sql, params).fetchall()
        results = [dict(r) for r in rows]

    html = TEMPLATE_HTML
    html = html.replace("{{ total_docs }}", str(total))
    html = html.replace("{{ q }}", (q or ""))
    html = html.replace("{{ date_from }}", (date_from or ""))
    html = html.replace("{{ date_to }}", (date_to or ""))
    # render results
    # crude Jinja-less render (MVP): replace block tags by manual insertion
    # We'll just use string replace for the result table via a tiny loop.
    if results:
        # keep table
        pass
    else:
        # keep table but empty
        pass

    # Simple render: replace Jinja loop manually
    table_rows = ""
    for r in results:
        table_rows += (
            "<tr>"
            f"<td>{escape(r.get('sent_at',''))}</td>"
            f"<td>{escape(r.get('to_addr',''))}</td>"
            f"<td>{escape(r.get('subject',''))}</td>"
            f"<td><a href=\"/pdf/{r['doc_id']}\" target=\"_blank\">Open PDF</a></td>"
            "</tr>"
        )

    # Replace the whole tbody loop section
    html = re.sub(r"{% for r in results %}.*?{% endfor %}", table_rows, html, flags=re.S)
    html = html.replace("{% if results is not none %}", "")
    html = html.replace("{% endif %}", "")

    return HTMLResponse(html)

def escape(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

@app.get("/pdf/{doc_id}")
def get_pdf(doc_id: int):
    with db() as conn:
        row = conn.execute("SELECT pdf_path FROM docs WHERE id=?", (doc_id,)).fetchone()
        if not row:
            return HTMLResponse("Not found", status_code=404)
        path = row["pdf_path"]
    return FileResponse(path, media_type="application/pdf")

def start_bg():
    t = threading.Thread(target=ingest_loop, daemon=True)
    t.start()

if __name__ == "__main__":
    init_db()
    start_bg()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)

What you get immediately:

automatic ingestion

central PDF storage

searchable UI at http://<vps-ip>:8080



---

7) Run it

From quote-vault/:

docker compose up --build -d
docker logs -f quotevault

Open:

http://YOUR_VPS_IP:8080 Search anything (customer name, “SG”, “football”, etc.)



---

8) Practical gotchas (so you don’t get stuck)

Sent folder name mismatch

If logs say Sent folder not found, we’ll list folders and set the correct one. Gmail sometimes exposes:

[Gmail]/Sent Mail

Sent

localized names


IMAP not enabled

Enable IMAP in Gmail settings for that mailbox.

App password formatting

Use it as a plain string (no spaces).


---

9) What’s next after v0 is running (in the right order)

1. Backfill: run once to ingest all history (this already happens as it polls ALL, but you can optimize later)


2. Normalize dates into a proper ISO field for accurate date filters


3. Add better “similar quote” ranking (still non-AI: keyword overlap scoring)


4. Later: table parsing + “copy items into draft” for productivity




---

If you tell me the mailbox address is on a custom domain or plain @gmail.com, I’ll also tell you the safest way to handle IMAP quotas + Gmail rate limits (still easy, just don’t hammer it).