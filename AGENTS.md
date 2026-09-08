# AGENTS.md

Guidance for coding agents (Claude Code, opencode, etc.) working in this repository.

## Stack

- **Backend**: FastAPI + uvicorn, Python venv at `.venv/`. Entry: `server/api/main.py` (serves the built SPA from `web/dist`).
- **Frontend**: React + TypeScript (Vite) in `web/`.
- **Bench**: `scripts/bench.py` — LLM regression suite that calls the real provider (OpenRouter).

## Commands (use exactly these)

```bash
# Backend tests — NEVER bare `pytest`: system python lacks the deps
.venv/bin/python -m pytest            # full suite ~10 min
.venv/bin/python -m pytest tests/integration/chat/test_hardening.py -q   # focused first

# Frontend
cd web && npm test                    # vitest
cd web && npm run build               # REQUIRED after any frontend commit (FastAPI serves web/dist)

# Bench (LLM regression)
set -a && source .env && set +a       # OPENAI_API_KEY + OPENAI_BASE_URL come from repo .env
.venv/bin/python scripts/bench.py --limit 11   # default --limit is 10 and silently skips Q11

# Server (local run)
set -a && source .env && set +a       # the server does NOT load .env itself
.venv/bin/uvicorn server.api.main:app --port 8000
```

**Gotchas**
- The LLM provider key lives in `.env` at the repo root — NOT in `~/.datara/datara.db` (that SQLite DB holds app data: users, sessions, messages, files, profiles).
- On WSL, starting uvicorn from `/mnt/c` takes ~10-15s (imports are slow); a curl right after launch may return 000 — wait and retry.
- Graceful uvicorn shutdown hangs on browser keep-alive connections; `kill -9` when needed.
- Never pipe pytest through other commands (`pytest | tail && commit` masks the exit code).

## Conventions

- Conventional commits (`feat:`, `fix:`, `test:`, `chore:`), message in English, **no** AI attribution or `Co-Authored-By`.
- Identifiers/comments in English; user-facing chat copy in natural professional Spanish; docs/specs in English.
- Full test suite must stay green before pushing: backend ~357, web ~88.

## Architecture rules (earned, do not break)

- **Persist-then-emit**: in the chat SSE flow, anything emitted after `create_message` but not persisted is discarded — the frontend clears streaming text and refetches messages from the DB on `done`. Persist first, then emit.
- **One system prompt per LLM call**: formatting rules (plain text, ≤6 decimals, thousands separators) do NOT propagate between calls. Each call's prompt carries its own.
- **Sandbox table capture**: every variable named `df*` / `*_df` (except plain `df`) is captured as a table artifact (head 20). Name only the final result table `df_<name>`; intermediate frames must use other names.
- **Narrative grounding**: the post-sandbox second pass receives the exact table values as context (stdout prints large floats in scientific notation and silently loses precision).
- **Fenced JSON**: models intermittently wrap `json_schema` payloads in markdown fences; the provider parser strips them (`_strip_json_fences` in `server/services/llm_openai.py`).
