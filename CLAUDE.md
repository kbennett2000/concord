# CLAUDE.md

Always-on rules for this repo. Tight by design — read every session.

**Source of truth for design is `docs/SPEC.md`. Read it before planning any slice.**
This file is the rules summary; the spec carries the full reasoning. Work proceeds one
slice at a time per the build plan in SPEC §10 — smallest reviewable unit.

## Project overview

Concord is a self-hosted, LAN-first, **read-only** Scripture API serving multiple
public-domain Bible translations from one canonical source, for self-hosters and
developers building Scripture-aware tools (church LAN platform, projection tool, future
semantic search). The hard logic lives in `bible-core` (standalone, **no web
dependencies**); `bible-api` is a thin FastAPI wrapper. It must run 100% offline after
install.

## Tech stack

- Python 3.11+
- FastAPI + Uvicorn — HTTP layer (`bible-api` only)
- Pydantic v2 — response models, OpenAPI generation
- SQLite via stdlib `sqlite3`; FTS5 for search
- pytest — tests
- Ruff — lint + format
- Docker + docker-compose — deploy
- ONNX Runtime + `tokenizers` + `numpy` — local embeddings (`bible-semantic` only; v2)
- Three packages: `bible-core` (pure) ← `bible-semantic` (ML, v2) ← `bible-api` (web),
  wired by local path dependencies

## Architecture

- `bible-core/` (import `bible_core`) — **zero web deps**. Holds: `schema` (DDL),
  `loader` (directory-scanning JSON→SQLite ETL), `parser` (pure, HTTP-free reference
  parser), `resolver` (BookResolver), `queries` (get_verses, get_chapter, search,
  cross_refs), `models` (internal dataclasses, not Pydantic).
- `bible-semantic/` (import `bible_semantic`) — **ML, web-free** (v2). Holds: `model`
  (ONNX query-embedding: tokenize → infer → CLS-pool → L2-normalize), and in later slices
  `store`/`search`/`build` for semantic search. Reads verse text through `bible-core`;
  never modifies it. Carries `onnxruntime`/`tokenizers`/`numpy` but **no** web framework
  and **no** `torch`/`transformers`/`sentence-transformers`/`optimum`.
- `bible-api/` (import `bible_api`) — FastAPI app/routers, Pydantic `schemas`, response
  `shaping` (parallel/grouped), `errors` (envelope + handlers). The only web layer; in v2
  it also depends on `bible-semantic`.
- `models/` — baked ONNX embedding weights (v2): a large build artifact, **gitignored**,
  fetched at build/test, never committed (like `bible.db`).
- `data/translations/` — committed public-domain JSON (loader input).
  `data/private/` — **gitignored**, non-distributable JSON, local only.
  `data/cross-references/` — cross-ref dataset. `data/SOURCES.md` — provenance.
- `docs/` — `SPEC.md` (design), `canonical-books.md` (book seed), `dev-notes.md` (log).
- `bible.db` is a build artifact, baked into the image at Docker build — **never committed**.

> **Hard invariants (the layering — keep it clean):**
> - **Never import a web framework (FastAPI, Starlette, Uvicorn, …) into `bible-core` or
>   `bible-semantic`.** Both are embeddable libraries, not services; this is what lets
>   `soap-journal` later link them in-process without dragging in a web stack. The only
>   web layer is `bible-api`.
> - **`bible-core` stays pure and tiny — no web framework and no heavy ML** (stdlib
>   `sqlite3` only), so anything can embed it cheaply. ML weight lives in `bible-semantic`.
> - Layering: `bible-core` = pure/tiny · `bible-semantic` = ML/web-free · `bible-api` = web.

## Conventions

- **Book identity:** USFM 3-letter codes (`GEN`, `1CO`, `REV`) internally, everywhere.
  Seed books/aliases from `docs/canonical-books.md` — never invent reference data.
- **Reference parser:** pure and HTTP-free; takes a `BookResolver`; tested with fixtures,
  no DB. It's the trickiest code — test exhaustively (grammar in SPEC §5).
- **Default response shape:** parallel-by-verse; `?format=grouped` available.
- **Missing verse** (omitted in a translation, e.g. Matt 17:21): `null` for that
  translation in parallel mode. Out of range in *all* requested translations → 404.
- **Error envelope:** `{ "error": { "code", "message", "detail" } }`.
  400 unparseable ref · 404 unknown book/verse/translation · 422 bad params.
- **Caching:** verses are immutable → strong ETag + long `Cache-Control`.
- **Loader:** scans data directories (no hardcoded filenames), validates input, fails
  loudly, idempotent (rebuilds from scratch). `chapter_count` is **computed from verse
  data**, never hand-entered.
- **Config via env:** port (`BIBLE_API_PORT`) and CORS allowed-origins must be
  env-configurable.
- **Offline at runtime:** no CDNs (self-host Swagger/ReDoc assets), no telemetry, no
  phone-home. Build/install may use the network; runtime may not.
- **Python style:** snake_case; absolute imports within each package; type hints on
  public functions.
- **Tests:** pytest; `bible-core` logic is tested independently of HTTP.
- **Dev notes:** append a short entry to `docs/dev-notes.md` per slice.
- **Docs deferred:** the full README is Slice 9. Until then keep only a functional
  operator README (build / run / deploy).

## Out of scope for v1

**v2 (semantic search), v3 (biblical geography), and v4 (translator's notes) are all
shipped.** v2's meaning-based retrieval landed in the `bible-semantic` package. v3 added
place data + the bi-directional place↔verse link (`places` + `place_verses` tables in
`bible.db`, owned by `bible-core`; `/v1/places*` endpoints in `bible-api`), designed in
`docs/v3/SPEC.md`. v4 added translator's/study/text-critical notes (`translator_notes` +
`note_cross_references` tables; the `/v1/translations/{translation}/notes/{book}/{chapter}`
endpoint), designed in `docs/v4/SPEC.md` — notes are **user-supplied and never shipped in
the public image**. Each milestone was **purely additive** — no schema rewrites — baked via
the existing build like v1's cross-references. **Journeys / routes is the named next
frontier.** The items below remain out of scope unless explicitly expanded.

Do not build these without an explicit decision to expand scope:

- Writes / mutations (the API is read-only).
- Auth (LAN-trusted).
- Catholic / deuterocanonical books, and any cross-scheme versification mapping. The
  schema is versification-ready; the data and mapping are deferred.
- Multi-translation search (search is single-translation).
- Semicolon-joined multi-reference strings in the parser (e.g. `John 3:16; Rom 8:1`).
- Committing non-distributable translations — they stay local-only in `data/private/`.
- Any internet dependency at runtime.
- **Journeys / routes** (Paul's missionary journeys, the Exodus path) — ordered sequences,
  competing proposed routes, segment-level links, and dating debates. **The named next
  frontier after v4**, deliberately deferred; it will *reference* v3's place data (hence
  v3's stable-id + disambiguation foundation), not rebuild it. Region grouping/containment
  and the dataset's full scholarly apparatus are deferred with it.

## Git Workflow

Each slice gets its own branch. Before starting a slice:
```
git checkout main && git pull
git checkout -b slice/N-short-name
```
All work on that branch — **never commit directly to `main`, never push to `main`.**

After any code change is complete and verified (tests pass / lint clean / typecheck
clean / feature works), do the following without being asked:

1. `git add -A` to stage all changes
2. Commit with a concise conventional-commit message, scoped to the package or area
   (e.g. `feat(core): add reference parser grammar for verse ranges`,
   `feat(api): wire /verses/{ref} to query function`,
   `test(core): cover cross-chapter range parsing`,
   `fix(loader): tolerate trailing whitespace in book aliases`,
   `docs(spec): clarify missing-verse semantics`).
   Scopes: `core`, `semantic`, `api`, `loader`, `geo`, `docs`, `data`, `infra`, `deps`. Omit
   scope only for repo-wide changes (`chore:`). (`geo` for geography-specific work; the v3
   loader landed under `core`/`data`.)
3. `git push` the slice branch

Commit at logical checkpoints — a complete sub-step, a passing suite, a refactor —
not after every individual file edit. Within a slice, each commit is independently
meaningful and atomic.

When the slice is complete, open a PR with `gh pr create`. PR title is the slice name
(e.g. `Slice 3: Reference parser`); body summarizes what landed, links the slice in
`docs/SPEC.md §10`, and lists anything appended to `docs/dev-notes.md`.
**PRs are merged by Kris after review — do not self-merge.**

If `git push` or `gh pr create` fails (auth, conflict, network), surface the full
error to the user immediately. Do not retry silently or attempt destructive
resolutions (no `--force`, no resetting branches, no rebasing shared history).

Never commit secrets, API keys, or anything matching `.gitignore`. For this repo
that explicitly includes `.env`, `bible.db` (built database — a Docker artifact),
`data/private/` (non-distributable translations — local only), and
`.claude/settings.local.json`.

## Engineering Principles

### Tests are required, not optional
- Every new feature, bug fix, or non-trivial change ships with tests.
- For new functionality, prefer test-first: write the test from the spec, then
  implement until it passes.
- A task is not "done" until the relevant tests pass. Do not report completion with
  failing or skipped tests.
- When fixing a bug, first write a test that reproduces the bug (and fails), then
  fix it. This prevents regressions.
- Keep the test suite fast. Slow tests are marked `@pytest.mark.integration`; the
  default `pytest` run uses `-m "not integration"` and stays under 10 seconds.

### Tight feedback loops
- Use strict typing everywhere — Pydantic v2 for HTTP boundary models, **pyright**
  (strict mode) for the rest. Type errors surface immediately.
- Run lint, format, and typecheck before declaring a task complete:
  `ruff check`, `ruff format --check`, `pyright`.
- Add structured logging at module boundaries from day one. Use **structlog** with
  JSON output to stdout — Docker captures stdout, no external sink, no telemetry,
  consistent with the offline-runtime rule.
- If a change requires manual verification (running the API, hitting an endpoint,
  checking `/docs`), state exactly what to check and how — don't leave it implicit.

### Spec before code for non-trivial work
- For any task touching 3+ files, introducing a new module, or changing a contract
  between components: produce a spec FIRST in plan mode. Do not start editing until
  Kris has approved the plan.
- Initial Concord design decisions live in `docs/SPEC.md` (especially §3 Decisions &
  non-goals). **New** significant architectural decisions after that get a short ADR
  in `docs/adr/` capturing context, options considered, decision, consequences.
  Reference the ADR in commit messages. Do not retroactively convert spec decisions
  into ADRs.
- Read `docs/SPEC.md` and `docs/canonical-books.md` before starting any slice. Those
  files describe intent; the code describes implementation. Both matter.

### Taste and restraint
- Prefer the simplest solution that solves the problem. Resist adding abstraction,
  config options, or framework features that aren't justified by an actual requirement.
- If a diff is getting large, stop and ask whether the task should be decomposed into
  smaller commits — or, for a slice, whether scope is creeping past what was planned.
- Reuse existing patterns in the codebase before inventing new ones.
- **Dependency discipline.** Don't add a new dependency without justification.
  Dependencies added to `bible-core` get extra scrutiny — the package must remain
  web-framework-free (see the hard invariant in Architecture). Prefer the standard
  library where it's adequate (e.g., `sqlite3` over an ORM for v1).
