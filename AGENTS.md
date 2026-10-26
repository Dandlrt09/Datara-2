# AGENTS.md

Guidance for coding agents (Claude Code, opencode, etc.) working in this repository.

## Working with the maintainer (teaching mode)

The maintainer is rebuilding Datara while learning it. Explaining is part of the
work, not an extra: an unexplained change counts as an unfinished change.

- **Explain before you edit, in plain Rioplatense Spanish** (voseo, natural prose,
  no bullet-point telegrams). What problem we are solving, why it exists, what we
  are about to touch, and what could break — then make the change.
- **Translate the jargon the first time it appears** in a session (whitelist, gate,
  probe, SSRF, lineage, receipt…): one sentence in criollo, then the technical name.
- **Teach the why.** For each design decision, say what the alternative was and why
  we did not take it. No unexplained code dumps.
- **Name the file and its job**, so the change has a place in the map of the app.
- **Flag scope growth out loud.** If the fix ends up touching more than what was
  explained, stop and explain the extra part before doing it.
- **Close with how to verify it**, in criollo: what to click in the browser and what
  should appear.
- Code, comments, commits and docs stay in English; the explanation is Spanish.

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
- **Native review / #4030**: before `gentle-ai review status ... --next-transition`, run `git worktree list --porcelain` and `git worktree prune --dry-run -v`; if anything is listed as prunable, run `git worktree prune` first. A stale registered worktree makes the OpenCode transport reject the reviewer (`opencode_review_transport_binding_invalid`, Gentle AI #4030) even when the review target is healthy.
- **Native review from an ext4 clone**: reviewing the repo in place on `/mnt/c` (9p) is unreliable — `candidate-view` times out first (`checkout-index` after 10 s) and the heavy reviewer capture (~100 KB prompts) can end in `operation_timeout`, leaving a stuck partial lineage and burning tokens for nothing. Run the review from an ext4 clone instead:

  ```bash
  git clone --no-local "/mnt/c/Users/Danieldlrt09/Proyectos/Datara 2" "$HOME/datara-review"
  ```

  `$HOME` is ext4 and `--no-local` copies every local ref, including the **unpushed** candidate commits. Then pass `workspaceRoot=/home/<user>/datara-review` on every `gentle_review` call (inspect, start, status, capture, acknowledge). In a clean clone `inspect` sees an empty working tree, so supply the committed range in the START `input`: `{"baseRef":"<base-commit>","committedOnly":true,...}`. The review is bound to the clone's repository context, so it is the review of record even though the code lives in the other checkout.

## Conventions

- Conventional commits (`feat:`, `fix:`, `test:`, `chore:`), message in English, **no** AI attribution or `Co-Authored-By`.
- Identifiers/comments in English; user-facing chat copy in natural professional Spanish; docs/specs in English.
- Full test suite must stay green before pushing: backend ~788, web ~569.

## Architecture rules (earned, do not break)

- **Persist-then-emit**: in the chat SSE flow, anything emitted after `create_message` but not persisted is discarded — the frontend clears streaming text and refetches messages from the DB on `done`. Persist first, then emit.
- **One system prompt per LLM call**: formatting rules (plain text, ≤6 decimals, thousands separators) do NOT propagate between calls. Each call's prompt carries its own.
- **Sandbox table capture**: every variable named `df*` / `*_df` (except plain `df`) is captured as a table artifact (head 20). Name only the final result table `df_<name>`; intermediate frames must use other names.
- **Narrative grounding**: the post-sandbox second pass receives the exact table values as context (stdout prints large floats in scientific notation and silently loses precision).
- **Fenced JSON**: models intermittently wrap `json_schema` payloads in markdown fences; the provider parser strips them (`_strip_json_fences` in `server/services/llm_openai.py`).
