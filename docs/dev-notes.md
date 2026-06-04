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

### Slice 1 — Schema & reference data
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/2. Full SQLite schema +
  `books`/`book_aliases` seeded by parsing `canonical-books.md`. Pure `bible-core`;
  `bible-api` byte-for-byte unchanged. 66 books, 264 aliases, 107 tests green.
- **Q1 — `canonical-books.md` → package data + drift-guard.** Vendored at
  `bible-core/src/bible_core/data/canonical-books.md`, read via `importlib.resources`,
  so `bible-core` is self-contained in-process. `docs/canonical-books.md` stays the
  human source of truth; `test_canonical_books_in_sync` asserts byte-identity. Verified
  the `.md` ships in the wheel with `uv build` (hatchling includes package non-`.py`
  files by default — no extra config needed).
- **Q2 — `chapter_count` → NULL** (distinguishes "not computed" from "0"; Slice 2 fills it).
- **Q3 — foreign keys → ON**, set per-connection inside `create_schema()`.
- **Q4 — normalize → standalone `bible_core/normalize.py`** (shared with Slice 3 parser).
- **Q5 — seed → single atomic transaction**; validate fully first, so a malformed file
  writes nothing.
- **Normalizer step-order subtlety (gotcha):** the contract lists "remove whitespace"
  before "leading ordinal → digit", but a faithful impl must fold the ordinal as a
  standalone *leading token* before collapsing whitespace — otherwise `Isaiah` → `isaiah`
  becomes indistinguishable from a real leading `i` and would mangle to `1saiah`. Order
  used: lowercase → strip `.`/`'` → ordinal-token-map → remove whitespace. Output matches
  every contract example. Not a change to the file — implementation detail only.
- **`canonical-books.md` needed no edits** — it passed all seed validations as-is
  (66 books, 1–66 order, 3-char USFM, no alias collisions, name/code round-trips,
  every alias already normalized). Nothing to flag for Kris.
- **Dropped planned `db.py` (YAGNI):** `create_schema()` already enables FK on its
  connection, all Slice 1 needs. A `connect()` helper (FK-on + row factory) belongs in
  **Slice 2**, where connections to an existing `bible.db` are opened and it's actually
  used/tested. ← reminder for Slice 2.
- **Pyright strict:** no `sqlite3` row-factory friction after all — the stdlib stubs
  type cursor results as `Any` (a known type), so strict stayed clean with 0 ignores in
  the new code. (Slice 0 had anticipated friction here.)
- **FTS5 check brought forward:** `create_schema` creating `verses_fts` is the SPEC §8
  "FTS5 compiled in" check; a missing build raises an unmistakable `RuntimeError`.
  Confirmed available locally.

### Slice 2 — Loader
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/3. Reproducible,
  idempotent JSON→SQLite loader (library + CLI). Pure `bible-core`; `bible-api`
  unchanged; `cross_references` still empty. 123 tests + 1 integration green.
- **Input contract as implemented (reference for future slices + soap-journal).**
  All 17 files share one shape. top: `code`, `name`, `language`, `copyright`, `books`(66).
  book: `abbreviation`, `name`, `order_index`, `chapters`. chapter: `number`, `verses`,
  `headings`, `footnotes`. verse: `number`, `text`, `is_red_letter`. Map → `translations`
  (`code`→`id`, `copyright`→`attribution`, `direction`="ltr", `versification`="standard")
  and `verses` (resolved `book_id`, `chapter`, `verse`, trimmed `text`). Ignored:
  `headings`, `footnotes`, `is_red_letter`. Books resolve via `normalize(abbreviation)`
  → `book_aliases`, asserted equal to `order_index`→`canonical_order`.
- **Q1 input contract** — above. **Q2 `bible.db`** → repo-root default, CLI `--output`;
  library takes an explicit path (tests use `tmp_path`). **Q3 CLI** → single
  `python -m bible_core.loader` build command + `make build-db`. **Q4 load pragmas**
  (loader connection only) `journal_mode=MEMORY`/`synchronous=OFF`/`temp_store=MEMORY`,
  one transaction; per-connection so output bytes unaffected. **Q5 text** → trim only;
  Unicode/brackets/spacing sacred.
- **`db.connect()` delivered** (the Slice 1 carry-over) + `apply_load_pragmas()`.
- **JSON quirks / data facts:** 529,146 verses, **zero** data-quality issues; **zero**
  cross-translation chapter-count disagreements (agreement check passes cleanly). **JPS**
  carries Hebrew/Masoretic *verse* splitting (higher verse count) but identical chapter
  counts — tagged `"standard"` for v1, cross-scheme mapping still deferred (SPEC §3).
  **Matt 17:21 present in all 13 PD** (so Slice 4's missing-verse `null` path won't fire
  on it from this corpus). `code` (e.g. ESV), not filename, is the translation id.
- **Idempotency holds out of the box:** two builds → identical sha256; no `VACUUM`/fixed
  page_size needed. **Timing:** 17 local files (incl. private) ≈ 5s; 13 PD ≈ 3.8s.
- **Pyright strict gotcha:** narrowing a `json.loads` `Any` via `isinstance(x, dict/list)`
  yields `dict[Unknown]`/`list[Unknown]`, which trips `reportUnknownVariableType` even
  under an `Any` return. Fixed with a `cast("dict[str, Any]", …)` / `cast("list[Any]", …)`
  in the two extraction helpers. Added `extraPaths` to `[tool.pyright]` so tests resolve
  the sibling `loaderkit` helper (matches pytest prepend import mode).
- **Bundled `docs(spec)` normalize step-order fix** — rewrote the contract to match the
  implemented algorithm; updated the vendored copy in lockstep to keep the drift guard green.
