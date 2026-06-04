# Concord — Dev Notes

A running log of decisions, gotchas, and "why it's this way" notes, captured **as slices
land** so the final documentation pass (Slice 9) has raw material instead of
reconstructing from memory. Keep it terse — a few lines per slice is plenty.

This is for builders (you, Claude, Claude Code), not end users. User-facing prose lives
in the README.

## Conventions

- Append a dated entry per slice (or per notable decision).
- Record the *why*, not just the *what* — especially anything non-obvious, anything that
  bit us, and anything a future reader might be tempted to "fix" without context.
- Link the PR where useful.

---

## Log

### Bootstrap
- 2026-06-04 — Re-bootstrapped repo, pushed to `main` (the one allowed direct-to-`main` commit; slices use branches from here on). Initial commit `0f3046b`. Public repo: https://github.com/kbennett2000/concord. Re-bootstrapped after attribution issue; identity now set globally via GitHub noreply email.

### Slice 0 — Skeleton & boot
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/1. Two-package
  foundation (`bible-core` + `bible-api`), tooling, dev container, `/healthz` → 200.
- **Q1 — uv workspace** (not two independent projects). One shared `.venv`, one
  `uv.lock`, single root commands. `bible-api` depends on `bible-core` via
  `[tool.uv.sources] bible-core = { workspace = true }`. Root is a *virtual* project
  (`[tool.uv] package = false`).
- **Q2 — all tooling config at the repo root**, once. Per-package `pyproject.toml`
  carry only metadata + deps; Ruff and Pytest find the root config by ancestor walk,
  Pyright via an explicit `include` list of both `src/` + `tests/` trees.
- **Q3 — `/healthz`** returns `{"status":"ok","translation_count":0,"verse_count":0}`
  (typed `HealthResponse`; counts are placeholders until Slice 7).
- **Q4 — CORS default** `CONCORD_CORS_ORIGINS=*` with `allow_credentials=False` (the
  safe permissive combo; `*`+credentials is the reckless pairing we avoid).
- **Q5 — root entry point**: `uv run pytest|ruff|pyright` cover both packages; wrapped
  in a `Makefile` (`make check` runs the whole gate).
- **Boundary nuance (gotcha):** in the shared workspace venv FastAPI *is* importable
  from `bible_core` because `bible-api` pulls it in. The real guarantee is that
  `bible-core/pyproject.toml` declares zero web deps — proven two ways: an automated
  `test_no_web_deps.py` guard, and a one-time isolated install
  (`uv venv /tmp/x && uv pip install --python /tmp/x ./bible-core` →
  fastapi/starlette/uvicorn/httpx all absent). ✓ verified.
- **Pyright strict gotchas (this fastapi 0.136 / starlette 1.2 / pyright 1.1.410
  combo):** (1) `@asynccontextmanager` lifespan must annotate `-> AsyncGenerator[None]`,
  not `AsyncIterator[None]` (reportDeprecated). (2) Nested `@app.get` route handlers
  trip `reportUnusedFunction`; moved routes to a module-level `APIRouter` +
  `include_router`. (3) `TestClient.get()`'s return type isn't fully resolved — narrow
  file-level `# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false`
  in the test only.
- **Env:** local Python pinned to **3.12** (system was 3.14.4); SQLite **FTS5
  available** (matters from Slice 2). **Docker not installed on this machine** — the
  `docker compose up` path is written but unverified locally; verify on a Docker host.
- **CI deferred:** worth a future slice running `uv run ruff/pyright/pytest` on PRs.
