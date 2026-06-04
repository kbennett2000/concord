# Concord — v1 Build Spec

**Concord** is a self-hosted, LAN-first, read-only Scripture API serving multiple
public-domain translations from a single canonical source. The name carries the idea on
two axes: *concordance* (Scripture lookup and search) and *concord* (agreement across the
aligned translations). It's designed to become the backend that every other
Scripture-aware tool in the ecosystem (church LAN platform, projection tool, future
semantic search) consumes, while the hard logic lives in a standalone library that
`soap-journal` can later link in-process.

The repo is `concord`. Inside it live two packages: `bible-core` (the reusable engine,
imported in-process) and `bible-api` (the thin HTTP face). The library keeps a
descriptive name because it's imported; the repo carries the product name.

---

## 1. Goals & shape

The interesting capability here is **multiple translations aligned by book/chapter/verse**,
so the API is built around addressing any verse or range across any subset of
translations and returning them in a shape that comparison UIs can render directly.

v1 is **read-only** and **full-surface**: verse/range fetch, chapter fetch,
multi-translation parallel reads, keyword search, cross-references, plus the
metadata and utility endpoints. No write path, no auth (LAN-trusted), no Catholic
data yet (see §3).

---

## 2. Architecture — two packages, one repo

The whole point of this exercise is **dependency hygiene**, so the hard logic ships
as a standalone library with zero web dependencies, and the HTTP service is a thin
wrapper around it. Keeping these as two physically separate packages (not just two
folders in one project) enforces the boundary mechanically: nothing web-framework-
shaped can leak into the core, because the core can't import it. That is exactly the
property that lets `soap-journal` depend on `bible-core` later **without** dragging
FastAPI into a non-technical deploy.

```
concord/                        # repo root
├── CLAUDE.md                   # cc auto-loads every session
├── README.md                   # stub at init; full version in Slice 9
├── LICENSE                     # MIT — Kris Bennett, from first commit
├── .gitignore
├── .claude/
│   └── settings.local.json     # local cc settings — GITIGNORED
├── bible-core/                 # standalone package — NO web deps
│   ├── pyproject.toml
│   ├── src/bible_core/
│   │   ├── schema.py           # DDL / table definitions
│   │   ├── loader.py           # JSON → SQLite ETL (directory-scanning)
│   │   ├── parser.py           # reference parser (pure, HTTP-free)
│   │   ├── resolver.py         # BookResolver (alias → canonical book id)
│   │   ├── queries.py          # get_verses, get_chapter, search, cross_refs
│   │   └── models.py           # internal dataclasses (not Pydantic)
│   └── tests/
├── bible-api/                  # FastAPI service — depends on bible-core
│   ├── pyproject.toml          # local path dependency on ../bible-core
│   ├── src/bible_api/
│   │   ├── app.py              # FastAPI app + routers
│   │   ├── schemas.py          # Pydantic response models (→ OpenAPI)
│   │   ├── shaping.py          # parallel / grouped response shaping
│   │   └── errors.py           # error envelope, exception handlers
│   └── tests/
├── data/
│   ├── translations/           # 13 PD translation JSON — COMMITTED
│   ├── private/                # non-distributable translation JSON — GITIGNORED (local only)
│   ├── cross-references/       # cross-ref dataset — committed w/ attribution if CC-BY
│   └── SOURCES.md              # provenance + attribution (text, not the source PDFs)
├── docs/
│   ├── SPEC.md                 # this document
│   ├── canonical-books.md      # 66-book seed: USFM codes, names, testament, aliases
│   └── dev-notes.md            # appended as slices land (§11)
├── scripts/                    # build-db convenience scripts
├── Dockerfile                  # multi-stage; runs loader at build, bakes bible.db
└── docker-compose.yml
```

The built database (`bible.db`), `.env`, `data/private/`, and `.claude/settings.local.json`
are all gitignored — see Prompt 1. Source PDFs live outside the repo entirely
(archival/provenance only; the loader consumes JSON, never PDF).

`bible-core` is the eventual home of the logic currently inside `soap-journal`. It is
**not** extracted from `soap-journal` as part of this work — `soap-journal` is a
shipped app serving the exact audience we care about, and gets left untouched. The
convergence (pointing `soap-journal` at `bible-core` in-process) is a clean, separate
refactor for later, only if/when it's clearly worth it.

Stack: Python 3.11+, FastAPI + Uvicorn, Pydantic v2, stdlib `sqlite3` with FTS5,
pytest. No cache layer — the corpus is ~13 × ~31k ≈ 400k verse rows, trivially small.

---

## 3. Decisions & non-goals

**soap-journal stays as-is.** It does not become an HTTP client of this service and
gains no new runtime dependency. The shared-code story is library-in-process, deferred.

**Response default is parallel-by-verse.** One object per verse, each translation's
text nested under it — maps straight onto a table row. `?format=grouped` available for
translation-keyed output. (§7)

**Versification: best-effort, mostly-aligned for v1**, but the schema is built
versification-ready now (the `versification` column, data-driven books/aliases, a `DC`
testament value). The 13 PD translations are close enough to a common scheme that v1
does not build a cross-scheme mapping.

**Catholic Bible — one API, not two; data + mapping deferred.** A separate Catholic
API is explicitly rejected: it would duplicate the service and make Douay-next-to-KJV
comparison (the interesting thing) impossible. The split into "trivially additive" vs
"breaks downstream":

- *Additive (any time):* the 7 deuterocanonical books are just new book IDs. Existing
  clients never request them; nothing changes.
- *Breaks alignment (the real work):* Vulgate Psalm numbering offset (Douay Ps 50 =
  everyone else's Ps 51), Daniel ch. 13–14 + the Azariah splice into ch. 3, Greek
  Esther additions, and — for Douay specifically — book naming ("3 Kings" → `1KI`,
  "Paralipomenon", "Apocalypse").

Single-translation reads of a Catholic translation need **none** of this solved —
Douay Ps 50 returning the *Miserere* is correct in Douay's own scheme. Breakage is
contained to cross-translation **alignment** features, and only when one side is
Catholic. So: defer the Catholic data load **and** the scheme-to-scheme mapping to a
post-foundation slice; build the mapping only when a comparison feature demands it.
PD options are **Douay-Rheims (Challoner)** (carries all the Vulgate quirks) or
**CPDV** (modern PD, Vulgate-based, likely more conventional naming — verify its exact
numbering/naming against source before committing).

**Out of scope for v1:** writes, auth, multi-translation search (search is
single-translation), semicolon-joined multi-reference strings in the parser (e.g.
`"John 3:16; Rom 8:1"`), and any cross-scheme versification mapping.

### Operating constraints (LAN / offline / port)

These are hard design constraints, not nice-to-haves — they shape the Docker, config,
and docs slices directly.

**LAN-only, not internet-facing.** The service is never assumed to be publicly exposed.
No design choice should depend on internet reachability at runtime.

**100% offline after install/config.** The build/install phase may reach the internet
(pip, base image, dependency downloads) — that's fine, it's a one-time setup step. But
once built, a fresh boot and all runtime operation must require **zero** internet: no
CDNs, no telemetry, no analytics, no phone-home of any kind. The reproducible db is
baked into the image at build time (§10, Slice 8) specifically so a cold start needs
nothing external.

> **Offline gotcha — interactive docs.** FastAPI's `/docs` (Swagger UI) and `/redoc`
> pull their JS/CSS from a public CDN by default, so on an air-gapped box they render
> blank or broken. The docs routes must serve **self-hosted** Swagger UI / ReDoc static
> assets so `/docs` works fully offline. This is wired up in Slice 8 and is easy to miss
> until someone opens `/docs` on a box with no internet.

**Easily configurable port.** A single obvious environment variable (e.g.
`BIBLE_API_PORT`), surfaced in `docker-compose.yml` and the operator README. Port
collisions are a real concern — this box already runs ~11 services — so changing the
port must be one edit, not a code change.

**CORS for LAN browser clients.** Downstream browser apps (the church LAN platform, the
projection tool, eventually `soap-journal`) call this API from other origins on the LAN,
so cross-origin requests must be allowed. Allowed origins are env-configurable, default
permissive for LAN use.

---

## 4. Data model

`verses` carries a surrogate integer PK so the FTS5 index can use external-content
(`content='verses'`) and avoid duplicating verse text.

**`translations`**
| column | type | notes |
|---|---|---|
| `id` | TEXT PK | short code, e.g. `KJV`, `WEB`, `YLT` |
| `name` | TEXT | "King James Version" |
| `language` | TEXT | "en" |
| `direction` | TEXT | `ltr` / `rtl` — future-proofing for Hebrew/Greek |
| `versification` | TEXT | scheme tag; v1 default shared across the 13, set/verified per-translation in the loader slice |
| `attribution` | TEXT | PD notice / source |

**`books`** (data-driven — *not* a hardcoded 66-book assumption)
| column | type | notes |
|---|---|---|
| `id` | TEXT PK | USFM/Paratext code: `GEN`, `1CO`, `REV` |
| `name` | TEXT | canonical English name |
| `testament` | TEXT | `OT` / `NT` / `DC` (DC unused in v1, present for later) |
| `canonical_order` | INTEGER | for sorting |
| `chapter_count` | INTEGER | convenience metadata |

**`book_aliases`** (the parser's data-driven input)
| column | type | notes |
|---|---|---|
| `alias` | TEXT | normalized lowercase: `john`, `jn`, `jhn`, `1 john`, `1jn`, `1jo` |
| `book_id` | TEXT FK → books.id | |

v1 aliases are global. Scheme-specific aliases ("3 kings" → `1KI` only under Vulgate)
are a Catholic-slice concern — flagged, not built now.

**`verses`**
| column | type | notes |
|---|---|---|
| `id` | INTEGER PK | surrogate, for FTS external-content linkage |
| `translation_id` | TEXT FK | |
| `book_id` | TEXT FK | |
| `chapter` | INTEGER | |
| `verse` | INTEGER | |
| `text` | TEXT | |

Constraints/indexes: `UNIQUE(translation_id, book_id, chapter, verse)`;
index on `(book_id, chapter, verse)` for cross-translation fetch;
index on `(translation_id, book_id, chapter)` for chapter fetch.

**`verses_fts`** — FTS5 virtual table, `content='verses'`, `content_rowid='id'`,
indexing `text`. Built during load.

**`cross_references`**
| column | type | notes |
|---|---|---|
| `from_book_id` / `from_chapter` / `from_verse` | | source verse |
| `to_book_id` / `to_chapter` / `to_verse_start` / `to_verse_end` | | target (range) |
| `votes` | INTEGER | confidence/weight (e.g. openbible.info votes), nullable |

Index on `(from_book_id, from_chapter, from_verse)`. Cross-refs are numbered in their
source dataset's scheme (Protestant) — fine for the 13, a mapping concern alongside
Catholic.

---

## 5. Reference grammar (v1)

The parser is a pure function over a `BookResolver`; it produces a structured query
plus a normalized canonical echo string, and is tested with a fixture resolver (no DB,
no HTTP). Supported forms for a **single book**:

- Single verse — `John 3:16`
- Verse range — `John 3:16-18`
- Verse list — `John 3:16,18` / `John 3:16,18,20`
- Whole chapter — `John 3`
- Chapter range — `John 3-4` (no colon ⇒ chapters 3 through 4)
- Cross-chapter verse range — `John 3:16-4:2`
- Numbered books — `1 John`, `1John`, `1 Jn`, `I John`, `First John`
- Separators — colon or period for chapter:verse (`3:16` ≡ `3.16`)

**Out of scope (v1):** semicolon-joined multi-book reference strings. The
cross-references endpoint composes multiple single-ref lookups internally — it does
not feed `;`-strings through the public parser.

Parse failures → `400`. Well-formed but nonexistent reference (out of range in all
translations) → `404`.

---

## 6. Endpoints (all under `/v1/`)

- `GET /verses/{ref}` — single verse or range. `?translations=kjv,web,ylt`
  (omit ⇒ server default). `?format=parallel|grouped` (default `parallel`).
- `GET /chapters/{book}/{chapter}` — whole chapter, multi-translation aware via
  `?translations=`, `?format=`.
- `GET /search` — `?q=` (FTS5), `?translation=` (single; default server default),
  `?book=` filter (id or alias), `?limit=` / `?offset=`. Returns hits with verse
  reference and a highlighted snippet.
- `GET /cross-references/{ref}` — `?include_text=true` to hydrate target verse text
  in `?translation=`; `?min_votes=` filter; `?limit=`.
- `GET /random` — `?translation=`, optional `?book=` / `?testament=` constraint
  (handy for verse-of-the-day / projection).
- `GET /books` — id, name, testament, chapter_count, canonical_order.
- `GET /translations` — id, name, language, versification, attribution.
- `GET /healthz` — liveness + loaded-translation count and total verse rows for sanity.

---

## 7. Response shapes, errors, caching

**Parallel (default):**
```json
{
  "reference": "John 3:16-17",
  "translations": ["KJV", "WEB"],
  "verses": [
    {
      "book": "JHN", "chapter": 3, "verse": 16,
      "reference": "John 3:16",
      "text": { "KJV": "For God so loved...", "WEB": "For God so loved..." }
    }
  ]
}
```

**Grouped (`?format=grouped`):**
```json
{
  "reference": "John 3:16-17",
  "translations": {
    "KJV": [ { "book": "JHN", "chapter": 3, "verse": 16, "text": "..." } ],
    "WEB": [ { "book": "JHN", "chapter": 3, "verse": 16, "text": "..." } ]
  }
}
```

**Missing-verse semantics.** A verse that exists in some requested translations but is
omitted in others (critical-text omissions like Matt 17:21) returns the verse object
with `null` for the omitting translation in parallel mode (`"text": { "KJV": "...",
"WEB": null }`), so comparison UIs can show the gap. A verse out of range in *every*
requested translation → `404`.

**Error envelope** (consistent shape, FastAPI exception handlers):
```json
{ "error": { "code": "unparseable_reference", "message": "...", "detail": {} } }
```
`400` unparseable ref · `404` unknown book/verse/translation · `422` bad query params.

**Caching.** Verses are immutable: serve a strong `ETag` and
`Cache-Control: public, max-age=31536000, immutable`; honor conditional requests.

---

## 8. Loader & tooling notes

The loader is a reproducible, idempotent CLI: it **scans a data directory** for
translation JSON (rather than hardcoding a list of 13 filenames), validates shape,
populates `translations` / `books` / `book_aliases` / `verses`, and builds the FTS5
index — rebuilding `bible.db` from scratch each run. It must **validate input and fail
loudly** on malformed data.

Directory-scanning is a deliberate design choice with two payoffs: adding or removing a
translation is just adding or removing a file (no code change), and the gitignored
`data/private/` directory of non-distributable translations is picked up automatically
on local builds while never existing in the public repo. The committed `data/translations/`
holds the 13 PD translations; the filesystem *is* the manifest of what's loaded.

Two correctness notes:
- **`books` / `book_aliases` are seeded from `docs/canonical-books.md`** (Slice 1) — the
  loader does not invent reference data.
- **`chapter_count` is computed from the loaded verse data**, not hand-entered, so it
  always matches reality.

Pydantic v2 response models give the OpenAPI spec and interactive `/docs` for free.
Confirm FTS5 is compiled into the target SQLite (standard builds have it) as part of the
loader/Docker slice.

---

## 9. Inputs needed from you (before the dependent slices)

1. **Translation JSON shape.** The loader (Slice 2) is written against your *actual*
   translation JSON from `soap-journal`. The 13 PD files go in `data/translations/`
   (committed); the 4 non-distributable files go in `data/private/` (gitignored, local
   only). Share one file so the loader's input contract and any normalization adapter
   match reality rather than a guess.
2. **Cross-reference dataset shape** (Slice 6) — confirm the format, its license/source
   (commit with attribution if CC-BY; gitignore if terms are unclear), and whether it
   carries a votes/weight field.
3. **Per-translation `versification` value** — a single shared default is fine for
   v1; confirm or override during Slice 2.

None of these block Slices 0, 1, or 3.

---

## 10. Build plan — sliced for Claude Code

Smallest reviewable, load-bearing units, PR-per-slice. Dependencies noted; the one
intentionally-larger slice is flagged with its reasoning.

| # | Slice | Package(s) | Delivers | Depends on | Review focus |
|---|---|---|---|---|---|
| 0 | Skeleton & boot | both | Two-package scaffold, path-dependency wiring, lint/format/test config, minimal dev Dockerfile + compose, configurable port (`BIBLE_API_PORT`), `/healthz` → 200 on empty DB, placeholder test | — | Boundary correct; app boots |
| 1 | Schema & reference data | core | All table DDL incl. future-proofing fields; canonical 66-book seed + `book_aliases` seed | 0 | Schema correctness; **the alias/book reference data** (review-heavy) |
| 2 | Loader (JSON → SQLite) | core | Reproducible ETL for the 13 translations, `translations` metadata, FTS5 index build; validates input; row-count + known-verse tests | 1 + JSON files | Input contract; idempotency; correctness |
| 3 | Reference parser | core | Pure parser over `BookResolver`, full §5 grammar, canonical echo, exhaustive unit tests incl. malformed inputs | 1 | Grammar edge cases (the trickiest code) |
| 4 | Core read endpoints | both | Query fns (`get_verses`, `get_chapter`) + `/verses/{ref}` & `/chapters/...`, parallel **and** grouped shaping, missing-verse semantics, error envelope, ETag/Cache-Control, Pydantic models | 2, 3 | End-to-end correctness; response shapes |
| 5 | Search endpoint | both | `/search` over the FTS5 index: query, `?book=` filter, pagination, highlighted snippets | 2, 4 | Query correctness; pagination |
| 6 | Cross-references | both | Load cross-ref dataset into `cross_references` + `/cross-references/{ref}` (`include_text`, `min_votes`, pagination) | 4 + dataset | Data load + endpoint together (self-contained feature) |
| 7 | Metadata & utility endpoints | both | `/random` (with `?book=`/`?testament=`), `/books`, `/translations`, flesh out `/healthz` | 4 | Small; `/random` constraint logic |
| 8 | Docker & deploy | both | Multi-stage Dockerfile baking `bible.db` at build, hardened compose + healthcheck, **self-hosted Swagger/ReDoc assets (offline-safe `/docs`)**, configurable CORS origins, port wired through compose, *functional operator README* (build / run / deploy on 192.168.1.62) | all | Image self-containment; **offline** start; deploy fit |
| 9 | Documentation & polish | repo | Warm, audience-aware **full README** that guides setup step by step; banner image **committed to the repo**; repo description + tags. Final pass after dev has largely stopped (§11) | 8 (functional) | Tone; completeness without overwhelm |

**Flagged combined slice — #4.** Query functions, both read endpoints, and the
parallel/grouped response shaper are proposed as one cycle rather than split. Reason:
the response-shaping logic (parallel vs grouped, the missing-verse `null` handling) is
*shared* by both endpoints and is the actual substance of the slice; splitting it
would force either duplicating the shaper across two PRs or merging a half-built
shaper, both of which create churn. Once the shaper and query functions exist, the
endpoints themselves are thin. Every other slice stays at the smallest load-bearing
unit.

**Ordering note.** Slices 2 (loader) and 3 (parser) are independent — the parser tests
on fixtures, not the live DB — and could be built in parallel. They're listed loader-
first only so there's real data on hand to sanity-check parsed references during manual
testing.

---

## 11. Documentation approach

Documentation is **deferred by design**. The full, warm README is the last slice,
written once the repo is functional and development has largely stopped — there's no
point polishing prose against a moving target. Until then, the only documentation is a
*functional operator README* (build / run / deploy) — just enough to test and stand up
each slice.

**Dev-notes convention (keep notes as we go).** As slices land, append gotchas,
non-obvious decisions, and "why it's this way" notes to `docs/dev-notes.md`. A few lines
per slice. This is the raw material for the final doc pass, so it doesn't get
reconstructed from memory months later. Low overhead, high payoff.

**Audience.** This repo's reader is *not* the non-technical church volunteer
`soap-journal` is written for. It's the **self-hoster / integrator** — someone
comfortable with Docker and a LAN — plus downstream developers consuming the API. Docs
can assume that baseline while still being warm, inviting, and step-by-step, leaving the
reader confident they can build and run this. Thorough without being overwhelming.

**Final doc pass (Slice 9) delivers:**
- A warm, professional README that walks setup start to finish and builds confidence.
- A clean, professional **banner image for the top of the README** — committed to the
  repo as a self-contained asset (never hotlinked), so the README renders correctly even
  on an offline / LAN-hosted git server. (I can produce this as a crisp SVG or PNG when
  we reach this slice.)
- A good repo **description** and **tags**.
