# ADR-0003: Multi-translation `/v1/search` response shape

**Status:** Accepted

<!--
Records the one v5 change to an existing endpoint: the additive multi-translation widening of
`/v1/search` (v5-S2, docs/v5/SPEC.md §2–§3). The §2 spec flags this as ADR-worthy because it
touches the /v1 stability promise. Format mirrors ADR-0001/0002: Context / Options / Decision /
Consequences.
-->

## Context

`/v1/search` (`search_endpoint` in
[bible-api/src/bible_api/routers.py](../../bible-api/src/bible_api/routers.py)) does FTS5 keyword
search over **one** translation. v5 widens it to search across several loaded translations at once
(`verses_fts` already indexes them all — no new storage). This is the *only* v5 change to an
existing endpoint, and `/v1` is a published stability contract (the committed `docs/openapi.json` is
a two-repo contract with songbird). So the widening must be **additive only**: a new optional
parameter plus new optional response fields, with the existing single-translation response
**byte-for-byte unchanged** when the new parameter is absent — no removed field, no changed type, no
changed default.

Two design questions had real trade-offs:

1. **Result model.** A flat row per `(verse, translation)` match returns the same canonical verse up
   to 13× with near-identical snippets — the noise the v1 SPEC named when it deferred this. How
   should multi-translation results be shaped, ranked, and counted?
2. **Additive shape.** How do the single- and multi-translation responses coexist without breaking
   the byte-for-byte guarantee, given Pydantic includes `null` fields in JSON by default?

## Options considered

**Result model.**
- *(A) Flat `(verse, translation)` rows.* Simple SQL (today's query, `IN (…)` over translations),
  but the duplicate-verse noise, and `total`/pagination over pairs rather than verses, contradict
  Concord's parallel-by-verse identity. Rejected.
- *(B) Deduped by canonical verse, with a per-translation `matches` map.* One hit per canonical
  verse that matched in ≥1 searched translation; `matches: {TRANSLATION: snippet}`; `total` = distinct
  matching verses. Matches Concord's verse identity. **Chosen.**
- Ranking within (B): *max* per-verse relevance (`MIN(f.rank)`, FTS5 rank is lower-is-better) vs sum
  of ranks vs weighting by how many translations matched. "The verse where some translation matched
  most strongly" is the intuitive order; the alternatives privilege verses by corpus coverage rather
  than match quality. **Max chosen** (spec §3).

**Additive shape.**
- *(C) A separate multi-only response model.* Zero risk to the legacy bytes, but two response schemas
  for one route and a `scope`-like fork in the handler. Since `/v1/search` returns a raw `Response`
  (not a `response_model`), neither model appears in OpenAPI anyway, so this buys nothing over (D)
  while fragmenting the model.
- *(D) One model, new fields optional (`None` default), omitted from JSON when null.* The fields live
  on the existing `SearchHit`/`SearchResponse`. The catch: a blanket `exclude_none` at dump time
  would also drop the **legacy** `book: null` (the single-mode response includes `"book": null`,
  which clients encode against), breaking byte-identity. **Chosen, with a surgical serializer** (a
  `@model_serializer(mode="wrap")` that pops *only* the new key and *only* when null), so existing
  nullable fields are untouched.

## Decision

Multi-translation search is opt-in via a new optional **`translations`** (plural, CSV; `*` = all
loaded) query parameter, mirroring `/v1/verses`. Dispatch is by presence:

- **Absent or blank** (incl. only the singular `translation=`): the unchanged path —
  `resolve_translation` → `bible_core.queries.search_verses` → today's `SearchResponse`. The new
  fields stay `None` and are omitted → **byte-for-byte the pre-v5 response**.
- **Present**: `bible_core.queries.search_verses_multi` runs across the resolved set (unknown id →
  `404 unknown_translation` via the shared `resolve_translations`; `*` expands to `sorted(loaded)`).
  Each hit gains a `matches` map; the flat `snippet` echoes the **top-ranked** translation's snippet
  (so a client reading only `snippet` still gets something sensible). Response-level `translation`
  carries the **primary** (first resolved id) — kept a required non-null string, so its type never
  changes — and a new `translations` list echoes the searched set.

Result model: one hit per canonical verse, ranked by `MIN(f.rank)` with a canonical tiebreak
(`book canonical_order`, chapter, verse); `total` = distinct matching verses.

Dedup-vs-pagination is solved with **two queries** (the `get_notes` precedent): query 1 groups to
canonical verses and applies `LIMIT/OFFSET`; query 2 hydrates `matches` for *only* that page's verses
via SQLite row-value `IN (VALUES …)`. Snippet work is bounded by `limit × |translations|` — no
per-verse fan-out.

## Consequences

- **The `/v1` contract holds.** Single-translation callers see an identical response to the byte; a
  test asserts no `matches`/`translations` key reaches the wire when `translations` is absent. The
  OpenAPI diff is one new query parameter (the response model isn't in the schema — raw `Response`).
- **`search_verses` is untouched**, which is what makes the byte-identity guarantee cheap and
  obvious: the legacy path runs literally the same code as before.
- **Slight asymmetry, accepted:** in multi mode the per-hit flat `snippet` (top-ranked, varies by
  verse) can name a different translation than the response-level `translation` (the primary
  requested). Documented in the model; the `matches` map is authoritative.
- **The serializer is surgical, not blanket** — it only ever drops the new keys when null, so it
  cannot regress other nullable fields. If more additive fields are added later they must each opt
  into the same omission explicitly (a deliberate, auditable choice over magic).
- Multi-translation **semantic** search remains out of scope: semantic matching is already
  translation-agnostic (it ranks references in WEB space), so "all translations" is meaningless for
  it (spec §3/§6).
