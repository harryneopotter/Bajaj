# Repository Guidelines

## Project Structure & Module Organization

- `app/` contains the FastAPI service (`main.py`) and its dependencies (`requirements.txt`) built into the container.
- `data/` is a runtime volume for SQLite (`quotevault.db`), stored PDFs, and extracted text.
- `docker-compose.yml` and `app/Dockerfile` define the container build and runtime layout.
- `.env` holds runtime configuration (IMAP credentials, polling interval, data path).

Example layout:

```text
quote-vault/
  app/
    main.py
    requirements.txt
  data/
  docker-compose.yml
  .env
```

## Build, Test, and Development Commands

- `docker compose up --build -d`: build and start the service.
- `docker logs -f quotevault`: tail runtime logs (IMAP ingest, errors).
- `docker compose down`: stop the service and keep data volume on disk.

There are no local non-Docker run scripts in the repo; the service is expected to run in a container.

## Coding Style & Naming Conventions

- Python: 4-space indentation, PEP 8 naming, type hints where practical.
- Filenames are lowercase and descriptive (`main.py`, `requirements.txt`).
- Keep configuration in `.env`; avoid hardcoding credentials in code.

No formatter or linter is configured yet; keep changes small and readable.

## Testing Guidelines

- No automated test suite is currently defined.
- If you add tests, place them under `tests/` and mirror module names (e.g., `tests/test_ingest.py`).
- Include a short note in PRs describing manual verification (e.g., “ingest ran and search UI loads”).

## Commit & Pull Request Guidelines

- No existing commit convention is documented. Prefer Conventional Commits (e.g., `feat: add search filter`).
- PRs should include: purpose, how to run/verify, and any config changes.
- If UI changes are made, add a screenshot or brief description of the UX impact.

## Security & Configuration Tips

- Use Gmail IMAP app passwords; do not store secrets in git.
- Validate the IMAP Sent folder name via logs if ingest stalls. Common folders include `Sent Messages` or `[Gmail]/Sent Mail`.
- Keep `data/` backed up; it holds PDFs and the SQLite index.

## Agent-Specific Instructions

- Keep changes focused on Docker + FastAPI workflow.
- Update this document if structure, commands, or tooling changes.
