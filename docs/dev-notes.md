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

### Slice 3 — Reference parser
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/4. Pure reference parser
  + `BookResolver`. Pure `bible-core`; `bible-api` unchanged; no new deps. 202 default +
  2 integration tests green.
- **Edge-case policy table (preserved for Slice 4's HTTP error mapping):**

  | Input | Outcome |
  |---|---|
  | `John 3:16` | verse `Span(3,16,3,16)` |
  | `John 3:16-18` | verse range `Span(3,16,3,18)` |
  | `John 3:16,18,20` | verse list → point-spans (sorted, deduped) |
  | `John 3` | whole chapter `Span(3,None,3,None)` |
  | `John 3-4` | chapter range `Span(3,None,4,None)` |
  | `John 3:16-4:2` | cross-chapter range `Span(3,16,4,2)` |
  | `3.16` ≡ `3:16` | `.` normalized to `:` |
  | `1 John`/`1John`/`1 Jn`/`I John`/`First John` | all → `1JN`, echo `1 John …` |
  | `Jn.` / `1 Jn.` | trailing punctuation stripped, accepted |
  | en/em dash `–`/`—` | normalized to ASCII `-` |
  | `John 1:99999999` | parses (no bounds check) |
  | `3-3`, `3:16-3:16`, `3:16-3:18` | collapse to simpler form |
  | `3:18-16`, `5-3` | reject "descending … range" |
  | `3-4:2` | reject "ambiguous range" |
  | `3:16-4` | reject "descending verse range" (16→4) |
  | `3:16,4:2` | reject "bare verse numbers" (no cross-chapter lists) |
  | `3:16-18,20` | reject "expected a verse number" (no ranges-in-lists) |
  | `John` | reject "needs at least a chapter" |
  | `3:16` | reject "no book name found" |
  | `` / whitespace | reject "empty reference" |
  | `0:5`, `3:0` | reject "must be positive" |
  | `-3:16` | reject "missing a bound" |
  | `3:16,,18` | reject "empty list element" |
  | `3:16--18` | reject "malformed range" |
  | `3:16!` | reject "unexpected character" |
  | `Hezekiah 1:1` | reject "unrecognised book" |
  | `John 3:16; Rom 8:1` | reject "multiple references" (semicolons out of scope) |
  | `3:16-18.20` | accept as cross-chapter range (`.`≡`:`) |

- **Q1 result shape → normalized `Span` list** (`start_chapter, start_verse|None,
  end_chapter, end_verse|None`); one type covers all forms, query-friendly for Slice 4
  (verse-None ⇒ chapter selection). **Ranges are never expanded** — so `John 1:1-99999999`
  is one cheap Span. **Q2 echo → no compression** (Kris's call): lists stay lists, ranges
  stay ranges (sorted/deduped, same-bound collapses); this is what makes the round-trip
  exact without unsafe range expansion. **Q3 → `resolve(token)->BookInfo|None`** (id +
  name in one call; resolver owns `normalize()`). **Q4** policy table above. **Q5 →
  hand-rolled.**
- **Split trick:** the chapter/verse spec is always numeric+separators (no letters), so
  the book name ends at the **last ASCII letter**; everything after (minus leading
  `.`/`'`/space) is the spec. This sidesteps the "is `1` an ordinal or a chapter?" problem
  for `1 John 3:16` and handles `Song of Solomon 1:1` and `Jn. 3:16` uniformly.
- **A couple of cases resolve by consistent rule, not special-case:** `John 3:16-4`
  rejects as a *descending* range (16→4), and `John 3:16-18.20` parses as a cross-chapter
  range because `.`≡`:`. Both intentional; both tested.
- **Pyright clean, no friction** (sqlite rows are `Any`, no `cast` needed in the resolver).
  Reused Slice 2's `extraPaths` so tests import the sibling `parserkit` resolver fixture.
- **For Slice 4 future-you:** the parser does **not** bounds-check chapters/verses — the
  HTTP layer owns the SPEC §5 "404 when nothing exists" outcome. The Matt 17:21
  missing-verse `null` path isn't in the production corpus (Slice 2 found it present in all
  13 PD), so Slice 4 will need **synthetic fixtures** to exercise that path. Slice 4 maps
  each `Span` → one SQL `WHERE`: chapter-mode (`chapter BETWEEN …`) when verses are None,
  else a linear `(chapter, verse)` range; a verse list is N point-spans.

### Slice 4 — Core read endpoints
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/5. The combined slice:
  query functions + `/v1/verses/{ref}` + `/v1/chapters/{book}/{chapter}` (parallel +
  grouped) + the shared shaper + error envelope + ETag/caching, and `/healthz` wired to
  real counts. 246 default + 2 integration tests green. Smoke-tested against the real
  17-translation `bible.db` (529,146 verses).
- **Q1 query result → flat `VerseRow` rows** in a `QueryResult` (feeds both shapers). **Q2
  DB → per-request read-only conn** (`connect_readonly`, `file:…?mode=ro`); startup opens
  one conn, verifies schema, caches `{translations, default_translation, counts}` on
  `app.state`, closes it. **Q3 translations case-insensitive** (upper at boundary). **Q4
  ETag = body-hashed sha256** (quoted, 32 hex), 304 on If-None-Match. **Q5 unknown
  translation → 404** (SPEC §7 404 family: unknown_book/unknown_translation/
  no_verses_found; unparseable grammar → 400). **Q6 default KJV**, validated at startup,
  **fail fast** if not loaded. **Q7 `/chapters` echo = `"<name> <chapter>"`** (`John 3`).
- **`UnknownBookError(ParseError)` added to `bible-core/parser.py`** so the HTTP layer can
  split unknown-book (404) from unparseable grammar (400). Subclass ⇒ Slice 3 tests
  (`except ParseError`) unaffected. Starlette dispatches to the most specific handler in
  the exception MRO, so registering both handlers works regardless of order.
- **Span→SQL:** chapter-mode `chapter BETWEEN`, same-chapter `verse BETWEEN`, cross-chapter
  a linear `(chapter,verse)` predicate. Ranges never materialized (`John 1:1-99999999`
  stays one cheap query — tested).
- **Synthetic missing-verse fixture pattern (reusable by Slices 5/6):** build a small DB
  with `create_schema` + `seed_books` + direct verse inserts where one translation omits a
  verse (`apikit.build_corpus`: WEB omits John 3:16). Parallel → `"WEB": null`; grouped →
  WEB's list omits it; only-WEB request for that verse → 404. The production corpus has
  Matt 17:21 everywhere, so this is the only way to exercise the null path.
- **ETag = body hash, not input hash:** correct by construction (different bytes ⇒
  different ETag) and immune to input-normalization subtleties. Costs one query before the
  304, which is negligible for an immutable LAN read API; chosen over input-keying which
  would have to capture translation order, default resolution, and format exactly.
- **Underspecified SPEC points decided:** grouped includes every requested translation as
  a key (empty list if none); parallel `translations` + `text` keys are the requested set
  in requested order (deduped); a verse present in *no* requested translation just doesn't
  appear (404 only when the whole reference is empty).
- **Strict-typing / framework snags:** FastAPI `Depends`/`Path` in parameter defaults trip
  ruff **B008** → use `Annotated[T, Depends(...)]` / `Annotated[int, Path(ge=1)]`. TestClient
  JSON (`.json()`) is untyped in this stack → API test files carry a narrow
  `# pyright: reportUnknownMemberType/VariableType/ArgumentType=false`; typed JSON helpers
  need explicit `dict[str, Any]` (bare `dict` trips `reportMissingTypeArgument`).
- **DB-required-at-startup ripple:** the app now refuses to boot without `bible.db`, so the
  dev Dockerfile bakes it (`COPY data/` + `RUN … loader`) to keep `docker compose up`
  working. `create_app(db_path=…)` lets tests point at a temp DB. The Slice 0 healthz test
  was rewritten (zeros → real counts). **Docker unverified locally (no Docker on this
  box).**
- **For Slice 5 (search) future-you:** the shaper/error-envelope/ETag/Cache-Control
  patterns are reusable; search responses follow the same envelope + caching conventions.
  The per-request `get_conn` dependency and `resolve_translations` (note: search uses a
  single `?translation=`, not the CSV set) are the wiring to copy.

### Slice 5 — Search endpoint
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/6. `GET /v1/search` over
  FTS5, single-translation, optional book filter + pagination, `<mark>` snippets. Pure
  reuse of Slice 4 (only two new error handlers added). `bible-core` change confined to
  `queries.py`; no web imports. 280 default + 3 integration tests green. Smoke-tested
  against the real `bible.db`.
- **Q1 module → `bible_core.queries.search_verses`.** **Q2 aux fn → `snippet()`**
  (32-token window, `…`): short verses show fully, long ones window; `highlight()` would
  dump the whole verse. **Q3 response** `{query, translation, book, limit, offset, total,
  hits[{book, chapter, verse, reference, snippet}]}`. **Q4 pagination** `limit` default
  20 / max 100, `offset` default 0; out-of-range → 422. **Q5 FTS5 → passthrough.** **Q6
  ETag → reuse `cached_json_response`** (body hash captures full query state). **Q7
  markers → `<mark>…</mark>`** (constant, not env-configurable).
- **Exposed FTS5 syntax (→ Slice 9 user docs):** terms = implicit AND (`god world`);
  phrase `"in the beginning"`; prefix `lov*`; boolean `OR`/`NOT`/`AND`, parentheses;
  `NEAR(...)`. Malformed (unbalanced quote, bare `*`) → `sqlite3.OperationalError` →
  caught → **400 `invalid_search_query`** with the FTS5 message in
  `error.detail.fts5_error`.
- **Book-filter status (the cross-slice wrinkle):** unknown `?book=` filter → **400
  `unknown_book`** (Kris's call) — a query-param bad request, deliberately distinct from
  `/verses` where the book is a path resource (**404** `unknown_book`). Same code, two
  statuses, by design. `BookFilterError` (bible-api) carries the 400; Slice 4's
  `UnknownBookError` still carries the 404.
- **Pagination is non-overlapping by construction:** `ORDER BY f.rank, b.canonical_order,
  v.chapter, v.verse` — relevance first, with a total-order canonical tiebreak so
  successive `limit`/`offset` pages never repeat a row. `total` is a separate `COUNT(*)`
  (independent of limit/offset). Empty results = **200** with `total:0`, never 404.
- **FTS5 quirks:** `snippet(verses_fts, 0, open, close, '…', tokens)` — markers/token-count
  are SQL literals (trusted constants, not params), so they're string-interpolated into the
  SQL while `q`/translation/book stay parameterized. `unicode61` (default) tokenizer
  lowercases, so queries are case-insensitive and punctuation/brackets (`[is]`) are split
  out but preserved in the stored text shown in snippets. Real-DB search of common phrases
  is instant (sub-ms) on the 529k-verse index. `text:foo` (column syntax) is harmless —
  one column.
- **For Slice 6 (cross-references) future-you:** the envelope + `cached_json_response` +
  resolver-based `?book=`/ref handling apply identically. Cross-refs will parse a single
  `{ref}` via the Slice 3 parser (like `/verses`) and may hydrate target text via a
  single `?translation=` (reuse `resolve_translation`). `min_votes`/`limit` are plain
  validated query params (422 on bad values, as here).

### Slice 6 — Cross-references
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/7. Dataset load +
  `GET /v1/cross-references/{ref}` + `cross_ref_count` in healthz. Pure reuse of Slice 4/5
  (only new cross-ref handlers/route + a `by_alias=True` no-op on the shared caching
  helper). 310 default + 4 integration tests green. Full build (translations + 344,799
  cross-refs) byte-identical across runs (~6.4s).
- **Implemented input contract** (reference for future readers / soap-journal): OpenBible.info
  TSV `cross_references.txt`, **CC-BY**, 344,799 rows. Columns `From Verse` · `To Verse` ·
  `Votes`; header line's 4th field is the attribution. Verse format `Book.Chapter.Verse`
  (`1Cor.8.6`); book token = text before the first `.`, resolved via `normalize()` →
  `book_aliases` (all 66 openbible abbreviations resolve). **From** always a single verse;
  **To** single or `A-B` range (full ref both sides). Votes integer.
- **Attribution (verbatim — for Slice 9 README):** *Cross-reference data courtesy of
  OpenBible.info (https://www.openbible.info/labs/cross-references/), licensed under a
  Creative Commons Attribution (CC BY) license.* Recorded in `data/SOURCES.md`; the 8.3 MB
  file is committed (CC-BY redistributable; `data/cross-references/` not gitignored).
- **Q1 contract** above. **Q2** queries in `bible_core.queries`. **Q3 response** — sketch,
  but `translation`/`text` **always present** (null when `include_text=false`; under a
  non-null `translation`, null `text` = target missing in that translation); `from` is a
  Pydantic `serialization_alias` (Python keyword) → `cached_json_response` now serializes
  `by_alias=True` (no-op for alias-free models). **Q4 pagination** = N total across the
  range (votes desc + canonical tiebreak). **Q5 `min_votes` default 0** (ge=0). **Q6 404
  bounds-check** via shared `_span_predicate` + `reference_exists` → `NoVersesFoundError`.
  **Q7 `include_text`** hydrates the **target start verse** only.
- **Dataset quirks:** **655 To-ranges (0.19%)** cross a chapter (637) or book (18) — the
  schema's single `to_chapter` can't hold them, so they're **clamped to the start verse**
  (`to_verse_end = NULL`), cross-ref preserved, loader logs the count. `to_verse_end`
  convention: NULL for single-verse *and* clamped targets; the end verse only for genuine
  same-book/same-chapter ranges. **3,512 rows have votes ≤ 0** (downvoted/disputed) —
  stored but never surfaced (`min_votes` constrained ≥0). `1 John 4:9-10` (a range target,
  votes 684) is the visible proof the range rendering + clamping logic both work.
- **Refactor:** `_span_predicate(span, chapter_col, verse_col)` extracted from `_query_span`
  and reused by cross-ref queries (`from_chapter`/`from_verse`) and `reference_exists`
  (`chapter`/`verse`, no translation filter) — one definition of the
  chapter/same-chapter/cross-chapter range logic.
- **For Slice 7 (utility endpoints) future-you:** the patterns are fully locked in —
  `/random`, `/books`, `/translations` should be small and almost mechanical. `/books`
  and `/translations` are plain `SELECT … ORDER BY canonical_order` / metadata reads
  shaped into Pydantic models + `cached_json_response`; `/random` picks a random verse
  (optionally constrained by `?book=`/`?testament=`) in `?translation=` — and is the one
  response that is **not** cacheable, so it should send `Cache-Control: no-store` rather
  than the immutable ETag treatment (the only place to deviate from the caching pattern).

### Slice 7 — Utility endpoints
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/8. `/v1/books`,
  `/v1/translations`, `/v1/random`, and `book_count` on `/healthz`. **The v1 read surface
  is now complete.** Pure reuse of Slice 4–6 (3 routes, 3 query fns, 1 caching helper, 1
  error code). 330 default + 5 integration tests green. `bible-core` change confined to
  `queries.py`; no web imports.
- **Q1 shape → wrapped** (`{"books":[...]}`, `{"translations":[...]}`). **Q2 `/translations`
  ordered by `id`** (`/books` by `canonical_order`). **Q3 `/random`** =
  `{translation, book, testament, verse{book,chapter,verse,reference,text}}` (echoes the
  resolved/normalized filters). **Q4 contradicting/empty filters → 404 `no_match`** (new
  `NoMatchError` handler; filters individually valid, intersection empty → not-found, not
  422). **Q5 `/healthz` adds `book_count`**. **Q6** translations case-insensitive via
  `resolve_translation`; `?testament=` via `Query(pattern="(?i)^(ot|nt)$")` → free 422 on
  bad values (verified); `?book=` via `SqliteBookResolver`.
- **The one design point — `/random` is NOT cached:** new `no_store_json_response`
  (`Cache-Control: no-store`, **no ETag**, no If-None-Match). Reusing the immutable-ETag
  pattern would let clients replay one "random" verse. Tested as a negative-presence
  assertion + non-determinism (≥2 distinct over 20 calls). Every other endpoint keeps the
  immutable cache unchanged.
- **Final `/healthz` shape (for Slice 9 user docs):**
  `{"status":"ok","translation_count":N,"verse_count":N,"cross_ref_count":N,"book_count":66}`.
- **`/random` query:** `… FROM verses v JOIN books b ON b.id=v.book_id WHERE
  v.translation_id=? [AND v.book_id=?] [AND b.testament=?] ORDER BY RANDOM() LIMIT 1` —
  `ORDER BY RANDOM()` scans the matching rows (~31k for one translation), sub-10ms; fine
  at this scale (no need for a rowid-sampling scheme).
- **Test-infra note:** `apikit.build_corpus` now computes `chapter_count` for populated
  books (`COUNT(DISTINCT chapter)`, mirroring the loader) so `/books` returns real values
  in unit tests; the real `chapter_count == MAX(chapter)` cross-check (GEN=50, PSA=150)
  runs in the integration test.
- **For Slice 8 (Docker & deploy) future-you:** the v1 read surface is **complete** — Slice
  8 is hardening, not new features. Preserve and verify, don't reinvent: multi-stage build
  baking `bible.db` at build time (the loader already does this; the dev Dockerfile from
  Slice 4 bakes it — make it a clean multi-stage prod image), a compose **healthcheck**
  hitting `/healthz`, **self-hosted Swagger/ReDoc assets** so `/docs` + `/redoc` work fully
  offline (FastAPI's default CDN-hosted assets render blank air-gapped — SPEC §3 gotcha),
  and the already-working env config (`BIBLE_API_PORT`, `CONCORD_CORS_ORIGINS`,
  `BIBLE_DB_PATH`, `CONCORD_DEFAULT_TRANSLATION`).
- **For Slice 9 (Documentation) future-you:** every endpoint now exists (`/verses`,
  `/chapters`, `/search`, `/cross-references`, `/random`, `/books`, `/translations`,
  `/healthz`) — walk them in a sensible order. The **OpenBible.info CC-BY attribution line**
  (Slice 6 / `data/SOURCES.md`) **must appear in the README**.

### Slice 8 — Docker & deploy
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/9. Deployment hardening,
  no feature changes. `bible-core` untouched. 337 default + 5 integration tests green.
  **Docker build + offline `/docs` verified by Kris on a Docker host** (I have no Docker
  on this machine).
- **Q1 one multi-stage Dockerfile** (replaced the dev single-stage). **Q2 runtime
  `python:3.12-slim`** (same base both stages so the venv interpreter symlinks resolve).
  **Q3 vendor + commit** the docs assets. **Q4 single hardened compose.** **Q5 512M
  memory rail** (tunable), no CPU limit. **Q6 healthcheck** 30s/3s/3/10s.
- **The offline `/docs` fix (load-bearing):** FastAPI 0.136.3 defaults reach jsdelivr
  (swagger bundle+css), `fastapi.tiangolo.com` (favicon), and — easy to miss —
  `fonts.googleapis.com` (ReDoc, `with_google_fonts=True`). Fix: `FastAPI(docs_url=None,
  redoc_url=None)`, mount vendored assets at `/static`, and module-level `/docs` +
  `/docs/oauth2-redirect` + `/redoc` routes via `get_swagger_ui_html`/`get_redoc_html`
  with local URLs and **`with_google_fonts=False`**. A default-suite test
  (`test_docs_offline.py`) asserts no CDN URLs + assets served — always-on guard against a
  FastAPI upgrade flipping the defaults back.
- **Pinned vendored versions (upgrades are deliberate):** swagger-ui-dist **5.32.6**
  (Apache-2.0), redoc **2.5.3** (MIT) — in `bible-api/src/bible_api/static/` (+ a
  `static/README.md`). They ship in the `bible_api` wheel (verified `uv build`), so
  `/docs` works offline under Docker *and* local `uv run`.
- **Runtime self-containment:** builder uses `uv sync --no-editable` so package code +
  static assets land in `.venv`; runtime copies only `.venv` + the baked `bible.db` (no
  source, data, loader, or build tools). `HEALTHCHECK` uses stdlib `urllib` (slim has no
  curl) and is healthy only when `translation_count > 0`. `bible.db` is baked, not mounted
  (reproducible per Slice 2).
- **Image size:** **528 MB** (`python:3.12-slim` + venv + the ~180 MB baked `bible.db`
  incl. 344,799 cross-refs). Loader runs in-image in ~6s; consistent across rebuilds.
- **Over-the-wire verification (done — Docker installed via snap mid-session):** build ✓;
  `docker compose up` → **healthy in ~8s**; `/healthz` shows 13/404889/344799/66; `/v1/random`
  → a verse; `BIBLE_API_PORT` remap ✓. **Air-gap proof:** `docker run --network none`
  (confirmed zero outbound network) still serves `/healthz` and renders `/docs` with **no CDN
  refs** — `swagger-ui-bundle.js` + `redoc.standalone.js` both 200, healthcheck `healthy`.
- **Two bugs the build/run caught (fixed in this slice):**
  1. **No `.dockerignore` → `data/private/` leaked into the image** (`COPY data/` swept in
     ESV/NET/NKJV/NLT; the baked db had 17 translations). Added `.dockerignore` excluding
     `data/private/` (+ host `.venv`/VCS/caches); image now bakes exactly the 13 PD
     translations. *Licensing-critical — only caught by building.*
  2. **`uv run … loader` re-synced the env editable** (re-added dev deps, reinstalled the
     workspace editable), undoing `--no-editable`; the source-less runtime then died with
     `ModuleNotFoundError: bible_api`. Fixed by running the loader via `/app/.venv/bin/python`.
  Both reinforce the lesson: a green pytest/pyright/`compose config` does **not** prove the
  image runs — build + run it.
- **snap-docker gotcha (operator):** snap's Docker leaves `/var/run/docker.sock` `root:root`
  and doesn't honor the host `docker` group, so non-root `docker` fails even after
  `usermod -aG docker`. Use `sudo docker …`, or (single-user box) `sudo chmod a+rw
  /var/run/docker.sock` (resets on `snap restart docker`). Not a repo issue; noted for deploy.
- **For Slice 9 (Documentation) future-you:** Concord is now **feature-complete and
  deployable**. The functional operator README this slice produced is the *skeleton* —
  Slice 9 warms it into a welcoming guide (the "what/why" narrative, a committed banner
  image, repo description + tags, an endpoint walkthrough). The OpenBible.info CC-BY
  attribution already in the README must stay. Nothing else to build — it's polish.

### Slice 9 — Documentation & polish
- 2026-06-04 — PR: https://github.com/kbennett2000/concord/pull/11. The final slice.
  Audience-aware `README.md` rewrite + new `docs/API.md` endpoint reference + committed
  `docs/banner.svg`. **No code changes** (`git diff main -- bible-core bible-api/src` empty);
  337 tests still green.
- **Q1** `docs/API.md` = one file, TOC + anchors. **Q2** env-var table canonical in the
  README, API.md links to it. **Q3** three-way decision tree (developer / curious / wants-an-app).
  **Q4** "Building on Concord" = soap-journal(-mobile) + tutorial forward-signal + `/v1`
  stability + in-process `bible-core` embedding.
- **Repo metadata applied (confirmed via `gh repo view`):** description = "A self-hosted,
  LAN-first, read-only Scripture API serving multiple public-domain Bible translations from
  one canonical source."; topics = bible, bible-api, scripture, self-hosted, lan-first,
  offline-first, fastapi, sqlite, fts5, public-domain, church-tech, homelab (12).
- **Accuracy discipline:** every `curl`/JSON in the README and API.md was captured from a
  live instance built with the 13 PD translations (not hand-written). Verse texts are real
  KJV/WEB; params/fields/codes cross-checked against `routers.py`/`schemas.py`/`errors.py`.
- **Consolidation done:** the user-facing nuggets earlier slices flagged "for the docs" are
  now surfaced — FTS5 syntax, cross-ref clamping, `/random` no-store, the `/healthz` shape,
  env-var defaults, error codes, the OpenBible.info attribution, the reference grammar +
  jud/jdg. The dev-notes stay as the build's historical record.
- **A late catch worth remembering:** PR #9 (Slice 8) was merged at its pre-verification tip,
  so the two image fixes I made *while building the container* (`.dockerignore`,
  `.venv/bin/python` loader) didn't reach `main` — `main`'s image was briefly both broken and
  non-distributable. Landed via a follow-up (PR #10) before this slice. Lesson: fixes pushed
  to a branch *after* its PR merges are orphaned; open a fresh PR.

#### Retrospective — nine slices, v1 shipped
- **What worked:** the slice discipline (one reviewable PR each, dev-notes captured as we
  went) and the hard `bible-core`/`bible-api` boundary. The web-free core paid off repeatedly
  — pure, fast unit tests and a free in-process embedding path. Establishing the patterns
  early (error envelope, `cached_json_response`, resolver, parser) made Slices 5–7 nearly
  mechanical. Discovering each input contract from the *real* files instead of assuming caught
  quirks (JPS Masoretic verse splits, 655 cross-chapter clamps, votes ≤ 0) before they became
  bugs. Reproducible byte-identical `bible.db` made the Docker bake trivial.
- **Deferred to v2:** semantic search via embeddings (highest-leverage next step),
  Catholic/deuterocanonical data + Vulgate versification mapping, multi-translation search,
  biblical geography, and a CI pipeline running the gate on PRs.
- **What I'd do differently:** wire CI from Slice 0 (the gate ran only locally throughout),
  and **build the Docker image earlier** — green pytest/pyright/`compose config` hid two
  image-level bugs until an actual build in Slice 8. Verify the artifact, not just the tests.
- **v1 is shipped.** Concord's first milestone: a complete, feature-frozen, deployable,
  documented, offline-first Scripture API — exactly the read surface designed in SPEC §6, no
  more and no less.

## v2 — Semantic search

### Slice S0 — Semantic package & inference core
- **Date:** 2026-06-04. **PR:** #12 (`slice/v2-s0-semantic-core`).
- **What landed:** new `bible-semantic` package (third in the workspace), web-free and
  ML-bearing (`onnxruntime` + `tokenizers` + `numpy`); `model.py`'s `embed_query` (one text →
  768-dim L2-normalized float32 vector) with no PyTorch; `scripts/fetch_model.py`; fast +
  integration tests; CLAUDE.md + `docs/v2/SPEC.md` updates.
- **Model & acquisition:** `ibm-granite/granite-embedding-311m-multilingual-r2` (Apache 2.0,
  ModernBERT, 768-dim). Fetched by `scripts/fetch_model.py` via **stdlib `urllib`** (zero new
  deps), **pinned to revision `44399559930365213510b1ee2eb15ded83374f0e`** (HF `main` as of
  2026-05-18) so fetches are byte-identical and don't drift. Files: `onnx/model.onnx` (fp32,
  ~1.25 GB), `tokenizer.json`, `config.json` → gitignored `models/`. **fp32 for S0**
  correctness; int8 (`onnx/model_quint8_avx2.onnx`) is the S3 runtime target.
- **Exact inference recipe used:** tokenize (`tokenizers`, special tokens on, no instruction
  prefix) → ONNX infer (`input_ids` + `attention_mask` only; ModernBERT has no
  `token_type_ids`; output 0 = last_hidden_state `(1, seq, 768)`) → **CLS pool** (token 0,
  `out[0,0,:]`) → **L2-normalize**. **No dense projection.**
- **The S0 finding:** the spec (and the slice prompt) assumed **mean-pooling**; the model card
  says verbatim *"granite-embedding-311m-multilingual-r2 uses CLS Pooling"*. Code uses CLS;
  `docs/v2/SPEC.md` §5/§8 corrected to match. Catching the wrong recipe before embedding the
  corpus is the entire reason S0 exists.
- **Observed sanity cosines** (unit-norm vectors, so cosine = dot product): related pair
  ("Do not be anxious about anything" / "Cast your cares on him") = **0.839**; each vs the
  unrelated "a genealogy of the kings of Israel" = **0.750** / **0.760**. Related > both →
  recipe correct, not merely well-shaped. (Absolute cosines run high for this model; the
  *ordering* is the signal.)
- **ONNX / tokenizers gotchas:** `onnxruntime` ships no type stubs → a file-scoped pyright
  pragma in `model.py` only (rest stays strict). Test files need unique basenames under
  pytest's prepend-import mode (no `__init__.py` in `tests/`) → `test_semantic_*` prefix to
  avoid colliding with `bible-core`'s `test_import.py`. `tokenizers` pulls `huggingface-hub`
  transitively — not a direct dep, not in the forbidden ML set. Integration tests are marked
  `@pytest.mark.integration` and skip cleanly when `models/` is absent, keeping the default
  suite fast/offline (343 passed, 7 deselected).

### Slice S1 — Embeddings store & corpus build
- **Date:** 2026-06-04. **PR:** #13 (`slice/v2-s1-corpus-build`).
- **What landed:** the `embeddings.db` schema (`bible_semantic/schema.py`:
  `verse_embeddings` + `embedding_meta`), a batched `embed_texts` in `model.py` (with
  `embed_query` now delegating to it), the build-time generator `build.py`, the
  `scripts/build_embeddings.py` CLI, and one additive read-only `bible-core` helper.
- **WEB corpus:** **31,054** verses, 0 empty/whitespace (verified against `bible.db`). One
  row per verse → `embeddings.db` is **~128 MB** (31,054 × 3,072-byte vectors ≈ 95 MB plus
  SQLite page + primary-key index overhead; SPEC §6's ~95 MB was vectors-only).
- **Observed build time (this machine, fp32, AVX2):** **1,376 s ≈ 22m56s** wall at batch
  size **64** (CPU `onnxruntime`, all cores). Slower than first guessed — granite-311M fp32
  is hefty. The slow AVX2-less Optiplex figure is **deferred to the deploy slice (S3)**,
  the same way v1 deferred its Docker-host check; int8 (also S3) should cut both size and
  time.
- **Bulk-access decision:** `bible-core` had no whole-translation reader (only
  reference-scoped `get_verses`/`get_chapter`), so added one additive, read-only generator
  `bible_core.queries.iter_verses(conn, translation_id)` — yields the existing `VerseRow`
  ordered by `books.canonical_order, chapter, verse`. `bible-semantic` reads `bible.db`
  only through `connect_readonly` + `iter_verses`, never directly; writes its own
  `embeddings.db` with stdlib `sqlite3`. No other `bible-core` change.
- **Metadata columns:** `model`, **`model_revision`** (new — the pinned S0 SHA, so S2's
  guard can catch "built with X, runtime loaded Y"), `dim`, `translation`, `normalized`,
  `built_at`. SPEC §6 updated to match.
- **Idempotency:** rebuilds from scratch (`unlink(missing_ok=True)`). fp32 CPU inference is
  deterministic and ordering + batch size are fixed, so a given verse's vector is
  byte-identical across runs — the test proves this with two `limit=256` builds (fast)
  rather than embedding 31k verses twice. `built_at` is the only thing that varies between
  builds (a wall-clock timestamp), so the whole-file bytes differ even though vectors don't.
- **Batching / CLS:** `tokenizer.encode_batch` + numpy right-pad (pad id 0,
  `attention_mask=0` on pads); CLS pooling reads token 0 (always real, never padding), so
  padded positions are masked out and a batched result matches the single-input result —
  no attention-mask gymnastics that mean-pool would have needed.
- **Config:** output via `CONCORD_EMBEDDINGS_PATH` (default repo-root `embeddings.db`);
  input `bible.db` via v1's existing `BIBLE_DB_PATH` (default `bible.db`). `embeddings.db`
  is gitignored (added in S0).

### Slice S2a — Search core
- **Date:** 2026-06-05. **PR:** #14 (`slice/v2-s2a-search-core`).
- **S2 split into S2a/S2b.** The v2 spec (§10) had S2 as one slice; we split it into **S2a
  (search core, this slice — library function)** and **S2b (the HTTP endpoint)**. The core
  is correctness-critical and cleanly testable in isolation; the endpoint is thin on top.
- **What landed:** `search.py` (pure cosine top-k), `store.py` (vector-store loader +
  model-vs-vectors guard + `semantic_search` orchestration). No HTTP, no hydration, no
  caching (all S2b); `bible-core`/`bible-api` untouched.
- **Lifecycle:** `load_store(path=None) -> VectorStore` (no global state — tests call it
  directly) + a lazy module-level singleton `get_store()`. `semantic_search` uses
  `get_store()`, so the ~95 MB matrix loads **once** per process; S2b's FastAPI lifespan can
  prime it at startup.
- **The guard (the point of S1's `model_revision`):** `load_store` reads `embedding_meta`
  and refuses to load (`StoreError`) if `model` / `model_revision` / `dim` differ from the
  running code's `MODEL_ID` / `MODEL_REVISION` / `EMBEDDING_DIM`, or if `normalized != 1`.
  Detects "vectors built with revision X, code now pins Y" rather than serving garbage
  similarities. `load_store` never invokes the model, so the guard tests are fast.
- **Matrix construction:** `SELECT ... ORDER BY book_id, chapter, verse`, preallocate
  `np.empty((N, 768), float32)`, fill per row via `np.frombuffer` (each blob asserted 3072 B).
  **Observed load time 0.18 s** for 31,054 rows; footprint **95.4 MB** held once.
- **`min_score`:** a cosine floor on `[-1, 1]`. Implemented as: sort all by score desc
  (`np.lexsort`, ties by ascending index for determinism), then walk top-down, breaking when
  a score drops below the floor or `k` is reached — equivalent to "score → filter → top-k".
- **Real-corpus evidence (`semantic_search`, top-5):** `"do not be anxious"` → MAT 6:34,
  LUK 12:29 surface (Matthew 6 "do not worry" passage); `"love your enemies"` → **MAT 5:44**
  #1; `"the good shepherd"` → **JHN 10:11** #1. The integration test asserts a known anxiety
  verse appears in the top-20. First query pays a one-time ONNX session warm-up (~3.3 s);
  subsequent queries ~80–120 ms.
- **Gotchas:** numpy fancy-indexing/`lexsort`/`tolist` return loosely-typed arrays under
  pyright-strict — pinned with explicit `NDArray` annotations + a `list[int]` bind rather
  than a file pragma. `pytest.approx` is loosely typed too → used plain tolerances (matches
  S0). Test files keep the `test_semantic_*` prefix to avoid basename collisions (bible-core
  already has `test_search.py`).

### Slice S2b — Semantic search endpoint
- **Date:** 2026-06-05. **PR:** #15 (`slice/v2-s2b-endpoint`). **S2 (S2a + S2b) complete.**
- **What landed:** `GET /v1/semantic-search` in `bible-api`, the cross-translation text
  hydrate, body-hash ETag caching (reused `cached_json_response`), FastAPI-lifespan priming
  (store load + guard + model warm-up), `/healthz` semantic readiness, and a `bible-api →
  bible-semantic` workspace dependency. `bible-core` and `bible-semantic` untouched.
- **Default display translation = `WEB`** (the embedded translation): a new
  `resolve_display_translation` mirrors `resolve_translation` but defaults to the store's
  embedded translation. Search always runs in WEB space; `translation` only chooses
  displayed text.
- **Unknown translation → 404, not 400:** SPEC §7 said `400 "consistent with /v1/search"`,
  but v1 actually returns **404** for an unknown translation (`UnknownTranslationError`;
  400 is the unknown-*book* filter). Reused that path → 404 `unknown_translation`, and
  **corrected SPEC §7 400→404** (Kris-confirmed).
- **Hydrate:** per-ref `bible_core.queries.get_verse_text(conn, translation, b, c, v)` →
  `str | None`; a verse absent in the requested translation yields `text: null` (the match
  still ranks). `reference` ("Philippians 4:6") from a `book_id→name` map cached on
  `app.state` at startup. `score` rounded to **4 dp**.
- **Priming vs test speed:** config flag `CONCORD_SEMANTIC_SEARCH` (default on) +
  `create_app(enable_semantic=..., embeddings_path=...)`. The API holds its own
  `app.state.semantic_store` (from `load_store` at lifespan) and composes `embed_query` +
  `cosine_top_k` — *not* the `get_store()` singleton — so the store path is injectable. The
  shared fast-test `client` fixture passes `enable_semantic=False`; the endpoint then 503s
  (`semantic_unavailable`) and **no model loads**, keeping the fast suite ~0.6 s. Real
  results are integration-marked against the repo's `bible.db` + `embeddings.db`.
- **Boot guard:** lifespan runs `load_store` (the model-vs-vectors guard); a mismatch raises
  `RuntimeError` → the app **refuses to start**. Tested fast by pointing at a tiny
  mismatched `embeddings.db` (fails at the guard, before any model load).
- **`/healthz` shape:** adds a nested `semantic` object —
  `{enabled, translation, embedding_count, model, dim}` (or `{enabled: false}` when off).
- **Observed (primed, live uvicorn on the dev box):** first real query ~**54 ms** (model
  pre-warmed at startup, so no ~3 s first-hit penalty); ETag 200→304 round-trip confirmed;
  `/healthz` reports `embedding_count: 31054`, `translation: WEB`, `dim: 768`.
- **Gotchas:** `bible-api` now depends on `bible-semantic` (workspace path dep) — importing
  `routers` pulls `onnxruntime` at import time, but the *model* loads only on prime, so fast
  tests stay model-free. bible-api endpoint tests need the existing file-level pyright pragma
  for the untyped `TestClient`/httpx surface. The endpoint integration test is
  `test_semantic_endpoint_real.py` (not `..._search_real.py`) to avoid colliding with
  bible-semantic's S2a test of that name. Integration validated for `bible-api` (9 passed);
  `bible-semantic` is untouched so its suite (incl. S1's ~23-min build) is unaffected.

### Slice S3a — int8 standardization & quality validation
- **Date:** 2026-06-05. **PR:** #16 (`slice/v2-s3a-int8`). S3 was split: **S3a (int8 + the
  quality gate, this slice); S3b (Docker & deploy).**
- **int8 obtained by FETCH, not quantize.** The granite repo publishes
  `onnx/model_quint8_avx2.onnx` (IBM's official dynamic uint8 quantization) at the pinned
  revision `44399559…` — fetched via the existing pinned-SHA `scripts/fetch_model.py` (no
  `quantize_model.py`, no calibration; reproducible by construction). **313 MB vs fp32's
  1.25 GB** (~4×) — the size relief SPEC §4 needs to stay under the deploy target.
- **int8 is now the default everywhere** (`model_precision()`, env `CONCORD_MODEL_PRECISION`,
  default `int8`, selecting the ONNX filename). fp32 stays selectable for dev/baseline only;
  `fetch_model.py` gets fp32 only with `--fp32`. Stored vectors remain float32 — precision
  is the inference path, not the vector dtype, so `verse_embeddings` is unchanged.
- **Precision guard:** new `precision` column in `embedding_meta` (written by `build.py`);
  `store._check_guard` refuses to load when the corpus precision differs from the running
  model's — query and corpus must share precision to compare correctly. SPEC §6 updated.
- **int8 build time:** **1267 s (~21m7s)** for 31,054 WEB verses, batch 64 — vs fp32's
  ~22m56s (only ~8% faster on this AVX2 box; the win is size, not build speed). Meta records
  `precision=int8`, 31,054 rows.
- **int8-vs-fp32 quality (top-5; fp32 = S2a baseline):**
  - `"love your enemies"` → **MAT 5:44 #1** (int8 0.928) — identical to fp32 #1.
  - `"the good shepherd"` → **JHN 10:11 #1**, JHN 10:14 #2 — identical to fp32.
  - `"do not be anxious"` → DEU 1:29 #1, HAG 2:5 #2; **MAT 6:34 moved #5→#7** but stays
    comfortably in top-20 (LUK 12:29 #10). Verdict: **acceptable** — canonical top-1 results
    preserved, only mild tail reordering (expected from quantization). The S2a/S2b
    appear-in-top-k integration tests pass on the int8 corpus (7 passed). Bar met; no fp32
    fallback needed.
- **AVX2 note:** the file is IBM's `_avx2`-labeled quantization; ONNX Runtime falls back to
  AVX kernels on the AVX2-less Optiplex (slower, still correct). **Optiplex timing +
  `--network none` verification are S3b.**
- **Gotchas:** the `precision` column is positional in `_read_meta`'s SELECT / `EmbeddingMeta`
  / `build.py` INSERT — kept in sync (after `dim`). Hand-built test embeddings.dbs
  (`test_semantic_store`, bible-api `test_semantic_boot_guard`) + the schema column-list test
  were updated for the new column. **int8 is now standard; S3b does the Docker packaging.**

### Slice S3b — Docker & deploy
- **Date:** 2026-06-05. **PR:** #17 (`slice/v2-s3b-docker`). Second half of the split S3.
  Authored by cc; **Docker build + offline check + measurements are Kris's** (no Docker on
  G434), mirroring v1 Slice 8.
- **Embeddings: built IN the builder stage** (not COPYed from a host pre-build) — a clean
  clone `docker build`s everything, fetching the int8 model at build time and baking the int8
  `embeddings.db`, exactly as v1 bakes `bible.db` via the loader in-builder. Self-contained;
  the ~21-min embed runs on the capable build machine.
- **Image structure (extends v1's multi-stage):** builder adds `bible-semantic` to the
  workspace COPY/sync (so `uv sync --no-editable` installs it + onnxruntime/tokenizers/numpy),
  copies `scripts/`, runs the loader → `fetch_model.py` (int8, pinned `44399559…`) →
  `build_embeddings.py`. Runtime additionally copies `/app/embeddings.db` + `/app/model`.
  fp32 (1.25 GB) never enters the image; the model is baked so **runtime needs no network**.
- **Explicit artifact paths:** packages install `--no-editable`, so bible_semantic's
  `__file__`-relative path defaults don't resolve in `.venv` — both stages set
  `BIBLE_DB_PATH=/app/bible.db`, `CONCORD_MODEL_PATH=/app/model`,
  `CONCORD_EMBEDDINGS_PATH=/app/embeddings.db` (same pattern v1 uses for `BIBLE_DB_PATH`).
  No Python changes — the env drives the existing scripts/store.
- **Hardening:** healthcheck (Dockerfile + compose) is now **semantic-aware** —
  `translation_count > 0` AND `semantic.enabled` — with `start_period` raised to 60s for the
  boot-time model warm-up (slower on a no-AVX2 box). compose memory rail raised **512M → 2g**
  (the §4 footprint); `make docker-verify` adds a `/v1/semantic-search` ranked-results check
  alongside the offline `/docs` no-CDN check. `.dockerignore` now excludes `models/` +
  `embeddings.db` (host copies kept out of the build context).
- **Deploy guidance (build-on-fast-machine):** build the image on a capable machine (G434),
  then `docker save concord:latest | gzip > concord.tar.gz` → copy to the Optiplex →
  `docker load`. The modest box only ever runs the fast query path; it never builds (a
  no-AVX2 in-Docker embed could be 1–2 hr). Full README treatment is S4.
- **Verification + measurement sequence for Kris** (also in the PR body):
  `docker compose build`; `docker run --rm --network none -p 8000:8000 concord:latest` then
  `curl /v1/semantic-search?q=do+not+be+anxious` (ranked) + `curl /healthz`
  (`semantic.enabled:true`, `embedding_count:31054`) — the **offline proof**; then
  `docker images` (size), `docker stats` (RSS), and timed queries on G434 + Optiplex.
- **Measured (2026-06-05, built on G434, verified on G434 + the Optiplex).** Docker turned
  out to be available on G434 after all, so cc ran the whole verification rather than
  leaving it to a separate host pass:
  - **Image size:** 1.42 GB on-disk / **446 MB compressed** (the ship size). On-disk exceeds
    the original "well under 1 GB" estimate — breakdown: model 347 MB + venv/ONNX 228 MB +
    `bible.db` 139 MB + `embeddings.db` 128 MB + base ~130 MB. A future trim (slimmer ORT,
    fewer baked translations) is a possible follow-up, not S3b.
  - **Runtime RAM:** ~662 MiB RSS (both boxes) — well under the 2 GB rail and the §4 estimate.
  - **Query latency (warm median):** G434 (AVX2) **42 ms** (32–59); Optiplex (AVX-only, int8
    via ORT fallback) **92 ms** (59–109). Optiplex cold-start→ready 6.0 s. The AVX-fallback
    worry was overblown — sub-100 ms on the $50 box; no non-AVX2 variant needed.
  - **Offline (`--network none`):** ✅ verified on **both** boxes — ranked semantic results +
    `/healthz` semantic-ready, no Hugging Face reach. The model baked correctly.
  - **Deploy path validated:** `docker save | gzip` (446 MB) → `scp` (~2 min) → `docker load`
    (~36 s) on the Optiplex; the modest box never builds.
  - **Build time:** ~22 min on G434 (the in-builder int8 embed dominates).
- **Bug found by this verification:** the Optiplex offline run surfaced an intermittent 500
  from a cross-thread SQLite `close()` (`check_same_thread`) on every sync endpoint — latent
  in v1, tripped by the Optiplex's thread scheduling. Fixed in **PR #18** (see the fix entry
  below); the image was rebuilt on the fix and the numbers above are post-fix (25/25 queries
  200 on both boxes).

### Fix — cross-thread SQLite close (found during S3b verification)
- **Date:** 2026-06-05. **PR:** #18 (`fix/sqlite-cross-thread-close`), off `main`.
- **Bug:** `bible_core.db.connect_readonly` opened the connection with the default
  `check_same_thread=True`. Under uvicorn, FastAPI runs a sync endpoint in a threadpool and
  a generator dependency's `finally: conn.close()` (`bible_api.dependencies.get_conn`) can
  run on a *different* worker thread than the one that opened the connection → intermittent
  `sqlite3.ProgrammingError` surfaced as **HTTP 500** on any sync endpoint (all of v1 +
  semantic-search). Latent and timing-dependent (tests/TestClient + G434 reused the thread
  and never tripped it); the **Optiplex's thread scheduling tripped it on the 2nd request**
  during S3b's offline run.
- **Fix:** `check_same_thread=False` in `connect_readonly`. Each request gets its own
  read-only connection, so access is never concurrent — only the cross-thread `close()` —
  making the check safe to disable (the standard FastAPI + sqlite remedy). Shipped with a
  regression test (`test_readonly_connection_usable_across_threads`) that reproduces the
  cross-thread close and failed before the fix.
- **Note:** unblocks the S3b Optiplex latency measurement — after this merges, rebuild the
  image, re-run the Optiplex warm-latency, and land the S3b numbers in PR #17.

### Slice S4 — Documentation & ship
- **Date:** 2026-06-05. **PR:** #20 (`slice/v2-s4-docs`). **v2 is shipped.**
- **What landed:** semantic search woven into the existing README (decision tree, intro,
  Quick start, a Nine-endpoint tour, a "Semantic search" subsection, a two-tier Requirements
  table, build-on-a-capable-machine deploy guidance, the Granite Apache-2.0 attribution, and
  geography promoted to the named next frontier); the `/v1/semantic-search` reference in
  `docs/API.md` (+ the now-accurate `/healthz` example with the `semantic` block). Docs only;
  every curl/JSON captured from the running int8 image.
- **Doc choices:** the v1 README had no hardware table, so the measured numbers went into a
  new compact two-tier Requirements table in the README's table style; `docs/API.md` keeps the
  two search endpoints adjacent. No changelog/version convention exists (pkg versions `0.0.0`),
  so this dev-notes marker is the ship record.

#### Retrospective — v2, seven slices
- **The shape:** S0 stood up `bible-semantic` + proved the ONNX embedding (CLS-pool, not
  mean-pool — the model card corrected the spec on slice one). S1 baked the WEB corpus
  (`embeddings.db`, ~31k vectors, the `model_revision` guard). S2a/S2b were the split search
  core then the `/v1/semantic-search` endpoint (search-in-WEB / display-in-any-translation,
  the lifespan guard). S3a standardized on int8 and proved quality held (313 MB vs 1.25 GB,
  canonical top-1 results preserved). S3b shipped the offline image; S4 documented it.
- **What real-hardware verification earned:** two bugs the fast path missed — the CLS-vs-mean
  pooling recipe (caught by reading the model card in S0) and the cross-thread SQLite `close()`
  500 (caught only on the Optiplex in S3b, latent in v1 too). The spec was corrected three
  times when reality disagreed (mean→CLS, 400→404 unknown_translation, the §6 metadata).
- **The measured close:** semantic Scripture search in **~92 ms on a $50 2012 desktop** (~42 ms
  modern), ~662 MB RAM, **fully offline** (`--network none` verified), in a ~450 MB image. The
  `bible-core` web-free boundary is intact; `bible-semantic` is web-free too. **v2 is shipped.**

## v3 — Geography

### Slice V3-S0 — Places schema & geo ingestion
- **Date:** 2026-06-05. **PR:** #21 (`slice/v3-s0-places-ingest`).
- **What landed:** the additive `places` + `place_verses` tables in `bible.db` (owned by
  `bible-core`, existing tables untouched), the build-time `bible_core.geo` loader ingesting
  the disciplined subset of OpenBible's `ancient.jsonl` + `modern.jsonl`, the ref mapping and
  two-axis confidence/status derivation, the committed CC-BY-4.0 source data + attribution,
  the `docs/v3/SPEC.md` commit, and the CLAUDE.md scope update. No endpoints (V3-S1), no
  README prose (V3-S2). The geo data bakes into `bible.db` via the existing build flow (the
  cross-references precedent) — **no Dockerfile change** (`COPY data/ data/` + a default
  `geo_dir` in `main()` carry it in).
- **Place count:** **1340 places** (1342 ancient records − 2 pure non-places), **8738
  place-verse links** (8742 verse entries − 4 same-verse dedups). Stable across rebuilds
  (byte-identical). Status split: **identified 1264 · disputed 66 · unknown 5 · symbolic 3 ·
  multiple 2**; confidence (coord-bearing only): high 749 · medium 545 · low 36.
- **Subset extracted (SPEC §4):** `id` (the stable PK), `friendly_id`, derived `name` +
  `url_slug`, `type`, `preceding_article`, best coordinates, `confidence`/`confidence_score`,
  `status`, `modern_name`, and the verse links. **Deliberately ignored:** time-weighted
  scores, resolution `paths`/`best_path_score`, all geometry (geojson/kml/isobands), images,
  `linked_data`, the 400+ sources, `epsg_28191`, and the per-translation spelling apparatus.
- **Field reality vs the spec's labels (the S0 finding):** the live data's `name` and `type`
  (singular) are **`null` for all 1342 records** — display `name` is derived from
  `friendly_id` (trailing " N" stripped: "Eden 1"→"Eden") and `type` from the `types` array
  (100% populated). `modern.jsonl`'s `lonlat` is **"longitude,latitude"** order (longitude
  first) — Jerusalem stores lat 31.777 / lon 35.234. The `special` marker lives at
  `identifications[].resolutions[].special` and carries a **6th kind, `recursive`**, absent
  from SPEC §6. Adjusted scores run **−87..1169**, not the upstream "0–1000". `docs/v3/SPEC.md`
  §4/§5/§6 were amended to this reality.
- **Two-axis honesty model (per Kris):** `confidence` (evidence strength) and `status`
  (resolution kind) are independent. **Confidence buckets:** high ≥ 500 · medium 100–499 ·
  low < 100 (negatives included as low) — calibrated against the real distribution (median
  577). **Status from the resolution kind**, never collapsed from the bucket.
- **Status-precedence refinement (discovered at impl — the planned "inspect the dual-flagged
  records" check earned its keep):** a naive "semantic special always wins" would null
  well-attested places, because **`recursive` co-occurs with strong associations** (Chesalon
  recursive@702, Beth-biri@625). So `recursive` is treated as a resolution-path *artifact*,
  not a semantic claim — it never voids a real association; a recursive-only place with no
  association is honestly `unknown`. The **semantic** specials (`unknown_place`,
  `nonspecific_place`, `multiple_locations`) *do* suppress coordinates and take precedence
  over a tentative association (honesty-first). **Competing** = a runner-up association ≥ 0.8×
  the top score with both ≥ 100 → `disputed`. **Net-negative best score → `disputed`, never
  `identified`** (coordinates kept but hedged via low confidence).
- **Eden vs Nod (the spec-example deviation, resolved):** an early ma-first scan suggested
  Eden wasn't marked unknown; the correct **semantic-special-first** precedence classifies
  **"Eden 1" (slug `eden-1`, Gen 2:8) as `unknown` with null coordinates** — vindicating the
  spec's original Garden-of-Eden example. **Nod** (Gen 4:16) is the other clean unknown. Both
  are asserted in the integration test; Eden's tentative associations are honestly suppressed.
- **Open-question answers:** (1) `not_a_place`/`not_a_proper_name` → **excluded** only when
  the place has no coordinate-bearing association (net **2** excluded). (3) `alternate_verses`
  → **ignored**; primary `sort` only. (4) association selection → **highest score**,
  deterministic tie-break (then lowest modern id). (5) **footprint:** committed whole —
  `ancient.jsonl` 11 MB + `modern.jsonl` 3.1 MB (~14 MB), comparable to the 8.3 MB
  cross-references; no trimming/gzip.
- **Ref mapping:** `sort` (BBCCCVVV) → USFM via `canonical_order`, `osis` fallback, `readable`
  never parsed. All 8742 verse entries had valid in-canon sorts, so the out-of-canon
  skip-and-count path is defensive (0 skipped on real data). `place_verses.book_id` FK to
  `books` held for every row.
- **Gotchas:** the loader↔geo import cycle (geo imports `LoaderError` from `loader`) is broken
  by a **local import** of `geo` inside `build_database`. `symbolic` is rare (3 rows) and
  every `nonspecific_place` also carried a tentative association, so the honesty-first rule is
  what makes those rows appear at all.

### Slice V3-S1 — Places endpoints
- **Date:** 2026-06-05. **PR:** #22 (`slice/v3-s1-places-endpoints`).
- **What landed:** the four read-only geography endpoints in `bible-api`, reusing v1's
  machinery throughout — `GET /v1/places` (browse: `type`/`status`/`q` filters + pagination),
  `GET /v1/places/{id}` (detail + verse count), `GET /v1/places/{id}/verses` (verses, text
  hydration), `GET /v1/verses/{ref}/places` (the inverse). Plus the supporting `bible-core`
  read queries, the Pydantic models, the `unknown_place`/filter errors, and `place_count` in
  `/healthz`. No schema/loader change; no new data; no README prose (V3-S2).
- **`bible-core` queries (additive):** `list_places`, `get_place`, `count_place_verses`,
  `get_place_verses`, `get_places_for_reference`, `distinct_place_types` in `queries.py`,
  modeled on `get_cross_references` and **reusing `_span_predicate`** + `get_verse_text`. The
  API writes no raw SQL — it calls these, exactly as the cross-references endpoint does.
- **Open-question answers:** (1) **`{ref}/places` range semantics** — the deduped **union** of
  places across the reference's spans (`SELECT DISTINCT … JOIN place_verses` with the OR of the
  span predicates); a valid-but-placeless ref → 200 empty list; an unparsable ref → 400; an
  unknown book → 404 (the parser's existing wiring). No pagination on this endpoint (a
  reference spans few places; the corpus is 1340). (2) **`/v1/places` default ordering** —
  `name ASC, id ASC` (a stable tiebreak so the disambiguated same-name places paginate
  deterministically). (3) **`disputed` representation** — surfaced **with** best-guess
  `latitude`/`longitude` + `status:"disputed"` + medium/low `confidence`; only
  unknown/symbolic/multiple carry null coords. (4) **`/healthz`** — added `place_count`,
  cached at startup like `cross_ref_count`.
- **Honesty model in responses:** coordinates are surfaced as **named `latitude`/`longitude`**
  fields (never an ordered `lonlat` pair a consumer could misread — the V3-S0 hemisphere-flip
  trap, closed at the API boundary). Jerusalem (`a15257a`) → `31.776667, 35.234167`, high,
  identified; Nod/Eden → null coords, `status:"unknown"`.
- **Errors:** `UnknownPlaceError` → 404 `unknown_place` (path resource), `PlaceFilterError`
  carrying its own `code` → 400 `unknown_type` (validated against `distinct_place_types`, with
  the available list in `detail`) / `unknown_status` (the fixed 5-value enum) — mirroring
  `BookFilterError`'s "filter is 400, path resource is 404" distinction. Bad pagination → the
  existing 422 `invalid_parameter`.
- **Gotchas:** (a) the new api test files needed the same per-file pyright suppression the
  existing api tests carry (`reportUnknownMemberType=false`, …) — httpx's `TestClient` response
  is untyped, so without it strict pyright flags every `.get(...).json()`. (b) The startup
  `place_count` query makes `places` part of the **required schema** — a stale pre-V3-S0
  `bible.db` now fails loudly at boot with the rebuild hint (correct, consistent with the
  existing table checks); the local repo-root `bible.db` artifact had to be rebuilt for the v2
  semantic real tests to pass. (c) Real settlement count is **843** (844 ancient minus the one
  excluded `not_a_place` that carried a settlement type).

### Slice V3-S2 — Documentation & ship
- **Date:** 2026-06-05. **PR:** #23 (`slice/v3-s2-docs`). **v3 is shipped.**
- **What landed:** geography woven into the existing `README.md` (intro clause, a curious-reader
  line in "What is this, really?", the developer decision-tree path, the endpoint tour Nine →
  **Thirteen**, a new "Geography" subsection parallel to "Semantic search", the OpenBible CC-BY
  4.0 attribution in the data + license sections, an honest upgrade/rebuild note in Deployment,
  a Requirements line, and journeys/routes promoted to the named next frontier); the four
  geography endpoints in `docs/API.md` (TOC, Errors table, the `/healthz` `place_count`, and a
  status table making the honesty model visible). Docs only; the README's voice matched to the
  surrounding v1/v2 prose. Every curl/JSON captured from a running instance (public `/healthz`
  counts kept; place data is identical across the 13- and 17-translation builds).
- **Doc choices:** geography sits with cross-references in `API.md` (reference-linked data); the
  `/v1/places/{id}` entry documents the honesty model with a status table **and** an unknown
  place (Nod) returning null coordinates, so the "never a fabricated pin" promise is visible in
  the reference, not just the prose. Acts 17 → its six places (Athens, Berea, Thessalonica, …)
  is the bi-directional showcase. No changelog/version convention exists (pkg versions `0.0.0`),
  so this dev-notes marker is the ship record.

#### Retrospective — v3, three slices
- **The shape:** S0 baked the `places` + `place_verses` tables and the disciplined-subset geo
  loader (1340 places); S1 added the four read-only endpoints over them, reusing v1's machinery
  whole; S2 documented it and shipped. The calmest version of the three — no new package, no ML,
  no runtime model, just data tables and endpoints riding the existing build.
- **What data-grounding caught (the recurring lesson, again):** the spec's field labels didn't
  survive contact with the real OpenBible data — top-level `name`/`type` are **null** (derive
  from `friendly_id`/`types[]`), `lonlat` is **longitude,latitude** (a hemisphere-flip trap
  closed by surfacing named `latitude`/`longitude` at the API), a sixth `recursive` special kind
  exists, and scores run −87..1169 not 0–1000. The precedence refinement — `recursive` is a path
  artifact that must **not** void a strong association, while the *semantic* specials
  (unknown/nonspecific/multiple) suppress coordinates — was found by inspecting the dual-flagged
  records, and it restored the spec's own Garden-of-Eden example (Eden → unknown). The two-axis
  model (confidence = evidence strength; status = resolution kind, never collapsed) came from
  review feedback and is what keeps a modestly-attested place honestly `identified`/`low` rather
  than falsely `disputed`.
- **The foundation laid:** stable external-safe place ids and real disambiguation (the several
  Antiochs/Bethlehems are distinct), plus the bi-directional place↔verse link — exactly what a
  future journeys/routes layer needs to reference rather than rebuild. The `bible-core` web-free
  boundary held throughout (the place queries are pure SQL over the link table). **v3 is shipped.**

## Hardening sprint

Perimeter-only security hardening (no request-path logic changes; nothing under
`bible-semantic/`). One branch + one PR per slice.

### HS-1 — CI
- Added `.github/workflows/ci.yml`: runs the `make check` gate (ruff lint, ruff
  format --check, pyright strict, pytest) on every PR and every push to `main`, as four
  discrete steps over `uv sync --frozen`. Mirrors local `make check` so CI cannot drift.
- Kept fast on purpose: the default pytest run is `-m "not integration"`, so the per-PR
  job uses only synthetic tmp fixtures — it does **not** fetch the ~313 MB embedding model
  or run the ~21-min embed (those stay behind the integration marker / the Docker build).
  A Docker build + `/healthz` smoke job was deliberately deferred.

### HS-2 — Non-root container user
- Runtime stage of the `Dockerfile` only: create a system user/group `app` (uid/gid 999),
  `COPY --chown=app:app` the venv + `bible.db` + `embeddings.db` + model, and add `USER app`
  before the healthcheck/`CMD`. The image no longer runs as root.
- Read-only model confirmed and held: `bible.db` is opened `mode=ro`; `embeddings.db` is
  only `SELECT`ed once at boot by `load_store` (no journal/WAL written); logs go to stdout —
  so no writable directory is needed. `--chown` gives `app` ownership of its assets, so the
  boot-time embeddings read needs no reliance on SQLite's read-only-open fallback.
- Verified end-to-end: rebuilt (builder layers cached, only the runtime stage changed),
  container reports `uid=999(app)`, reaches `healthy`, and `make docker-verify` passes
  (corpus + semantic search primed, offline /docs, random) — all as the non-root user.

### HS-3 — Input bounds (behavior change)
- Capped unbounded inputs that previously fanned out to compute or many SQL queries:
  - `bible-api`: `max_length` on `q` (1000) for `/search` + `/semantic-search`, and on the
    `ref` path param (256) for `/verses/{ref}`, `/cross-references/{ref}`,
    `/verses/{ref}/places`. Over-length input → 422 `invalid_parameter` at the HTTP edge.
  - `bible-core` parser: `_parse_list` now rejects verse lists with > 100 elements
    (`ParseError` → 400 `unparseable_reference`). This is the load-bearing fix — each list
    element becomes its own SQL query in `queries._collect`, and the parser is embeddable
    outside the web layer, so the cap lives with it, not only at the HTTP edge.
- Tests added matching existing patterns: parser cap accept-at-100 / reject-at-101
  (`test_parser_edge_cases.py`); `q` too long → 422 (`test_search_errors.py`); `ref` too
  long → 422 and oversized list → 400 (`test_errors.py`). `make check`: 425 passed.

### HS-4 — Security headers + threat model
- `bible-api`: added a tiny pure-ASGI `SecurityHeadersMiddleware` that sets
  `X-Content-Type-Options: nosniff` on **every** response (JSON, errors, and the vendored
  static docs). No CSP — unnecessary for a JSON API and would risk the offline Swagger
  UI/ReDoc for little gain. CORS left exactly as-is; the rationale (read-only +
  unauthenticated → `*` with credentials off is safe) is now documented, not just commented.
- Docs: new `docs/SECURITY.md` (trusted-LAN threat model, CORS rationale, and a checklist of
  what to add — reverse proxy/TLS, auth, rate limiting, narrowed CORS — before any public
  exposure) plus a short Security section in the README pointing to it.
- Verified: `test_security_headers.py` asserts nosniff on a JSON endpoint, an error, and
  `/docs`; the existing `test_docs_offline.py` still passes. Confirmed against a live uvicorn
  run that `/docs` carries nosniff and still has no CDN URLs. `make check`: 428 passed.

### HS-5 — Pin base images by digest
- `Dockerfile`: pinned all three base-image references by `@sha256:` digest — `python:3.12-slim`
  in both the builder and runtime stages and the `ghcr.io/astral-sh/uv:0.11` image — with the
  human-readable tag (and resolved version, 3.12.13-slim-trixie) kept in an adjacent comment.
  Pinned to the multi-arch **index** digest so cross-arch resolution still works.
- Verified the digests pull and the image builds and runs healthy off the pinned bases.

### HS-6 — Precision-aware integration skip-guards
- Pre-Track-B cleanup. Four real-model integration tests gated their skip on the fp32 file
  `onnx/model.onnx` (the S0–S2 default); S3a moved the default to int8 without updating them,
  so they silently skipped on the int8 standard. Changed each guard to the precision-aware
  `model_dir() / "onnx" / _ONNX_FILENAMES[model_precision()]` (so it's correct in both int8
  and fp32 envs and can't drift under a future default change); the `@pytest.mark.integration`
  markers are untouched, so CI still excludes them. Files: `test_build_embeddings.py`,
  `test_semantic_embed.py`, `test_semantic_search_real.py` (bible-semantic),
  `test_semantic_endpoint_real.py` (bible-api). The private `_ONNX_FILENAMES` import trips
  pyright strict's `reportPrivateUsage`; since `model.py` is out of scope, each file carries a
  file-scoped `# pyright: reportPrivateUsage=false` pragma.
- Verified in an isolated int8-only env (`CONCORD_MODEL_PATH` → int8-only model, fp32 absent):
  `pytest -m integration` went from **22 passed / 14 skipped** to **36 passed / 0 skipped**
  (the 14 items in the four files now run + pass). `make check`: 428 passed, 36 deselected.

### HS-7 — Publish image to GHCR (first release)
- Distribution only (no runtime/behavior/Dockerfile-contents change): new
  `.github/workflows/publish-image.yml` builds the existing multi-stage Dockerfile and pushes
  to `ghcr.io/kbennett2000/concord`. **Gated to version tags (`v*`) + manual dispatch** so the
  ~22-min embed build never runs per-commit; the `ci.yml` test/lint gate is untouched. Tags
  pushed: `vX.Y.Z` + `latest` + `sha-<short>` (amd64 only; arm64 would emulate the embed for
  hours). Uses `docker/login-action` with the built-in `GITHUB_TOKEN` (`packages: write`).
- First release **v1.0.0**: bumped bible-api `__version__`/pyproject `0.0.0 → 1.0.0` (the
  OpenAPI version shown at `/docs`; refreshed `uv.lock`). Lets songbird's combined compose
  `docker pull` a ready image instead of building.
- **One-time manual step:** GHCR packages default to private — set the `concord` package
  visibility to **Public** after the first publish so `docker pull` works anonymously.
- README gains a "pull the published image" path in Deployment (additive to build-from-source
  + tarball) and a Quick start pointer.

### HS-8 — Semantic-endpoint concurrency cap (ADR-0001, Track B)
- Implements the accepted ADR-0001: a per-app bounded semaphore in **bible-api** caps
  concurrent `/v1/semantic-search` ONNX inferences; over-cap requests are shed with **503
  `semantic_busy` + `Retry-After: 1`** in the standard envelope. Knob
  `CONCORD_SEMANTIC_MAX_CONCURRENCY` (config.py, **default 2**, sized to a weak ~2-core
  non-AVX2 box; `0` disables). Inert when `CONCORD_SEMANTIC_SEARCH=0` or cap `0`; FTS5
  `/search` untouched; bible-semantic stays pure. Shed events log
  `concord.api.semantic_shed`. **No in-app inference deadline** (uncancelable `session.run()`)
  — caller-wait-time delegated to a documented client/proxy read-timeout (SECURITY.md + README).
- Tests are **deterministic** (`test_semantic_concurrency.py`): a stub store + no-op compute
  reach the guard, and "cap full" is simulated by pre-holding the permit — no threads/sleeps.
  Covers 503+envelope+Retry-After, sub-cap success, slot release, cap-0 inert, disabled-inert,
  FTS5 unaffected. ADR-0001 flipped to Accepted. `make check` green.

### HS-9 — Bump CI actions off Node 20
- `ci.yml`: `actions/checkout@v4 → @v6` and `astral-sh/setup-uv@v5 → @v7` (their latest
  bare-major tags, on Node 24; setup-uv has no `v8` moving tag) ahead of GitHub's 2026-06-16
  forced Node-24 cutover, clearing
  the Node-20 deprecation warning flagged in HS-2. Versions only — gate steps, the `uv`
  `version: "0.11"` pin, concurrency, and permissions unchanged. Verified by the PR's own
  green CI run on the bumped versions.

## Corrections

### Docs — the soap-journal relationship (2026-06-05, PR #24)
- **Correction:** the README claimed soap-journal *and* soap-journal-mobile "consume" / are
  "built on top of" Concord's API surface. Both claims were false and are now fixed. **Why:**
  soap-journal-mobile is offline-first and used anywhere, so a phone off the home LAN cannot
  reach Concord's LAN-only self-hosted server — a categorical mismatch; it's removed as a
  consumer entirely (noted only as independent of the LAN server). soap-journal (desktop) is the
  app Concord is *designed to build on*, but that integration **is not yet built** — so the docs
  now use intent language ("designed to build on"), not a finished "consumes this surface". The
  curious-reader pointer toward soap-journal stays. (The `bible-core` in-process-linking mentions
  in `docs/SPEC.md` / `docs/v2/SPEC.md` / `CLAUDE.md` were already future-framed and untouched.)

### API — `Vary: Origin` on cacheable responses (2026-06-06)
- **Correction:** cacheable responses carried `ETag` + `Cache-Control: …immutable` but **no
  `Vary` header**, a cross-origin cache-poisoning bug surfaced by `concord-tutorial-web`.
  **Mechanism:** Starlette's `CORSMiddleware` (`allow_origins=["*"]`, credentials off) adds
  `Access-Control-Allow-Origin` *only* when the request carries an `Origin` header. So a
  top-level browser navigation (no `Origin`) hard-caches a copy with **no `ACAO`** for a year;
  a later cross-origin `fetch()` of the same URL — with no `Vary: Origin` to mark the response
  origin-dependent — reuses that cached copy, and the browser's CORS check fails even though the
  server and CORS config are correct. Bites any consumer that visits a URL directly then fetches
  it cross-origin (tutorial; songbird/soap-journal exposed too).
- **Fix:** one line — added `"Vary": "Origin"` to the `headers` dict in
  `cached_json_response` (`bible-api/.../caching.py`), the single place that serves immutable
  responses, so it covers **every** cacheable endpoint and **both** the 200 and 304 paths.
  `/random` (`no_store_json_response`, uncached) is unaffected. **CORS posture unchanged** —
  still `*`, credentials off; this is cache-correctness, not a policy change. No ADR (correctness
  fix). `docs/SECURITY.md` CORS section gains a one-line note.
- **Tests:** `test_cors_cache_vary.py` asserts `Vary: Origin` on the 200 and on the 304
  (If-None-Match) path, and documents that an `Origin`-bearing request still gets
  `ACAO: *`. Red on `main` (200 + 304), green after the one-liner. Full fast gate clean.

## v4 — Translator's notes

### Slice V4-S1 — Notes storage + ingest + licensing safety
- **Date:** 2026-06-06. **PR:** _(this PR)_ (`v4/slice-1-notes-storage`).
- **What landed:** the additive `translator_notes` + `note_cross_references` tables + the
  `notes_fts` FTS5 mirror in `bible.db` (owned by `bible-core`, existing tables untouched); the
  build-time `bible_core.notes` loader ingesting **user-supplied notes JSON from
  `data/private/notes/`**; the licensing-safety proof (clean build → zero notes) + the
  dual-ignore regression guard; synthetic-fixture tests; and the docs/licensing
  (`THIRD_PARTY_NOTICES`, `data/SOURCES.md`, `docs/v4/notes-ingest.md`). **No endpoint** (Slice
  2). Notes bake into `bible.db` via the existing build flow (the cross-references / geography
  precedent) — **no Dockerfile change** (`COPY data/ data/` + a default `notes_dir` in `main()`
  carry it in when present locally).
- **The four open-question resolutions (SPEC v4 §10 / Slice-1 prompt):**
  1. **JSON shape + pickup** — a **Concord-native contract** (documented in
     `docs/v4/notes-ingest.md`), one file per translation at **`data/private/notes/<CODE>.json`**.
     The pickup dir is a **subdirectory** of `data/private/`, so the non-recursive translation
     scanner (`discover_files` globs `data/private/*.json`) never sees it — a notes file is never
     mistaken for a translation (a flat `data/private/notes.json` would have been parsed as one
     and failed).
  2. **FTS** — built the `notes_fts` table + rebuild **now** (the cheap `verses_fts`
     external-content pattern); the search *endpoint* is deferred to the search slice. Slice-2
     search will JOIN `notes_fts.rowid = translator_notes.id` to filter by translation/type.
  3. **Parser home** — **deferred.** The MIT NET parser lives in an external repo
     (`kbennett2000/net-bible-study`) not in this workspace; per Kris's answer this slice is
     capability-first — it documents the parse step + the target JSON contract + intended home,
     and the actual port is a follow-up. (Diverges from the Slice-1 prompt's lean; flagged and
     approved in planning.)
  4. **Verse anchor** — **canonical coordinates** (`book_id` FK to `books` + `chapter` + `verse`)
     plus `translation_id`, **no `verses.id` FK** — matching `cross_references` / `place_verses`.
     Notes are translation-specific because `char_offset` indexes into *that* translation's text.
- **How "the image ships no notes" is proven:** two tests. (1)
  `test_notes_loader.test_clean_build_with_no_private_data_yields_zero_notes` — a build with no
  `notes_dir` bakes zero notes / cross-refs (exactly the Docker build, whose context excludes
  `data/private/`). (2) `test_licensing_safety` — `data/private/` stays in **both** `.gitignore`
  and `.dockerignore` (the dual-ignore invariant; the only barrier in front of the broad
  `COPY data/ data/`). Also confirmed live: `python -m bible_core.loader` on the real corpus
  (with the 4 private translations present but no `data/private/notes/`) reports **0 notes,
  0 note cross-references**. **No new ignore path needed** — `data/private/notes/` is already
  under the covered `data/private/`.
- **Loader details:** ids assigned deterministically (files in sorted-path order, notes in array
  order) → idempotent / byte-identical rebuilds. Loud `LoaderError` on unknown translation,
  unknown book, bad note type, empty text, negative `char_offset`, invalid JSON. Default
  `ordinal` = 1-based position among a verse's notes; `note_type` nullable (CHECK-constrained set
  `tn`/`sn`/`tc`/`map`/`other`). Same loader↔module import-cycle break as geo (local import of
  `notes` inside `build_database`; `notes` imports `LoaderError` from `loader`).
- **CI is licensing-clean:** every test uses tiny synthetic fixtures (`noteskit.py`); none
  depends on the copyrighted NET data (gitignored — CI never has it). `make check` green; full
  fast suite 451 passed. v1/v2/v3 behavior unchanged (additive tables only).

### Slice V4-S2 — Notes read endpoint
- **Date:** 2026-06-06. **PR:** _(this PR)_ (`v4/slice-2-notes-endpoint`).
- **What landed:** the passage-read endpoint `GET /v1/translations/{translation}/notes/{book}/{chapter}`
  (+ optional `?verse`) serving the notes S1 baked — `get_notes` query (`NoteRow`/`NoteCrossRefRow`)
  in `bible_core.queries`, the `TranslatorNote`/`NoteCrossReference`/`NotesResponse` Pydantic models,
  the router endpoint, synthetic-fixture tests, and the SPEC §5 resolutions. **No schema change**
  (serves what S1 baked); mirrors the `/cross-references` endpoint. No FTS search, no parser, no
  songbird.
- **Open-question resolutions (SPEC §5):**
  1. **Response shape** — flat `notes` list, each with its canonical anchor + a `reference`
     string, `type`/`text`/`char_offset`/`marker`/`ordinal`, and nested `cross_references` (target
     canonical coords + nullable range + `reference`). Top level echoes
     `translation`/`book`/`chapter`/`verse`/`total`. Mirrors the `CrossRef*` shape.
  2. **`?verse`** — chapter in path, optional `?verse` query (`Query(ge=1)`); present narrows to
     that verse, a valid-but-absent verse → empty 200, a non-positive verse → 422.
  3. **Empty / out-of-range** — only unknown *translation* (404) or unknown *book* (404, matching
     the chapter read) errors; a valid book+chapter/verse with no notes → empty 200 (notes are an
     overlay, like `/verses/{ref}/places` — no verse-range validation).
  4. **Attachment** — flat list with per-note anchor (simplest for a client placing markers),
     ordered `verse` → `ordinal` → id. Unpaginated (a chapter's notes are bounded — mirrors
     `get_places_for_reference`).
- **Public-image correctness (load-bearing):** a known translation with **no notes returns 200 +
  empty list**, not 404 — so the endpoint is correct on the notes-free published image. Proven by
  `test_known_translation_no_notes_is_empty_200` (WEB is loaded but has zero notes in the fixture).
  Unknown translation → 404 `unknown_translation`; unknown book → 404 `unknown_book`.
- **Tests:** extended `apikit.build_corpus` with synthetic KJV notes (WEB deliberately has none);
  `test_notes_endpoint.py` covers chapter read + ordering, `?verse` narrowing, the cross-ref shape
  (nullable end + range + reference strings), the empty/unknown split, case-insensitive
  translation path, and the immutable-ETag 304. CI uses only synthetic fixtures — no NET data.
  `make check` green; full fast suite **465 passed**. v1/v2/v3 + v4 S1 unchanged.

### Tooling — soap-journal → Concord notes converter
- **Date:** 2026-06-06. **Script:** `scripts/convert_net_notes.py`.
- **What it does:** reshapes a soap-journal *translation* file (footnotes nested under
  `books[].chapters[].footnotes[]`) into Concord's flat v4 notes contract
  (`{"translation": "<CODE>", "notes": [...]}` at `data/private/notes/<CODE>.json`). The field
  vocabulary already matches (SPEC §4 mirrored soap-journal), so it's a mechanical reshape:
  flatten the footnotes to a flat `notes[]`; inject the canonical anchor (`book` from the
  enclosing `abbreviation`, `chapter` from the enclosing `number`); rename `verse_number`→`verse`,
  `note_type`→`type`, `cross_refs`→`cross_references` (and within each, `to_*`→`*`); stringify the
  int `marker` (the loader requires string|null); and map cross-ref `to_book_order_index` → a book
  token via the file's own `order_index → abbreviation`. Skips-and-counts empty-text /
  bad-verse / unknown-xref-book entries so the emitted file is guaranteed loadable.
- **Verified on the real NET data (local):** emits **58,253 notes + 16,167 note cross-references**
  (matches SPEC §4), loads via `python -m bible_core.loader` with no `LoaderError`, and serves
  through `/v1/translations/NET/notes/{book}/{chapter}`.
- **Licensing:** the converter is copyright-free transform logic (no embedded NET text), distinct
  from the deferred MIT PDF parser. Its **output** `data/private/notes/NET.json` is restricted,
  **generated locally and never committed or shipped** — it sits under `data/private/`, excluded by
  **both** `.gitignore` and `.dockerignore` (the dual-ignore invariant, SPEC v4 §2). Proven both
  ways: the `.dockerignore` `data/private/` rule, and an empirical busybox build of the
  post-`.dockerignore` context (`COPY . /ctx` + `find … NET.json -o net.json`) that returned
  nothing — confirming the restricted notes never enter the build context or the baked `bible.db`.

### Release — v1.0.1 (Vary: Origin CORS fix)
- **Date:** 2026-06-06. v1.0.1 — Vary: Origin CORS cache-poisoning fix (surfaced by
  concord-tutorial-web); first patch release. Bumped bible-api `__version__`/pyproject
  `1.0.0 → 1.0.1` (the OpenAPI version shown at `/docs`; refreshed `uv.lock`). The underlying
  fix is logged above (`### API — Vary: Origin on cacheable responses`); tag/publish is a
  separate manual trigger (`publish-image.yml` on `v*`), not part of this prep.

### Release — v1.0.2 (corrects mis-tagged v1.0.1)
- **Date:** 2026-06-06. v1.0.2 supersedes a mis-tagged v1.0.1: the `v1.0.1` tag landed on the
  pre-bump commit (tree still read 1.0.0) before the version bump merged, so the tag and
  in-code version disagreed. Bumped bible-api `__version__`/pyproject `1.0.1 → 1.0.2` to match
  the intended release tag (refreshed `uv.lock`). The CORS fix is present in both tags.

## Hardening + honesty pass

### Semantic-endpoint wall-clock deadline (ADR-0002)
- **Date:** 2026-06-07. Closes the gap ADR-0001 left open (risk 2 — *one slow inference*): the
  cap bounded how *many* inferences run, nothing bounded how *long* one runs, so on a no-proxy
  `make run` / `docker compose` deploy a caller could hang for seconds. Adds a server-side
  deadline `CONCORD_SEMANTIC_TIMEOUT_S` (config.py, float, **default 10s**, `0` disables) → on
  breach, **503 `semantic_timeout` + `Retry-After: 1`** in the standard envelope.
- **The load-bearing trick (honors ADR-0001):** the inference runs in a per-app
  `ThreadPoolExecutor`; the handler waits with `future.result(timeout=T)`, but the concurrency
  **permit is released by the worker, never the handler** (new `_run_inference` helper). So a
  timed-out *zombie* inference keeps holding its slot until it actually finishes — the deadline
  bounds *caller wait*, the cap still bounds *CPU*, and they never decouple (a retry after a
  timeout hits a full cap → `semantic_busy`). This is precisely the "soft timeout is harmful"
  failure mode ADR-0001 warned about, avoided by *not* releasing early.
- **Sharp edge:** `max_workers` is pinned to the cap. Acquire-before-submit means a request
  with no permit is shed before it can submit, so in-flight workers can never exceed the cap —
  executor depth tracks the cap with no unbounded thread growth under a timeout storm.
- **503 not 504:** Concord is the origin doing its own compute, not a gateway awaiting an
  upstream; a breach is the same "overloaded, retry shortly" condition as `semantic_busy`, so
  503 keeps client backoff uniform. Distinct `code` keeps the two separable in logs.
- **Inert paths preserved byte-for-byte:** cap off → inline, no deadline; timeout `0` → ADR-0001
  synchronous `acquire→run→release`; semantic disabled → `semantic_unavailable` before any of it.
  Executor created only when cap on **and** timeout > 0; shut down in `lifespan` (`wait=False,
  cancel_futures=True`). bible-semantic untouched (stays pure/web-free).
- **Tests** (`test_semantic_timeout.py`): deterministic via a blocking callable on a
  `threading.Event` the test controls (work never completes → any positive deadline fires) —
  no sleeps/races. Covers the 503 envelope, the **cap-coupling proof** (zombie holds permit →
  concurrent request shed `semantic_busy` → succeeds only after the worker drains), timeout-0
  and cap-0 inert. Docs synced same PR: README Security + Configuration, `.env.example`,
  docs/SECURITY.md (the "one slow request" bullet flips from "your concern only" to "partly the
  app's, proxy read-timeout as defense-in-depth"), ADR-0002 Accepted. `make check` green.

### Notes-endpoint honesty
- **Date:** 2026-06-07. `GET /v1/translations/{translation}/notes/{book}/{chapter}` is fully
  wired and live, but the public image ships **zero** notes (notes are user-supplied; the richest
  source, NET, is copyrighted), so for almost every operator it always returns `200` with an empty
  list. That read as broken without being stated. Made it explicit: README "What Concord doesn't do
  (yet)" gains a notes item, and docs/API.md's existing empty-200 callout now also explains *how to
  supply your own* (the `data/private/notes/` pattern + `make build-db`).
- Added `examples/notes-sample.json` — a minimal, committed example of the file shape (KJV anchor,
  two note types + a null-type plain footnote, a cross-reference). Synthetic illustrative content,
  not real notes; lives outside the gitignored `data/private/`. **Verified loadable** via the real
  loader (`bible_core.notes.parse_notes_file` → 3 notes, 2 cross-references). Docs-only otherwise;
  `make check` green.

### In-process embedding reference example
- **Date:** 2026-06-07. `bible-core`'s headline — zero web deps, embeddable in-process — had no
  consumer in the tree. Added `examples/embed_in_process.py`: opens a built `bible.db`, parses a
  reference, and fetches a verse using **only `bible_core`** (read-only conn → `SqliteBookResolver`
  → `parse_reference` → `get_verse_text`), no FastAPI/Uvicorn/socket. It then *optionally* runs a
  `bible_semantic` query — `bible_semantic` is imported **lazily inside the function, guarded by
  `try/except ImportError`**, and returns `None` (caller skips, exit 0) if the package, the ONNX
  model (`FileNotFoundError`), or the vector store (`StoreError`) is absent. So the core path is
  genuinely web-free *and* semantic-free at import time.
- **Smoke test** lives in `bible-semantic/tests/` (the package that can import both `bible_core`
  and `bible_semantic` without dragging in the web layer). It builds a tiny one-translation
  `bible.db` via the public `bible_core.loader.build_database` (inline JSON — the test kits aren't
  importable across package test dirs), loads the example by path with `importlib`, and asserts the
  fetch returns the expected text. The semantic skip is made **deterministic** by pointing
  `CONCORD_EMBEDDINGS_PATH` at a missing file → `StoreError` → `None`, so it holds whether or not a
  real store/model is present locally. The real embedding path is an `@pytest.mark.integration`
  test with the standard store+model skip-guard. README "Embedding in-process" bullet now points at
  the example. `make check` green.

### Published /v1 OpenAPI contract artifact
- **Date:** 2026-06-07. The producer half of the two-repo contract with songbird: the
  FastAPI-generated OpenAPI schema is now committed at `docs/openapi.json`, with a CI drift check
  so a response-shape change can't merge without regenerating the artifact.
- `scripts/dump_openapi.py` builds the schema via `create_app(enable_semantic=False)` — DB- and
  model-free (the lifespan that opens `bible.db` runs only on startup, not on construction) and
  all routes register unconditionally, so the schema is the full surface even in CI with no
  `bible.db` / model. Rendered **deterministically** (`json.dumps(indent=2, sort_keys=True)` +
  trailing newline) so the committed file diffs cleanly; verified byte-stable across re-runs.
  `info.version` flows from `bible_api.__version__` (currently 1.0.2) → the artifact is versioned
  with the release for free, and a version bump that isn't regenerated fails the check.
- `make openapi` regenerates; `make openapi-check` (script `--check`, exit 1 on drift) is folded
  into `make check` **and** added as an explicit CI step for a clear failure label. Verified the
  check fails on a stale artifact and passes after `make openapi`. API.md points at the committed
  schema. `make check` green.

## v5 — Search completeness

### Slice V5-S1 — Notes keyword search
- **Date:** 2026-06-07. **PR:** _(this PR)_ (`v5/slice-1-notes-search`).
- **What landed:** `GET /v1/notes/search` over the existing `notes_fts` mirror (built in v4-S1) —
  the direct analogue of `/v1/search`. **Purely additive**: one new route + two response models,
  **no schema change**. `bible_core.queries.search_notes` (+ `NoteSearchHit`/`NoteSearchPage`)
  reuses `search_verses`' FTS5 shape — `snippet()`, the `SEARCH_MARK_*` markers, the
  `OperationalError → SearchQueryError` mapping — over `JOIN notes_fts.rowid = translator_notes.id`,
  relevance-ranked with the canonical tiebreak **extended by `ordinal, id`** so multi-note verses
  page deterministically. `bible-api` adds `NoteSearchHit`/`NoteSearchResponse` and the endpoint
  (`q`, optional `translation`/`type`/`book`, `limit` 1–100, `offset` ≥0).
- **Filters & errors (the two spec open questions, resolved):** `translation` is an *optional
  filter* here (omit ⇒ all translations), not `/search`'s defaulted single selector, so it
  validates-without-defaulting — **unknown `translation` → 404 `unknown_translation`** (shared
  casing, consistent with every translation param). **Unknown `type` → 400 `unknown_type`** (closed
  enum `NOTE_TYPES`, reusing `PlaceFilterError` like `/places` status). Unknown `book` → 400
  `unknown_book` (as `/search`). Malformed `q` → 400 `invalid_search_query`. **Honest empty:** no
  notes loaded (the public image) or zero matches → 200 `total:0 hits:[]`, never 404.
- **Cross-references omitted** from search hits (spec's lean default) — fetch the full note via the
  passage read. Confirmed in the hit-key-list test.
- **Test-corpus fix (load-bearing):** `bible-api/tests/apikit.py` seeded notes but rebuilt only
  `verses_fts`, never `notes_fts` (so the mirror was empty in tests). Added the
  `INSERT INTO notes_fts(notes_fts) VALUES('rebuild')` rebuild, mirroring the real loader
  (`bible_core.notes`). Also added a synthetic identical-body note pair (GEN 2:1 + 1JN 1:1) so the
  cross-book canonical tiebreak is observable — placed in chapters no v4 notes-read test asserts on,
  keeping those green. Synthetic only; no NET data.
- **Tests:** new `bible-core/tests/test_notes_search.py` (13: word/phrase, snippet markers, each
  filter, canonical + ordinal tiebreaks, pagination, malformed→raise) and
  `bible-api/tests/test_notes_search_endpoint.py` (21: matching, filters incl. case-insensitive
  translation, ordering/pagination, empty splits, the unknown-filter 404/400 splits, immutable-ETag
  304, hit shape omits `cross_references`). OpenAPI regenerated (additive: the new path).
  `make check` green.

### Slice V5-S2 — Multi-translation keyword verse search
- **Date:** 2026-06-07. **PR:** _(this PR)_ (`v5/slice-2-multi-translation-search`). **ADR:**
  [ADR-0003](adr/ADR-0003-search-multi-translation-shape.md).
- **What landed:** the additive widening of `/v1/search` to search across several loaded
  translations at once, deduped by canonical verse (SPEC v5 §3). **Purely additive** — a new optional
  `translations` (plural, CSV; `*` = all loaded) param + two new optional response fields; **no
  schema/storage change** (`verses_fts` already indexes every translation). The single-translation
  path is **byte-for-byte unchanged** (`search_verses` untouched; a contract-unchanged test proves no
  new key reaches the wire when `translations` is absent).
- **Result model:** one hit per canonical verse that matched in ≥1 searched translation, carrying a
  `matches: {TRANSLATION: snippet}` map; ranked by **max** per-verse relevance (`MIN(f.rank)`, FTS5
  rank is lower-is-better) + canonical tiebreak; `total` = distinct matching verses. The flat
  `snippet` echoes the top-ranked translation's snippet (old clients still get one); response-level
  `translation` is the primary (first resolved id, still a required non-null string).
- **Dedup vs pagination → two queries** (`bible_core.queries.search_verses_multi`, the `get_notes`
  precedent): query 1 groups to canonical verses + paginates (`GROUP BY book/chapter/verse`,
  `ORDER BY MIN(rank), canonical_order, …`, `LIMIT/OFFSET`); query 2 hydrates `matches` for only that
  page's verses via SQLite **row-value `IN (VALUES …)`**. Snippet work bounded by
  `limit × |translations|` — no per-verse fan-out.
- **Byte-identity mechanism:** the new `SearchHit.matches` / `SearchResponse.translations` fields are
  optional (`None`) and dropped from the JSON by a surgical `@model_serializer(mode="wrap")` that pops
  **only** the new key when null — so the legacy `book: null` and every other byte are untouched
  (a blanket `exclude_none` would have wrongly dropped `book`). See ADR-0003.
- **Errors/dispatch:** unknown id → 404 `unknown_translation` (shared `resolve_translations`);
  malformed `q` → 400 `invalid_search_query`; empty → 200 empty; `translations` blank → the legacy
  single path; if both `translation=`/`translations=` given, `translations` wins.
- **Tests (synthetic only):** new `bible-core/tests/test_search_multi.py` (12) and
  `bible-api/tests/test_search_multi_endpoint.py` (17, incl. the contract-unchanged proof, dedup, the
  WEB-omits-JHN-3:16 asymmetry, max-relevance ordering, pagination over verses, `*`=all, 404/400,
  immutable-ETag 304). OpenAPI regenerated (additive: the new `translations` query param).
  `make check` green.

### Release v1.1.0
- **Date:** 2026-06-07. **PR:** _(this PR)_ (`chore/release-v1.1.0`).
- **What shipped:** the first minor since v1.0.2, packaging the merged-but-unreleased v5 search work.
  v1.1.0 adds **notes keyword search** (`GET /v1/notes/search`, V5-S1) and **multi-translation
  keyword verse search** (`GET /v1/search?translations=`, V5-S2). Both are **purely additive to
  `/v1`** — new endpoint / new optional param, no change to any existing response shape — hence a
  **semver minor**, not a patch.
- **Mechanics:** bumped `bible_api.__version__` `1.0.2 → 1.1.0` (`bible_core.__version__` left as-is);
  regenerated `docs/openapi.json` via `make openapi` (only `info.version` moved — the V5 PRs already
  landed the new paths/param); README published-image examples (`docker pull`/`docker run … :v1.0.2`)
  → `:v1.1.0` (local-build `concord:latest` examples untouched). `make check` green.
- **Not in this release:** notes *semantic* search (v5-S3) — deferred, not in the code. v1.1.0 is
  keyword search only.
- **Post-merge (Kris):** push the `v1.1.0` tag to trigger `publish-image.yml`, building/pushing
  `ghcr.io/kbennett2000/concord:v1.1.0` (+ `:latest` + `:sha-…`).

## Roadmap — ship WEB's public-domain footnotes

### Slice A — public notes path mechanism (ADR-0004)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/A-public-notes-path`).
- **Why:** v4 made notes private-only — the loader scanned the single dual-ignored
  `data/private/notes/`, so the stock image shipped **zero** notes (docs/v4/SPEC.md §2). The WEB's
  own translator footnotes are **public domain** and *should* ship, but there was nowhere committed
  to put them. Roadmap item #1, step 1: add the mechanism; the real WEB data lands in Slice B.
- **What landed (mechanism only, no real data):** a second, committed, ship-by-default notes path
  **`data/notes/`** (empty `.gitkeep` this slice), scanned by the loader **alongside**
  `data/private/notes/`. `build_database`'s `notes_dir: Path | None` → **`notes_dirs:
  list[Path] | None`** (mirrors the existing `cross_ref_dirs: list[Path]`); `bible_core.notes`
  gained `discover_notes_files_in_dirs` and `load_notes` now iterates the list. `main()` passes
  `[data/notes, data/private/notes]` in that order. **Union, deterministic ids** (dir order, public
  first; sorted filename within each) — byte-identical rebuilds preserved. Same-translation-in-both
  → union (no dedup; documented). See **ADR-0004**.
- **Safety split preserved + re-tested.** `data/private/` dual-ignore **untouched**; `data/notes/`
  is **not** ignored (the point). Tests: kept `test_private_data_dir_is_ignored`; **added**
  `test_public_notes_dir_is_not_ignored` (the mirror guard — fails loudly if the public path is ever
  ignored). Evolved the behavioral proof from "clean build → zero notes" to
  **`test_clean_build_bakes_public_notes_but_zero_private_notes`** (public file present, no
  `data/private/` → public note baked, private zero). Added multi-dir union tests
  (`test_public_and_private_dirs_are_unioned_in_order`,
  `test_dropping_private_dir_removes_exactly_the_private_notes`).
- **No API/schema/contract change** — purely the build-input mechanism. `bible-core` stays web-free;
  runtime stays offline. Synthetic fixtures only. `make check` green.

## Post-v4 batch — section headings

### Slice — expose chapter section headings (ADR-0005)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/section-headings`).
- **Why:** the section headings that anchor a chapter ("The Creation", "The Beatitudes") were
  **already in the bundled translation sources** (`chapters[].headings[]`, shape
  `{"before_verse": N, "text": "..."}`, populated for 12/13 translations — only BSB has none) but
  `parse_translation_file` read each chapter and **discarded the headings array**. Pure wire-up:
  stop discarding data we already read, bake it, expose it. No new source, no parser, **no
  licensing path** (headings inherit public/private from the translation file, like verse text).
- **What landed:**
  - **core:** additive `section_headings` table + `idx_headings_anchor` (schema.py, styled like
    `translator_notes`); `HeadingRow` + `TranslationData.headings`; the chapter loop now parses
    `headings[]` tolerantly (`_opt_list`: missing/null → `[]`; loud `LoaderError` on empty text),
    `ordinal` = 1-based source array order; bulk-inserted in the existing translation transaction
    (no new `build_database` param). `BuildStats.section_headings` + the summary line report the
    count. `get_section_headings` (queries.py) mirrors `get_notes`, ordered
    `before_verse → ordinal → id`.
  - **api:** `GET /v1/translations/{translation}/headings/{book}/{chapter}` (routers.py) clones
    `notes_endpoint` — `resolve_translation` (404), `SqliteBookResolver` (404), `chapter >= 1`
    (422), shared ETag/`Cache-Control`/304. `SectionHeading` + `HeadingsResponse` (schemas.py).
    A translation/chapter with no headings → **200 `[]`** (e.g. BSB), never 404.
- **Decision (ADR-0005):** a **dedicated** endpoint (mirrors notes; leaves `/v1/chapters`
  byte-for-byte unchanged) over an additive `headings` array on `/v1/chapters`. Per-translation;
  cross-translation "canonical pericope" is interpretive and **out of scope**.
- **Tests (synthetic only):** `bible-core/tests/test_section_headings_loader.py` (anchor + order,
  ordinal = source order even when two headings share a `before_verse`, chapter/translation with
  none → 0, idempotent rebuild); `bible-api/tests/test_headings_endpoint.py` (ordered read, shape,
  empty-200 for a heading-less translation/chapter, 404/422, ETag 304). `loaderkit` gained a
  `heading()` builder + `chapter(..., headings=)`; `apikit` seeds WEB JHN 3 (two) + KJV GEN 1 (one),
  YLT none. OpenAPI regenerated (additive: one new path). `make check` green.
- **Live check:** real build reports the headings count in the summary; `get_section_headings` for a
  real chapter returns the expected titles at the right `before_verse`; BSB → empty.

### Slice — topical Bible (ADR-0006)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/topical-bible`).
- **Why:** add a browsable, bi-directional topical Bible (topics → curated verse lists; verse →
  the topics it appears under). Structurally **the geography/places feature again**, so it was
  cloned end-to-end rather than designed anew.
- **Source:** Nave's Topical Bible (Orville J. Nave, 1897, **public domain**) via
  BradyStephenson/bible-data `NavesTopicalDictionary.csv` (**CC BY 4.0** compilation — same
  treatment as the OpenBible cross-ref/geography data). 5,319 topics; the CSV `entry` column carries
  refs in prose using USFM-style codes.
- **What landed:**
  - **core:** additive `topics` + `topic_verses` tables + `idx_topic_verses_bcv` (schema.py, cloning
    `places`/`place_verses`); `bible_core.topics.load_topics` (cloning `geo.load_places`), wired into
    `build_database(topics_dir=…)`; `main()` scans `data/topics`; `BuildStats.topics`/`topic_verses`
    + summary line. `queries.py` adds `TopicRow`/`TopicPage`/`TopicVerseRef` + `list_topics`/
    `get_topic`/`count_topic_verses`/`get_topic_verses`/`get_topics_for_reference` (cloning the place
    queries, reusing `_span_predicate` + `get_verse_text`).
  - **data/parser:** `scripts/convert_naves_topics.py` (sibling to `convert_web_footnotes.py`)
    extracts **verse-level** refs into committed `data/topics/naves.json` (5,319 topics, 586
    redirects, 138,138 links). Book codes resolve via the canonical-books alias table (+ a tiny
    `1JHN→1JN` override family); chapter-only/cross-chapter/prose tokens skipped + counted (only 188
    unresolved, all the prose words "So"/"with"). Deterministic (byte-identical re-run). Raw CSV
    not committed.
  - **api:** `GET /v1/topics` (q/section filters, pagination), `/v1/topics/{id}` (detail +
    verse_count + see_also), `/v1/topics/{id}/verses` (include_text + translation + pagination),
    `/v1/verses/{ref}/topics` (reverse) — cloning the place endpoints; `UnknownTopicError` → 404
    `unknown_topic`. Topic*/Verse* Pydantic models clone the Place* ones.
- **Decisions (ADR-0006):** **flat** topics (Nave's sub-headings flattened into one verse union);
  "See X" redirects → a `see_also` pointer with **0 verses** (faithful; `q=anxiety` finds ANXIETY →
  `see_also: care`, and the verses live under CARE). Hierarchical sub-topics, multi-source merging,
  and chapter-level links deferred.
- **Tests (synthetic only):** `bible-core/tests/test_topics_loader.py` (counts, PK dedup, skipped
  unresolved link, redirect 0-verses, both directions, ordering, idempotent); `bible-api/tests/
  test_topics_endpoint.py` (browse/filters/pagination, detail, include_text true/false + missing-
  verse null, redirect empty, reverse union, 404 unknown_topic, 400/404 ref errors, ETag 304).
  `apikit` seeds CARE/CREATION/LOVE + an ANXIETY redirect. OpenAPI regenerated (4 additive paths).
- **Live check:** real build → 5,319 topics / 138,138 topic-verse links; `q=anxiety` →
  ANXIETY (`see_also: care`); CARE carries Phil 4:6; `/verses/Phil 4:6/topics` → CARE, COMMANDMENTS,
  PRAYER, THANKFULNESS, TROUBLE. `make check` green.

## v6 — word study (Strong's lexicon, original-language texts & tagged tokens)

Designed in [`docs/v6/SPEC.md`](v6/SPEC.md); architecture in
[`docs/adr/ADR-0007-word-study.md`](adr/ADR-0007-word-study.md). All-STEPBible-Data (CC BY 4.0),
Greek-NT-first (S1–S4), Hebrew OT last (S5). **Naming:** "v5" was already taken by *search
completeness* — this milestone is **v6**.

### Slice V6-S1 — Greek NT as a translation (ADR-0007)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/v6-s1-greek-nt`).
- **Why:** the original-language word-study feature loads each OL text **as an ordinary
  translation** so it rides the existing `/v1/verses` + `/v1/translations` machinery. The Greek NT
  goes first because its NRSV chapter counts match the standard English NT, so it loads with **no
  schema and no loader changes** — proving the "OL as a translation" idea before the additive
  lexicon/token tables land in S2–S4.
- **What landed:**
  - **data/parser:** `scripts/convert_step_tagnt.py` reads STEPBible's `TAGNT` (Translators
    Amalgamated Greek NT), keeps the **SBL-edition** words (the `editions` column contains `SBL`),
    strips the transliteration parenthetical, **NFC-normalizes**, and joins each verse's words in
    `#word-index` order into `data/translations/SBLGNT.json` (27 books, **7,917 verses, 137,121 SBL
    words**; 4,975 non-SBL words skipped). Book codes resolve via the canonical-books alias table
    (all 27 NT codes are seeded; no override needed). NRSV ref; alt-versification brackets
    (`{…}`/`[…]`/`(…)`) ignored. Deterministic (byte-identical re-run). Raw `TAGNT` files live under
    the new gitignored + **dockerignored** `data/original/` — re-derivable, not committed.
  - **no production-code changes:** the Greek NT loads through `parse_translation_file` /
    `build_database` unchanged; `direction` stays `ltr` (Greek is LTR), `versification` `standard`.
- **Decisions (ADR-0007):** all-STEPBible CC BY 4.0; **commit** the derived JSON (raw not
  committed); id **`SBLGNT`** = the SBL *word selection* with STEPBible's NA-based spelling (not a
  byte-faithful printed SBLGNT — `copyright` says so); **NFC** text. Collapsed-base Strong's ids,
  the lexicon/token tables, and the versification-grouping for the Hebrew OT are later slices.
- **Tests:** `bible-core/tests/test_ol_translation_loads.py` (fast/synthetic — a Greek translation
  loads beside an English one, language preserved, verse retrievable, and the chapter-count lock
  still rejects a disagreeing OL text); `test_loader_real.py` gains
  `test_real_build_loads_greek_nt_as_a_translation` (SBLGNT is NT-only, JHN 21 chapters, John 3:16
  drops the TR-only αὐτοῦ, John 5:4 absent, text is NFC). Translation-count assertions updated
  **13→14** in `test_loader_real.py` + `test_utility_real.py` (13 PD English + the Greek SBLGNT).
- **Live check:** full real build → **18 translations** (13 PD English + SBLGNT + 4 local private),
  no chapter-count conflict; SBLGNT 7,917 verses, `grc`/`ltr`; `/v1/verses/John 3:16?translation=
  SBLGNT` returns the Greek. `make check` green.

### Slice V6-S2 — Strong's lexicon (ADR-0007)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/v6-s2-strongs-lexicon`).
- **Why:** word study needs a lexicon — "what does G26 (*agapē*) mean?". This slice lands the
  additive `strongs_entries` table + the two read endpoints, mirroring the topical-Bible pattern
  (entry table + browse/detail queries + `cached_json_response` + an `Unknown…Error`). Pure SQLite
  through `bible-core` — no embeddings.
- **What landed:**
  - **data/parser:** `scripts/convert_strongs_lexicon.py` reads STEPBible's `TBESG` (Translators
    Brief lexicon of Extended Strongs for Greek; tab-separated, CC BY 4.0) → `data/strongs/
    lexicon.json` (**10,846 entries**). Each id is the eStrong column collapsed to its **base**
    (`G0026`→`G26`); where a number splits into disambiguated senses (`G0001G`/`G0001H`) the first
    wins (188 dups collapsed). HTML in the definition is stripped to plain text; the `__` indent
    markers are dropped. One extended LXX entry with an empty gloss is skipped+counted. Deterministic
    (sorted by Strong's number). Raw `TBESG` lives under the gitignored+dockerignored `data/original/`.
  - **schema/loader (`core`):** new `strongs_entries` table (PK `strongs_id`; `language`, `lemma`,
    `transliteration`, `gloss`, `definition`, `source`); new `bible_core.strongs` loader
    (`load_strongs_entries`, duplicate id → `LoaderError`); `lexicon_dir` threaded through
    `build_database`/`main` (→ `data/strongs/`) like `topics_dir`; `BuildStats.strongs_entries` +
    summary line. Transliteration is allowed empty (105 extended entries lack one); the rest required.
  - **queries (`core`):** `StrongsRow`/`StrongsPage`/`StrongsEntry` + `list_strongs(q, language,
    limit, offset)` (substring over lemma/transliteration/gloss, optional language; ordered
    **numerically** within language via `CAST(SUBSTR(strongs_id,2) AS INT)`) and `get_strongs(id)`.
  - **api:** `GET /v1/strongs` (browse) + `GET /v1/strongs/{id}` (detail, with definition);
    `UnknownStrongsError` → `404 unknown_strongs`; path id normalized (upper-case letter + drop
    leading zeros, so `g0026`/`g26`/`G26` all resolve to `G26`). Schemas `StrongsSummary`/
    `StrongsResponse`/`StrongsDetail`.
- **Tests:** `bible-core/tests/test_strongs_loader.py` (synthetic — counts, detail, empty
  transliteration allowed, `q`/`language` filter + numeric order, duplicate-id rejected, idempotent,
  missing dir → 0); `bible-api/tests/test_strongs_endpoint.py` (browse/echo/order, `q` over
  gloss+transliteration, language filter, pagination, detail shape, id normalization, 404
  `unknown_strongs`, ETag/304) seeded via `apikit`; `test_loader_real.py` gains
  `test_real_build_loads_the_strongs_lexicon` (real G26 = ἀγάπη "love").
- **Acceptance ①:** `GET /v1/strongs/G26` → ἀγάπη "love" with full definition. ✔
- **Live check:** real build → **10,846 Strong's entries**; `/v1/strongs/g0026` → `G26` ἀγάπη love;
  `/v1/strongs?q=love&language=grc` lists G25/G26/…; unknown → `404 unknown_strongs`. `make check` green.

### Slice V6-S3 — tagged word tokens (ADR-0007)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/v6-s3-word-tokens`).
- **Why:** word study needs the per-verse tagged tokens and the Strong's↔verse link — "every verse
  where G26 appears" and "the tagged words of John 3:16". This slice lands the additive `word_tokens`
  table + the two bi-directional queries in `bible-core`; the endpoints that expose them are S4.
- **What landed:**
  - **parser:** `convert_step_tagnt.py` now emits a **second** file, `data/strongs/tokens-sblgnt.json`
    (**137,121 tokens**), from the same TAGNT pass that builds `SBLGNT.json`. Each kept SBL word →
    `{book, chapter, verse, position, surface_form, strongs_id, morph_code}`. The dStrong column
    (`G0976=N-NSF`) is split into a **collapsed-base** Strong's (`G0976`→`G976`, disambiguation suffix
    dropped, `G2264G`→`G2264`) and the morph code. Deterministic; **`SBLGNT.json` re-generates
    byte-identical** (verse text unchanged).
  - **schema/loader (`core`):** new `word_tokens` table (PK `(text_id, book_id, chapter, verse,
    position)`; nullable `strongs_id`/`morph_code`; a plain `strongs_id` column, no FK) + two indexes
    (`idx_word_tokens_strongs` for Strong's→verses, `idx_word_tokens_bcv` for verse→tokens, mirroring
    place_verses). `load_word_tokens` (resolve book via alias, **skip+count** unresolved, `INSERT OR
    IGNORE` on the PK); `tokens_dir` threaded through `build_database`/`main` + `BuildStats.word_tokens`
    + summary. Lexicon and tokens **share `data/strongs/`** — the lexicon loader reads `*.json` minus
    `tokens-*`, the token loader reads `tokens-*.json`.
  - **queries (`core`):** `StrongsVerseRef`/`WordToken` + `count_strongs_verses`,
    `get_strongs_verses(strongs_id, text_id, …)` (DISTINCT verse, canonical order) and
    `get_words_for_reference(reference, text_id)` (tokens for the ref's spans, ORDER BY
    chapter/verse/position, LEFT JOIN `strongs_entries` for lemma/translit/gloss; reuses
    `_span_predicate`).
- **Tests:** `bible-core/tests/test_word_tokens_loader.py` (synthetic — counts/dedup/skip, both query
  directions, lexicon join + untagged-null tokens, empty-for-untagged-verse, idempotent, missing dir
  → 0); `test_loader_real.py` gains `test_real_build_loads_word_tokens_both_directions` (real John 3:16
  tokens in order with G25→ἀγαπάω gloss; αὐτοῦ absent from the SBL token stream).
- **Live check:** real build → **137,121 word tokens**; `get_strongs_verses("G26","SBLGNT")` → 106
  verses; `get_words_for_reference(John 3:16,"SBLGNT")` → 25 ordered tokens with glosses; Gen 1:1
  (OT, NT-only text) → empty. `make check` green (613 tests).

### Slice V6-S4 — the two remaining endpoints (ADR-0007)
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/v6-s4-strongs-endpoints`).
- **Why:** expose the S3 queries over HTTP — the concordance ("every verse where G26 appears") and
  the per-verse tagged tokens ("the Greek words of John 3:16"). **Completes the Greek word-study cut
  (acceptance ①–③).** API-only; mirrors the topical-Bible endpoints.
- **What landed:**
  - **api (`routers.py`):** `GET /v1/strongs/{id}/verses` (normalize id → 404 `unknown_strongs` if
    no lexicon entry; `?text=` selects the tagged text [default `SBLGNT`], `?translation=` +
    `include_text` hydrate the verse text via `resolve_translation`/`get_verse_text` like
    `/topics/{id}/verses`; pagination) and `GET /v1/verses/{ref}/words` (`?text=` default `SBLGNT`;
    `parse_reference` → 400/404; a valid ref with no tokens → 200 empty). Both via
    `cached_json_response`. `?text=`/`?translation=` reuse `resolve_translation` — `text or "SBLGNT"`
    makes SBLGNT the token-set default while still 404-ing a bad id. Added `DEFAULT_WORD_TEXT`.
  - **schemas:** `StrongsVerse`, `StrongsVersesResponse`, `WordTokenOut`, `VerseWordsResponse`.
    No new error types (`UnknownStrongsError` + reference/translation errors already exist).
  - **tests/corpus:** `apikit.build_corpus` now seeds the **SBLGNT** translation (grc, no synthetic
    verses needed) + a handful of `word_tokens` (JHN 3:16 with G25 / a no-entry G9999 / an untagged
    word; G26 in JHN 4:7-8). `test_strongs_endpoint.py` covers order/echo, id-normalize,
    include_text true/false, missing-text→null (WEB omits JHN 3:16), pagination, 404s, the lexicon
    join (null lemma for a no-entry token), empty-200, 400 unparseable, bad `?text=`→404, ETag/304.
    Bumped `test_healthz` (3→4) and `test_translations_endpoint` (KJV/**SBLGNT**/WEB/YLT) for the
    added Greek translation.
- **Acceptance ② & ③:** `/v1/strongs/G26/verses` → its occurrences; `/v1/verses/John 3:16/words` →
  the tagged Greek tokens. ✔
- **Live check:** real build → `/v1/strongs/G26/verses` returns 106 verses (KJV-hydrated by default);
  `?include_text=false` → null text; `/v1/verses/John 3:16/words` → 25 tokens (ἠγάπησεν → G25, gloss
  "to love"); `/v1/verses/Genesis 1:1/words` → 200 empty; unknown id → 404; bad ref → 400.
  `make check` green; `docs/openapi.json` regenerated (two new paths).

### Slice V6-S5 — the Hebrew OT (ADR-0007) — completes v6
- **Date:** 2026-06-08. **PR:** _(this PR)_ (`slice/v6-s5-hebrew-ot`).
- **Why:** extend word study to the OT — load the Hebrew OT (**OSHB**, from STEPBible's **TAHOT**) as
  an RTL translation with tagged tokens, plus the Hebrew Strong's lexicon (**TBESH**). Final v6 slice.
- **Key finding (reshaped the slice):** TAHOT references the OT in **English/NRSV versification**
  (the Masoretic ref trails in brackets, e.g. `Mal.4.6(3.24)#10=L`). Parsing the **English** primary
  ref makes OSHB's chapter counts match the English Bibles (Malachi 4, Joel 3) → the
  `_update_chapter_counts` versification-grouping relaxation that ADR-0007 earmarked for S5 turned out
  **unnecessary** (it assumed MT numbering). The only loader change is reading an optional `direction`
  for RTL. (User-approved: English/NRSV alignment; commit the derived JSON.)
- **What landed:**
  - **parser:** `scripts/convert_step_tahot.py` (new; reuses `load_book_table` from
    `convert_step_tagnt.py`) reads the 4 TAHOT files → `data/translations/OSHB.json` (39 books,
    **23,145 verses**, `language="hbo"`, `direction="rtl"`) + `data/strongs/tokens-oshb.json`
    (**305,102 tokens**). English ref parsed (bracket ignored); **verse-0 Psalm titles skipped**
    (478); surface = col1 with `/`+`\` separators removed, NFC; `strongs_id` = collapsed-base **root**
    dStrong (col8, `H0853_A`→`H853`); `morph_code` = the root element of the grammar column. Compound
    words stay whole-word (prefix/suffix sub-tokens deferred). Deterministic.
  - **lexicon:** `convert_strongs_lexicon.py` gained `--language`/`--output`; TBESH (same columns as
    TBESG) → `data/strongs/lexicon-hebrew.json` (**8,723 entries**, `hbo`). The eStrong collapse now
    drops a trailing BDB suffix letter (`H1254a`→`H1254`) so Hebrew tokens join the lexicon; Greek
    ids are bare so `lexicon.json` re-generates **byte-identical**.
  - **loader:** `parse_translation_file` reads an optional `direction` (∈ `{ltr,rtl}`, default `ltr`);
    **no `_update_chapter_counts` change**. OSHB tokens/lexicon load through the existing
    `tokens_dir`/`lexicon_dir` (both already glob `data/strongs/`). H- and G-ids don't collide.
  - **api:** `direction` added to `TranslationMeta` + `get_translations` + the `Translation` schema +
    `/v1/translations`. No new endpoints. **Smart `?text=` defaulting** (a small enhancement beyond
    the S4 `SBLGNT`-only default, so the OT works without a param): `/v1/strongs/{id}/verses` defaults
    the text by the id's language (`H…` → OSHB, else SBLGNT); `/v1/verses/{ref}/words` defaults by the
    reference's testament (OT → OSHB, NT → SBLGNT). An explicit `?text=` overrides.
  - **loaderkit:** `translation(...)` gained optional `direction`/`versification` kwargs.
- **Tests:** `test_ol_translation_loads.py` (a Hebrew `rtl` translation loads; `direction` read +
  persisted; default `ltr`; invalid direction rejected; the chapter-count lock still enforced);
  `test_loader_real.py` gains `test_real_build_loads_the_hebrew_ot` (OSHB rtl/hbo; Malachi 4 / Joel 3
  chapters; Genesis 1:1 Hebrew; H430 = אֱלֹהִים "God"; H430→Gen 1:1; Gen 1:1 → 7 tokens with root
  lemma/gloss). Translation-count assertions **14→15** (`test_loader_real`, `test_utility_real`);
  `test_translations_endpoint` asserts the `direction` field.
- **Acceptance (OT):** `/v1/strongs/H430` → אֱלֹהִים "God"; `/v1/strongs/H430/verses` → occurrences;
  `/v1/verses/Genesis 1:1/words?text=OSHB` → tagged Hebrew tokens. ✔
- **Live check:** full real build → **19 translations** (13 Eng + SBLGNT + OSHB + 4 local private),
  **19,569 Strong's entries**, **442,223 word tokens**, no chapter-count conflict. `make check` green;
  `docs/openapi.json` regenerated (`Translation` gains `direction`). **v6 complete.**
- **Data size:** `OSHB.json` ~7.4 MB, `tokens-oshb.json` ~59 MB, `lexicon-hebrew.json` ~3 MB —
  committed derived JSON (raw TAHOT/TBESH stay in the gitignored/dockerignored `data/original/`).
