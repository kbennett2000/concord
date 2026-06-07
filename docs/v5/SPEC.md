# Concord v5 — Search Completeness (design spec)

Concord's search surface is half-built. Keyword search (`/v1/search`) hits **one** translation
at a time; semantic search (`/v1/semantic-search`) covers verses only; and the translator's-notes
corpus (v4) is stored with an FTS mirror (`notes_fts`) that **nothing queries yet**. v5 finishes
the surface along two axes — *corpus* (verses · notes) and *kind* (keyword · semantic) — so every
cell a caller would reasonably expect is filled.

This is **Concord v5**. v1–v4 are shipped and unchanged; every v5 change is **additive** (new
routes, plus additive-only fields on `/v1/search` — never a removed or altered v1 field, so the
`/v1` stability contract holds). Journeys / routes remains the deferred next frontier and is
**not** this work.

---

## 1. What this is (and is not)

**Is:** three capabilities that complete the 2×2 of {verses, notes} × {keyword, semantic}:

1. **Multi-translation keyword verse search** — search across *all loaded* translations at once
   (today's single-translation `/v1/search` becomes the N=1 case), deduped by canonical verse.
2. **Notes keyword search** — FTS over the existing `notes_fts`, exposed as an endpoint.
3. **Notes semantic search** — meaning-based search over note bodies (a new, licensing-gated
   embedding corpus). **Deferred behind real demand** — see §5 and §7.

**Is not:** multi-translation *semantic* search (semantic matching is already
translation-agnostic — it ranks references in WEB space and renders text in any translation, so
"all translations" is meaningless for it; §3); **cross-corpus** search (one query returning both
verses and notes in a single ranked list — the result objects differ; kept separate); a notes
*authoring* / editing path (notes are ingested — v4); the songbird UI for any of this
(presentation is a later songbird slice); journeys / routes.

## 2. The search surface — topology (the decision to ratify first)

The cells, named by **corpus in the path, kind in the leaf**:

| | keyword (FTS5) | semantic (ONNX) |
|---|---|---|
| **verses** | `GET /v1/search` *(extend → multi-translation, S2)* | `GET /v1/semantic-search` *(unchanged)* |
| **notes** | `GET /v1/notes/search` *(new — S1)* | `GET /v1/notes/semantic-search` *(new — S3, gated)* |

The verse cells stay top-level (their v1/v2 homes); the note cells live under `/v1/notes/`,
mirroring the leaf names. This is deliberately **not** a single `/v1/search?scope=verses|notes`
endpoint: verse hits and note hits are different objects with different fields, and a `scope`
enum would force a union response and muddy the OpenAPI. Parallel paths keep each response a
single clean shape — and match the existing `/v1/semantic-search` precedent (kind in the leaf).

The notes **passage-read** endpoint `GET /v1/translations/{translation}/notes/{book}/{chapter}`
(v4) is a different axis (anchor read, not content search) and is **untouched**.

> **Contract invariant (load-bearing): `/v1` is stable, so v5 only *widens*.** New endpoints are
> free. The one change to an existing endpoint — multi-translation on `/v1/search` — must be
> **additive only**: a new optional parameter plus new optional response fields, with the existing
> response **byte-for-byte unchanged when the new parameter is absent**. No removed field, no
> changed type, no changed default. The committed `docs/openapi.json` diff must be additive (a new
> route + new optional fields), and `make openapi-check` must pass after regeneration.

## 3. Multi-translation keyword verse search (S2)

**Why keyword only.** Semantic search already matches on *meaning*, not words, and returns
translation-agnostic references (it embeds WEB and renders any translation via `?translation=`).
So "search across all translations" is a keyword-only idea — only literal-word search differs per
translation. `/v1/semantic-search` needs no multi-translation notion and gets none.

**The result model — deduped by canonical verse.** The naive approach (a flat row per
(verse, translation) match) returns the same verse up to 13× with near-identical snippets —
exactly the noise the v1 SPEC flagged when it deferred this. Instead the unit of result is the
**canonical verse**, consistent with Concord's parallel-by-verse identity:

- One result object per canonical verse that matched in *at least one* searched translation.
- Each carries a `matches` map: `{ "<TRANSLATION>": "<highlighted snippet>", … }` — which
  translations matched, and the match in each, in `<mark>`-tagged form (the existing
  `SEARCH_MARK_*` convention).
- Ranked by **best (max) per-verse FTS relevance** across its matching translations, with a
  canonical tiebreak (book order, chapter, verse) so `limit`/`offset` pages over *canonical
  verses* don't overlap. (Alternative aggregations — sum of ranks, or weighting by how many
  translations matched — are rejected as the default: "the verse where some translation matched
  most strongly" is the intuitive order. Confirm in planning.)
- `total` is the count of distinct matching canonical verses (not (verse, translation) pairs).

**How it stays additive on `/v1/search`.** A new optional `translations` (plural, CSV) param,
mirroring `/v1/verses`:

- **Absent** (or only the existing singular `translation=` given): **byte-for-byte today's
  behaviour and response** — single translation, flat `hits[]` each with one `snippet`, `total` =
  matches in that translation. Old clients and the existing OpenAPI path are untouched.
- **Present**: search runs across the named translations (or **all** loaded if the token is `*`),
  and each hit additionally carries the `matches` map. The flat `snippet` field is populated with
  the top-ranked translation's snippet (so a client reading only `snippet` still gets something
  sensible); the `matches` map carries the full per-translation detail. An unknown id in
  `translations` → `404 unknown_translation` (same as `/v1/verses`, via the shared resolver).

`verses_fts` already indexes every loaded translation (verified: one `lovingkindness` query spans
ASV / ERV / KJV / JPS), so **no new index or storage** — S2 is query shaping + the additive
contract, nothing more.

> **ADR-worthy:** the additive-widening of `/v1/search` touches the `/v1` stability promise. If
> the dual-shape `snippet`/`matches` interaction proves contentious in planning, capture the chosen
> shape in a short ADR (the `/v1/search` evolution) rather than only in this spec.

## 4. Notes keyword search (S1 — the shovel-ready one)

`notes_fts` exists and the loader already rebuilds it (v4-S1); only the endpoint was deferred.

**`GET /v1/notes/search`**

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — (required) | FTS5 query; same syntax as `/v1/search`, capped at `MAX_QUERY_LENGTH`. |
| `translation` | string | — (all) | Optional filter to one notes translation (e.g. `NET`). Omitted ⇒ all loaded translations' notes. |
| `type` | string | — | Optional filter: `tn`/`sn`/`tc`/`map`/`other`. |
| `book` | string | — | Optional filter; USFM id or alias. |
| `limit` | int | `20` | 1–100. |
| `offset` | int | `0` | ≥ 0. |

Backed by a JOIN `notes_fts.rowid = translator_notes.id`, filtered by the optional
translation/type/book, relevance-ranked (FTS5 `rank`) with a canonical tiebreak
(verse → ordinal → id). Each hit carries the note's **canonical anchor**
(`book`/`chapter`/`verse` + a `reference` string), `translation`, `type`, `char_offset`,
`marker`, `ordinal`, and a `<mark>`-tagged `snippet` of the note body. (The note's own
`cross_references` are **omitted** from search hits for leanness — fetch them via the passage
read; confirm in planning if you'd rather inline them.)

**Honest absence + filter errors.** On the public image (and any instance with no notes loaded)
this returns `200` with `"total": 0` and `"notes": []` — never an error. Unknown `translation` →
`404 unknown_translation` (consistent with every other translation parameter, via the shared
resolver). Unknown `type` → `400 unknown_type` (an enum filter, like `/v1/places`'s status).
FTS5 syntax errors → `400 invalid_search_query` (`detail.fts5_error`), as `/v1/search`. Immutable
caching like the other read endpoints (body-hash ETag + `Vary: Origin`).

## 5. Notes semantic search (S3 — design now, build on demand)

Meaning-based search over note bodies. Architecturally the verse-semantic pipeline with two
load-bearing differences: a **separate, licensing-gated** vector store, and a **shared** compute
budget.

**`GET /v1/notes/semantic-search`** — `q` (required), `translation` (filter, default all),
`type` (filter), `min_score`, `limit`, `include_text`. Embeds `q` with the **same granite model**,
runs the pure `cosine_top_k` over the note vectors, hydrates the matched notes by
`note_id` → `translator_notes`, and returns note hits + `score` (the §4 hit shape plus `score`).

> **LICENSING INVARIANT (load-bearing — note vectors are NET-derived, therefore restricted):**
> Note embeddings are a derivative of copyrighted "all rights reserved" NET note text. They do
> **not** become public-domain by being float vectors. They fall under the v4 dual-ignore rule
> exactly like the notes JSON: built **locally**, stored under `data/private/`, excluded by
> **both** `.gitignore` and `.dockerignore`, and **never baked into the shipped image**.
> **Concretely:** the public image's `embeddings.db` (WEB verse vectors — public domain) *does*
> ship, so note vectors **must not** go in that file. They live in a **separate**
> `data/private/note_embeddings.db` (under the already-covered `data/private/`), so the rule needs
> no new ignore path. The public image gets the **capability** (build script + endpoint),
> **never** the note vectors.

**Storage (separate store).** A new `data/private/note_embeddings.db` owned by `bible-semantic`,
mirroring `embeddings.db` but **keyed by `note_id`**:

- `note_embeddings(note_id INTEGER PRIMARY KEY, vector BLOB)`.
- `embedding_meta` extended with the corpus identity — a `corpus` discriminator (`notes`), the
  source `translation` (NET), plus the existing `model` / `model_revision` / `dim` / `precision` /
  `normalized` / `built_at`. The read-side guard refuses a model/revision/dim/precision mismatch,
  exactly as the verse store does (returning garbage similarities is worse than failing loudly).

**Build.** A `bible-core` `iter_notes(conn, translation_id, types=None)` reader (the `iter_verses`
analogue), a `bible-semantic` build path embedding note bodies in batches, and a
`scripts/build_note_embeddings.py` CLI. The build is **opt-in and local** (it reads notes that
exist only on a user's instance) and supports a `--types` filter so an operator can embed only
`tn`/`sn` and skip `tc`/`map` — see RAM below.

**Shared compute budget (reuse ADR-0001 / ADR-0002).** Note inference is ONNX forward passes on
the same CPU as verse inference, so the two share **one** budget: the notes-semantic endpoint
acquires the **same** `app.state.semantic_semaphore` and uses the **same** executor + wall-clock
deadline (`CONCORD_SEMANTIC_TIMEOUT_S`). A separate budget would let the box be saturated by 2× the
intended concurrent inferences. Over-cap / over-deadline shed with the same `semantic_busy` /
`semantic_timeout` 503s.

**Graceful absence — do NOT block startup.** Most instances (the public image, anyone without NET)
have no note store, so a missing `note_embeddings.db` must **not** make the app refuse to start
(unlike the verse store, which is always present and primed). When the note store is absent the
endpoint returns **`503` with a distinct code** (e.g. `notes_semantic_unavailable`) — the
"capability present, data not built here" state, consistent with verse-semantic's
`503 semantic_unavailable` for a disabled capability. (Empty-200 is the alternative; 503 is
recommended because this is a config/capability state, not content absence. Confirm in planning.)
A `CONCORD_NOTES_SEMANTIC_SEARCH` toggle (default on, inert without a store) mirrors the verse
toggle; `CONCORD_NOTE_EMBEDDINGS_PATH` overrides the store location (mirrors
`CONCORD_EMBEDDINGS_PATH`).

**RAM (why S3 is its own milestone, and gated).** The full NET note corpus is ~58k notes × 768
dims × 4 bytes ≈ **~180 MB** resident, on top of the ~95 MB verse matrix + the model + the ORT
arena. On the supported 2012-Optiplex baseline (~662 MB with verse-semantic on) that is real
pressure — precisely the RAM concern ADR-0001 deferred. The `tn`/`sn`-only build is the mitigation
(fewer, more semantically-meaningful vectors; text-critical/map notes search *worse* semantically
anyway, being about mechanics rather than ideas). **Recommendation: ship S1, use it on the NET
instance, and only build S3 if keyword notes search proves insufficient in practice** (CLAUDE.md
taste-and-restraint — don't build the expensive corpus on spec).

When S3 is built, add `docs/v5/note-embeddings.md` (the build + user flow, mirroring v4's
`notes-ingest.md`) and update `THIRD_PARTY_NOTICES` if needed.

## 6. Out of scope / deferred

- Multi-translation **semantic** search (semantic is already translation-agnostic; §3).
- **Cross-corpus** search (one ranked list mixing verse and note hits).
- Searching the verse-semantic corpus in non-WEB *meaning*-space (unchanged from v2: search runs
  in WEB space; `?translation=` only changes rendered text).
- Note authoring / editing (notes are ingested — v4).
- The songbird UI for any v5 endpoint.
- Journeys / routes (the standing deferred frontier).
- Shipping any NET-derived data (notes JSON or note vectors) in the public image — forbidden (§5).

## 7. Build plan — sliced for Claude Code

Smallest reviewable, load-bearing units, PR-per-slice (CLAUDE.md). S1 and S2 are independent
(notes vs verses) and could land in either order; **S1 is first** because it is the cheapest and
is dormant-safe on the public image. S3 is gated on demand.

| # | Slice | Package(s) | Delivers | Depends on |
|---|---|---|---|---|
| **V5-S1** | Notes keyword search | both | `GET /v1/notes/search` over `notes_fts` (translation/type/book filters, snippets, pagination, honest empty + filter errors); synthetic-fixture tests; OpenAPI regen | v4 (`notes_fts` exists) |
| **V5-S2** | Multi-translation keyword verse search | both | Additive `translations=` on `/v1/search`: deduped-by-verse `matches` map, max-relevance ranking; **unchanged** single-translation path; additive OpenAPI; tests for both paths + a contract-unchanged proof | — |
| **V5-S3** | Notes semantic search *(gated on demand)* | all three | Separate `data/private/note_embeddings.db` (note-id-keyed) + guard; `iter_notes` + `scripts/build_note_embeddings.py` (`--types`); `GET /v1/notes/semantic-search` sharing the semantic budget; graceful absence (no startup block, 503); `docs/v5/note-embeddings.md`; licensing-safety tests | S1 (note shape), v2 model infra |

**Spec-first per slice (CLAUDE.md):** each slice opens in Plan Mode against this spec; any new
significant decision (e.g. the `/v1/search` evolution shape if contentious, or the 503-vs-empty
notes-semantic-absence call) gets a short ADR.

## 8. Verification (licensing-safe testing)

As in v4, tests must **not** depend on copyrighted NET data (gitignored — CI never has it):

- **S1 / S2:** synthetic fixtures only — the existing test kits already build a tiny corpus with
  synthetic KJV notes (WEB deliberately has none) and multiple translations; extend them. The fast
  suite stays licensing-clean and under the integration bar; `make check` green.
- **S3:** a **tiny synthetic note-embedding store** (a handful of fake-note vectors) exercises
  build → store-guard → endpoint → the shared-budget shedding deterministically (the
  `threading.Event`-blocked-callable pattern from `test_semantic_timeout.py`), with **no** real
  model and **no** NET data. Two regression guards: a clean build produces **no**
  `note_embeddings.db` (the public-image state), and `data/private/` stays in both ignore files
  (the dual-ignore invariant). Verifying real NET note-semantic quality is a **local-only** step
  (you have the PDF/JSON), reported like v4's local NET pass — never in CI or the image.
