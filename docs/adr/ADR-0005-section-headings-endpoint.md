# ADR-0005: A dedicated endpoint for chapter section headings

**Status:** Accepted

<!--
Records how chapter section headings (already present in the translation sources, previously
discarded by the loader) are exposed via /v1. Format mirrors ADR-0001..0004:
Context / Options / Decision / Consequences.
-->

## Context

The bundled translation JSON (`data/translations/*.json`) already carries chapter section headings —
the editorial titles that anchor a passage ("The Creation", "The Beatitudes") — as
`chapters[].headings[]` with shape `{"before_verse": N, "text": "..."}`. They are populated for 12
of 13 translations (WEB ~2,755, KJV ~2,923, …; only BSB has none). But `parse_translation_file`
reads each chapter dict and extracts only `number` + `verses` — **the headings array is silently
discarded**. So the data ships in the repo yet is invisible to API clients.

This is wire-up, not sourcing: no new parser, no new source, and **no licensing path** — headings
inherit public/private from the translation file's location, exactly like the verse text. The only
real decision is *how to expose them*.

**Scope:** whole-chapter headings keyed by translation. A cross-translation "canonical pericope"
notion (one heading set spanning translations) is interpretive and deliberately **out of scope**.

## Options considered

- **(A) A dedicated `GET /v1/translations/{translation}/headings/{book}/{chapter}` endpoint.**
  Mirrors the v4 translator-notes endpoint exactly (same URL shape — headings are
  translation-specific, like notes — same resolve/404/empty-200 rules, same ETag/caching). Leaves
  every existing endpoint byte-for-byte unchanged. **Chosen.**
- **(B) An additive `headings` array on `GET /v1/chapters/{book}/{chapter}`.** Co-locates headings
  with the verses they annotate (one round-trip to render a chapter). But `/v1/chapters` is
  multi-translation aware (`?translations=`), so headings — which are per-translation — would have
  to be nested per translation, complicating a stable, published response shape; and `/v1/chapters`
  is part of the `/v1` contract (the committed `docs/openapi.json`), so any change there carries
  contract risk for a purely additive feature. Rejected as the *default*; can still be added later
  without conflicting with (A).

## Decision

Expose headings through a **separate, dedicated endpoint**:

```
GET /v1/translations/{translation}/headings/{book}/{chapter}
```

- Storage: an additive `section_headings` table (`translation_id, book_id, chapter, before_verse,
  text, ordinal`), baked by the existing translation ingest — no new `build_database` parameter,
  no new data path. `ordinal` preserves source array order; the build stays deterministic /
  idempotent (`BuildStats.section_headings` reports the count).
- Read: `bible_core.queries.get_section_headings` returns a chapter's headings ordered
  `before_verse → ordinal → id` (mirrors `get_notes`). Empty tuple when none.
- Endpoint: clones `notes_endpoint` — `resolve_translation` (unknown → 404), `SqliteBookResolver`
  (unknown book → 404), `chapter` path param `>= 1` (422 otherwise), strong ETag + immutable
  `Cache-Control` + 304 via the shared `cached_json_response`. A known translation with no headings
  for the chapter (e.g. BSB) returns **200 with `headings: []`**, never 404 — an honest
  "this translation has no headings here" state.

## Consequences

- **No existing endpoint changes** — `/v1/chapters` and the rest stay byte-for-byte identical; the
  OpenAPI diff is one new additive path. Lowest-risk way to ship the feature.
- **The headings ride the existing translation ingest**, so public/private licensing is automatic
  (no new ignore rules, no new source) and a rebuild is byte-identical.
- **Per-translation by design.** Each translation's own editorial headings are returned as-is; no
  attempt to reconcile them into a canonical pericope set (interpretive — explicitly deferred).
- **Co-location is still open.** If a client later needs headings inline with verses, an additive
  `headings` array on `/v1/chapters` (option B) can be added on top of this without conflict.
