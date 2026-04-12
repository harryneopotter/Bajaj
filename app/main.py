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
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, FileResponse

DATA_DIR = Path(os.getenv("DATA_DIR", "/data"))
POLL_SECONDS = int(os.getenv("POLL_SECONDS", "60"))

IMAP_HOST = os.getenv("IMAP_HOST", "imap.gmail.com")
IMAP_PORT = int(os.getenv("IMAP_PORT", "993"))
IMAP_USER = os.getenv("IMAP_USER", "")
IMAP_APP_PASSWORD = os.getenv("IMAP_APP_PASSWORD", "")
IMAP_SENT_FOLDER = os.getenv("IMAP_SENT_FOLDER", "[Gmail]/Sent Mail")
BACKFILL_ALL = os.getenv("BACKFILL_ALL", "true").strip().lower() in {"1", "true", "yes"}

DB_PATH = DATA_DIR / "quotevault.db"
PDF_DIR = DATA_DIR / "pdf"
TXT_DIR = DATA_DIR / "text"

PDF_DIR.mkdir(parents=True, exist_ok=True)
TXT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI()

SEARCH_TEMPLATE_HTML = """
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
    .nav{margin-bottom:12px;font-size:14px}
  </style>
</head>
<body>
  <div class="nav"><a href="/imap-test">IMAP Test</a></div>
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

IMAP_TEST_HTML = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>IMAP Test</title>
  <style>
    body{font-family:system-ui,Segoe UI,Roboto,Arial;max-width:860px;margin:24px auto;padding:0 16px}
    input,select{width:100%;padding:10px 12px;font-size:15px}
    label{display:block;margin-top:12px;font-size:13px;color:#555}
    button{margin-top:14px;padding:10px 16px;font-size:14px;cursor:pointer}
    .row{display:flex;gap:12px;flex-wrap:wrap}
    .row .col{flex:1;min-width:220px}
    pre{background:#f6f6f6;padding:12px;border-radius:8px;white-space:pre-wrap}
    a{color:#0b57d0;text-decoration:none}
  </style>
</head>
<body>
  <div><a href="/">Back to Search</a></div>
  <h1>IMAP Test</h1>
  <form method="post" action="/imap-test">
    <label>IMAP Host</label>
    <input name="host" value="{{ host }}" placeholder="imap.gmail.com" />

    <div class="row">
      <div class="col">
        <label>Port</label>
        <input name="port" value="{{ port }}" placeholder="993" />
      </div>
      <div class="col">
        <label>Folder</label>
        <input name="folder" value="{{ folder }}" placeholder="[Gmail]/Sent Mail" />
      </div>
    </div>

    <label>User</label>
    <input name="user" value="{{ user }}" placeholder="you@yourdomain.com" />

    <label>App Password</label>
    <input type="password" name="password" value="" placeholder="16-char app password" />

    <div class="row">
      <div class="col"><button type="submit" name="action" value="test">Test Connection</button></div>
      <div class="col"><button type="submit" name="action" value="fetch">Fetch 2 Emails</button></div>
    </div>
  </form>

  {% if output %}
    <h2>Result</h2>
    <pre>{{ output }}</pre>
  {% endif %}
</body>
</html>
"""

def log_event(msg: str):
    ts = datetime.utcnow().isoformat(timespec="seconds")
    print(f"[{ts}Z] {msg}", flush=True)


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
        conn.execute("""
        CREATE TABLE IF NOT EXISTS meta (
          key TEXT PRIMARY KEY,
          value TEXT
        )""")
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
    return safe_decode(msg.get("Date", ""))


def imap_connect(host: str, port: int, user: str, password: str) -> imaplib.IMAP4_SSL:
    ctx = ssl.create_default_context()
    im = imaplib.IMAP4_SSL(host, port, ssl_context=ctx)
    im.login(user, password)
    return im


def imap_select_folder(im: imaplib.IMAP4_SSL, folder: str, readonly: bool = True):
    base = folder or "INBOX"
    candidates = [base]

    quote_fn = getattr(im, "_quote", None)
    if callable(quote_fn):
        candidates.append(quote_fn(base))

    encode_fn = getattr(imaplib, "EncodeUTF7", None)
    if callable(encode_fn):
        encoded = encode_fn(base)
        candidates.append(encoded)
        if callable(quote_fn):
            candidates.append(quote_fn(encoded))

    last = ("NO", [b"no candidates attempted"])
    for cand in candidates:
        try:
            typ, data = im.select(cand, readonly=readonly)
            if typ == "OK":
                return typ, data, cand
            last = (typ, data)
        except imaplib.IMAP4.error:
            last = ("NO", [b"select error"])
            continue
    return last[0], last[1], base


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

    try:
        im = imap_connect(IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_APP_PASSWORD)
        folders = list_folders(im)
        if IMAP_SENT_FOLDER not in folders:
            log_event(f"WARN Sent folder not found. Available folders: {folders[:15]} ...")
        im.logout()
    except Exception as e:
        log_event(f"IMAP folder list failed: {e}")

    while True:
        try:
            log_event("Ingest poll start")
            im = imap_connect(IMAP_HOST, IMAP_PORT, IMAP_USER, IMAP_APP_PASSWORD)
            typ, _, used = imap_select_folder(im, IMAP_SENT_FOLDER, readonly=True)
            if typ != "OK":
                raise RuntimeError(f"Folder select failed: {IMAP_SENT_FOLDER}")

            typ, data = im.uid("search", None, "ALL")
            if typ != "OK":
                raise RuntimeError("IMAP search failed")

            uids = [int(x) for x in data[0].split()] if data and data[0] else []

            with db() as conn:
                cur = conn.execute("SELECT COALESCE(MAX(imap_uid), 0) AS m FROM emails")
                last_uid = int(cur.fetchone()["m"])
                backfill_done = conn.execute(
                    "SELECT value FROM meta WHERE key='backfill_done'"
                ).fetchone()
                do_backfill = BACKFILL_ALL and (backfill_done is None)
                new_uids = uids if do_backfill else [u for u in uids if u > last_uid]

            mode = "backfill" if do_backfill else "incremental"
            log_event(
                f"Selected folder: {used} | UIDs total: {len(uids)} | New: {len(new_uids)} | Mode: {mode}"
            )

            for uid in sorted(new_uids):
                typ, msgdata = im.uid("fetch", str(uid), "(RFC822)")
                if typ != "OK" or not msgdata or not msgdata[0]:
                    continue

                raw = msgdata[0][1]
                msg = email.message_from_bytes(raw)

                msg_id = safe_decode(msg.get("Message-ID", "")).strip()
                if not msg_id:
                    msg_id = f"uid-{uid}-{hashlib.md5(raw).hexdigest()}"

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
                    with db() as conn:
                        upsert_email(conn, msg_id, uid, sent_at, to_addr, subject)
                        conn.commit()
                    log_event(f"UID {uid}: no PDF attachments")
                    continue

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

                        try:
                            content = extract_text(pdf_path, txt_path)
                        except Exception:
                            txt_path.write_text("", encoding="utf-8")
                            content = ""

                        doc_id = insert_doc(conn, msg_id, fname, pdf_path, txt_path, sha)
                        fts_blob = f"{to_addr}\n{subject}\n{sent_at}\n{content}"
                        upsert_fts(conn, doc_id, fts_blob)
                        log_event(f"UID {uid}: indexed PDF {fname} as doc {doc_id}")

                    conn.commit()

            im.logout()

            if do_backfill:
                with db() as conn:
                    conn.execute(
                        "INSERT OR REPLACE INTO meta (key, value) VALUES ('backfill_done', ?)",
                        (datetime.utcnow().isoformat(),),
                    )
                    conn.commit()
                log_event("Backfill complete; switching to incremental mode")
        except Exception as e:
            log_event(f"Ingest error: {e}")

        time.sleep(POLL_SECONDS)


def sanitize_id(s: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._-]+", "_", s)[:180]


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    with db() as conn:
        total = conn.execute("SELECT COUNT(*) AS c FROM docs").fetchone()["c"]
        rows = conn.execute(
            """
            SELECT d.id AS doc_id, e.sent_at, e.to_addr, e.subject
            FROM docs d
            JOIN emails e ON e.id = d.email_id
            ORDER BY d.id DESC LIMIT 200
            """
        ).fetchall()
        results = [dict(r) for r in rows]
    html = SEARCH_TEMPLATE_HTML
    html = html.replace("{{ total_docs }}", str(total))
    html = html.replace("{{ q }}", "")
    html = html.replace("{{ date_from }}", "")
    html = html.replace("{{ date_to }}", "")
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
    html = re.sub(r"{% for r in results %}.*?{% endfor %}", table_rows, html, flags=re.S)
    html = html.replace("{% if results is not none %}", "")
    html = html.replace("{% endif %}", "")
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

        where = []
        params = []
        if q.strip():
            where.append("docs_fts MATCH ?")
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

    html = SEARCH_TEMPLATE_HTML
    html = html.replace("{{ total_docs }}", str(total))
    html = html.replace("{{ q }}", (q or ""))
    html = html.replace("{{ date_from }}", (date_from or ""))
    html = html.replace("{{ date_to }}", (date_to or ""))

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


@app.get("/imap-test", response_class=HTMLResponse)
def imap_test_form():
    html = IMAP_TEST_HTML
    html = html.replace("{{ host }}", IMAP_HOST)
    html = html.replace("{{ port }}", str(IMAP_PORT))
    html = html.replace("{{ folder }}", IMAP_SENT_FOLDER)
    html = html.replace("{{ user }}", IMAP_USER)
    html = html.replace("{% if output %}", "")
    html = html.replace("{% endif %}", "")
    html = re.sub(r"<pre>.*?</pre>", "", html, flags=re.S)
    return HTMLResponse(html)


@app.post("/imap-test", response_class=HTMLResponse)
def imap_test_action(
    host: str = Form("imap.gmail.com"),
    port: str = Form("993"),
    user: str = Form(""),
    password: str = Form(""),
    folder: str = Form("[Gmail]/Sent Mail"),
    action: str = Form("test"),
):
    output_lines = []
    try:
        port_num = int(port)
    except ValueError:
        port_num = 993

    try:
        im = imap_connect(host, port_num, user, password)
        output_lines.append("Login: OK")
        folders = list_folders(im)
        output_lines.append(f"Folders (first 20): {folders[:20]}")

        if action == "fetch":
            typ, _, used = imap_select_folder(im, folder, readonly=True)
            if typ != "OK":
                raise RuntimeError(f"Folder select failed: {folder}")
            output_lines.append(f"Selected folder: {used}")

            typ, data = im.uid("search", None, "ALL")
            if typ != "OK":
                raise RuntimeError("IMAP search failed")

            uids = [int(x) for x in data[0].split()] if data and data[0] else []
            sample_uids = sorted(uids)[-2:]
            output_lines.append(f"Sample UIDs: {sample_uids}")

            samples = []
            for uid in sample_uids:
                typ, msgdata = im.uid("fetch", str(uid), "(BODY.PEEK[HEADER])")
                if typ != "OK" or not msgdata or not msgdata[0]:
                    continue
                raw = msgdata[0][1]
                msg = email.message_from_bytes(raw)
                samples.append({
                    "uid": uid,
                    "date": safe_decode(msg.get("Date", "")),
                    "to": safe_decode(msg.get("To", "")),
                    "subject": safe_decode(msg.get("Subject", "")),
                })

            if samples:
                for s in samples:
                    output_lines.append(
                        f"UID {s['uid']} | {s['date']} | To: {s['to']} | Subject: {s['subject']}"
                    )
            else:
                output_lines.append("No sample emails found in folder.")

        im.logout()
    except Exception as e:
        output_lines.append(f"Error: {e}")

    html = IMAP_TEST_HTML
    html = html.replace("{{ host }}", escape(host))
    html = html.replace("{{ port }}", escape(str(port_num)))
    html = html.replace("{{ folder }}", escape(folder))
    html = html.replace("{{ user }}", escape(user))
    safe_output = "\n".join(escape(line) for line in output_lines)
    html = html.replace("{{ output }}", safe_output)
    html = html.replace("{% if output %}", "")
    html = html.replace("{% endif %}", "")
    return HTMLResponse(html)


def start_bg():
    t = threading.Thread(target=ingest_loop, daemon=True)
    t.start()


if __name__ == "__main__":
    init_db()
    start_bg()
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
