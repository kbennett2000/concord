# Concord API reference

Every endpoint, with real request/response examples. All examples were captured from a
running instance loaded with the 13 bundled public-domain translations.

- **Base URL:** `http://<host>:<port>` (default `http://localhost:8000`)
- **Versioning:** data endpoints live under `/v1`. That prefix is a stability contract.
- **Responses:** JSON (`application/json`). Verse text is returned exactly as stored —
  Unicode, editorial brackets (`[is]`), and punctuation are preserved untouched.

## Contents

- [Conventions](#conventions)
- [Errors](#errors)
- [`GET /v1/verses/{ref}`](#get-v1versesref)
- [`GET /v1/chapters/{book}/{chapter}`](#get-v1chaptersbookchapter)
- [`GET /v1/search`](#get-v1search)
- [`GET /v1/cross-references/{ref}`](#get-v1cross-referencesref)
- [`GET /v1/random`](#get-v1random)
- [`GET /v1/books`](#get-v1books)
- [`GET /v1/translations`](#get-v1translations)
- [`GET /healthz`](#get-healthz)
- [Reference grammar](#reference-grammar)

## Conventions

**Translation IDs** are case-insensitive on input (`kjv`, `KJV`, `Kjv` all work) and
returned upper-cased. When a translation parameter is omitted it defaults to
`CONCORD_DEFAULT_TRANSLATION` (default `KJV`; see the README → Configuration).

**Books** in filters and paths resolve from a USFM id (`JHN`) *or* an alias (`john`, `jn`,
`jhn`). Aliases are normalized (lowercased, punctuation stripped, leading ordinal folded:
`I John` → `1 John`).

**Caching.** Scripture is immutable, so every endpoint except `/random` and `/healthz`
sends a strong `ETag` and `Cache-Control: public, max-age=31536000, immutable`, and honors
`If-None-Match` with a `304 Not Modified`. `/random` is explicitly **not** cached (see its
section). `/healthz` carries no caching headers.

```bash
# ETag round-trip
$ curl -sD- -o /dev/null 'localhost:8000/v1/verses/John%203:16?translations=kjv' | grep -i etag
etag: "0da1ee58348725b2badc17a751303b8e"
$ curl -s -o /dev/null -w '%{http_code}\n' \
    -H 'If-None-Match: "0da1ee58348725b2badc17a751303b8e"' \
    'localhost:8000/v1/verses/John%203:16?translations=kjv'
304
```

## Errors

Every error uses one envelope:

```json
{ "error": { "code": "unparseable_reference", "message": "...", "detail": {} } }
```

| Code | Status | When |
|---|---|---|
| `unparseable_reference` | 400 | A reference doesn't match the grammar (e.g. `foo bar`). |
| `unknown_book` | 404 *(path)* / 400 *(filter)* | An unrecognized book. 404 when it's the resource in a path (`/verses/Hezekiah 1:1`); 400 when it's a query-param filter (`/search?book=hezekiah`). |
| `unknown_translation` | 404 | A requested translation isn't loaded. |
| `no_verses_found` | 404 | A well-formed reference matches no verse in any requested translation (e.g. `Genesis 999:1`). |
| `no_match` | 404 | `/random` filters match nothing (e.g. `book=GEN&testament=NT`). |
| `invalid_search_query` | 400 | Malformed FTS5 syntax; the SQLite message is in `detail.fts5_error`. |
| `invalid_parameter` | 422 | A query/path parameter fails validation (bad `format`, `limit` out of range, `min_votes` < 0, non-integer chapter). |

```bash
$ curl -s 'localhost:8000/v1/verses/foo%20bar'
{"error":{"code":"unparseable_reference","message":"'foo bar' is missing a chapter/verse — a reference needs at least a chapter number","detail":{}}}
```

## `GET /v1/verses/{ref}`

Fetch the verses named by `{ref}` across one or more translations.

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `ref` | path | string | — | A reference per the [grammar](#reference-grammar) (URL-encode spaces). |
| `translations` | query | CSV | default translation | e.g. `kjv,web,ylt`. |
| `format` | query | `parallel` \| `grouped` | `parallel` | Response shape. |

**Parallel** (default) — one object per verse, each translation's text nested under it; a
translation that omits a verse (a critical-text gap like Matthew 17:21) shows `null`:

```bash
$ curl -s 'localhost:8000/v1/verses/John%203:16?translations=kjv,web'
```
```json
{
  "reference": "John 3:16",
  "translations": ["KJV", "WEB"],
  "verses": [
    {
      "book": "JHN", "chapter": 3, "verse": 16,
      "reference": "John 3:16",
      "text": {
        "KJV": "For God so loved the world, that he gave his only begotten Son, that whosoever believeth in him should not perish, but have everlasting life.",
        "WEB": "For God so loved the world, that he gave his one and only Son, that whoever believes in him should not perish, but have eternal life."
      }
    }
  ]
}
```

**Grouped** (`?format=grouped`) — verses bucketed by translation:

```json
{
  "reference": "John 3:16-17",
  "translations": {
    "KJV": [
      { "book": "JHN", "chapter": 3, "verse": 16, "text": "For God so loved the world, ..." },
      { "book": "JHN", "chapter": 3, "verse": 17, "text": "For God sent not his Son ..." }
    ]
  }
}
```

**Errors:** `400 unparseable_reference` · `404 unknown_book` (e.g. `Hezekiah 1:1`) ·
`404 no_verses_found` (well-formed but no such verse, e.g. `Genesis 999:1`) ·
`404 unknown_translation` · `422 invalid_parameter` (bad `format`). **Caching:** immutable.

Note: the parser does **not** bounds-check chapter/verse numbers — `John 3:999` parses
fine; you get `404 no_verses_found` only because no translation has that verse.

## `GET /v1/chapters/{book}/{chapter}`

A whole chapter, multi-translation aware. `{book}` is a USFM id or alias; `{chapter}` is a
positive integer. `?translations=` and `?format=` work exactly as for `/verses`.

```bash
$ curl -s 'localhost:8000/v1/chapters/john/1?translations=kjv'
```
```json
{
  "reference": "John 1",
  "translations": ["KJV"],
  "verses": [
    { "book": "JHN", "chapter": 1, "verse": 1, "reference": "John 1:1",
      "text": "In the beginning was the Word, and the Word was with God, and the Word was God." },
    ...
  ]
}
```

**Errors:** `404 unknown_book` · `422 invalid_parameter` (chapter < 1 or non-integer) ·
`404 no_verses_found` (no such chapter). **Caching:** immutable.

## `GET /v1/search`

Full-text search within **one** translation (multi-translation search is out of scope for
v1). Backed by SQLite FTS5.

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — (required) | FTS5 query; see syntax below. |
| `translation` | string | default translation | Single translation. |
| `book` | string | — | Optional filter; USFM id or alias. |
| `limit` | int | `20` | 1–100. |
| `offset` | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/search?q=lamp%20unto%20my%20feet&translation=KJV&limit=2'
```
```json
{
  "query": "lamp unto my feet", "translation": "KJV", "book": null,
  "limit": 2, "offset": 0, "total": 1,
  "hits": [
    { "book": "PSA", "chapter": 119, "verse": 105, "reference": "Psalms 119:105",
      "snippet": "NUN. Thy word [is] a <mark>lamp</mark> <mark>unto</mark> <mark>my</mark> <mark>feet</mark>, and a light <mark>unto</mark> <mark>my</mark> path." }
  ]
}
```

Matched terms are wrapped in `<mark>…</mark>`. Results are relevance-ranked (FTS5 `rank`)
with a canonical tiebreak, so `limit`/`offset` pages don't overlap. `total` is the full
match count, independent of the page.

**FTS5 query syntax** (passed through to SQLite):

| Form | Example | Meaning |
|---|---|---|
| terms | `lamp feet` | implicit **AND** — both must appear |
| phrase | `"lamp unto my feet"` | exact adjacent sequence |
| prefix | `lov*` | `love`, `loved`, `loveth`, … |
| boolean | `god OR lord`, `god NOT wrath` | explicit operators (uppercase), parentheses |
| near | `NEAR(faith hope, 5)` | within N tokens |

**Empty results** return `200` with `"total": 0` and `"hits": []` — never a 404.

**Errors:** `422 invalid_parameter` (missing/empty `q`, `limit` out of 1–100) ·
`400 invalid_search_query` (malformed FTS5, e.g. an unbalanced quote — `detail.fts5_error`
carries the SQLite message) · `404 unknown_translation` · `400 unknown_book` (filter).
**Caching:** immutable.

## `GET /v1/cross-references/{ref}`

Cross-references whose *source* falls within `{ref}`, ordered by community votes
(descending) with a canonical tiebreak.

| Param | Type | Default | Notes |
|---|---|---|---|
| `ref` | path | — | A reference per the [grammar](#reference-grammar). |
| `include_text` | bool | `false` | Hydrate each target's text. |
| `translation` | string | default translation | Only consulted when `include_text=true`. |
| `min_votes` | int | `0` | ≥ 0. Filters weak/disputed links. |
| `limit` | int | `20` | 1–100. |
| `offset` | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/cross-references/John%203:16?include_text=true&translation=KJV&limit=2'
```
```json
{
  "reference": "John 3:16", "translation": "KJV", "min_votes": 0,
  "limit": 2, "offset": 0, "total": 23,
  "cross_references": [
    {
      "from": { "book": "JHN", "chapter": 3, "verse": 16, "reference": "John 3:16" },
      "to":   { "book": "ROM", "chapter": 5, "verse_start": 8, "verse_end": null, "reference": "Romans 5:8" },
      "votes": 968,
      "text": "But God commendeth his love toward us, in that, while we were yet sinners, Christ died for us."
    },
    {
      "from": { "book": "JHN", "chapter": 3, "verse": 16, "reference": "John 3:16" },
      "to":   { "book": "1JN", "chapter": 4, "verse_start": 9, "verse_end": 10, "reference": "1 John 4:9-10" },
      "votes": 684,
      "text": "In this was manifested the love of God toward us, ..."
    }
  ]
}
```

When `include_text=false` (the default), `translation` is `null` and each entry's `text` is
`null`. When `include_text=true`, `text` is the target's **start verse** in the chosen
translation, or `null` if that verse is missing there.

**Target ranges.** A target can span verses (`verse_end` set, as in `1 John 4:9-10`). The
dataset has a few hundred targets whose range crosses a chapter or book boundary; the schema
stores a single `to_chapter`, so those **655 of 344,799** are clamped to their start verse
(`verse_end: null`) — the cross-reference is preserved, pointed at the correct first verse.

**Empty results** return `200` with `"total": 0`. A source verse that exists but has no
cross-references is *not* a 404; only an out-of-range source is.

**Errors:** `400 unparseable_reference` · `404 unknown_book` · `404 no_verses_found`
(out-of-range source) · `404 unknown_translation` (with `include_text=true`) ·
`422 invalid_parameter` (`min_votes` < 0, `limit` out of range). **Caching:** immutable.

## `GET /v1/random`

One random verse, optionally constrained. Handy for verse-of-the-day / projection.

| Param | Type | Default | Notes |
|---|---|---|---|
| `translation` | string | default translation | Single translation. |
| `book` | string | — | Optional; USFM id or alias. |
| `testament` | string | — | Optional; `OT` or `NT`, case-insensitive. |

```bash
$ curl -s 'localhost:8000/v1/random?translation=KJV&testament=OT'
```
```json
{
  "translation": "KJV", "book": null, "testament": "OT",
  "verse": {
    "book": "EZK", "chapter": 34, "verse": 25, "reference": "Ezekiel 34:25",
    "text": "And I will make with them a covenant of peace, ..."
  }
}
```

**Not cached.** `/random` returns `Cache-Control: no-store` and **no `ETag`** — every call
is meant to differ. Don't build `If-None-Match` / retry logic against it.

**Errors:** `404 unknown_translation` · `400 unknown_book` (filter) · `422 invalid_parameter`
(`testament` not `ot`/`nt`) · `404 no_match` (filters intersect to nothing, e.g.
`book=GEN&testament=NT`).

## `GET /v1/books`

The 66-book catalog, in canonical order.

```bash
$ curl -s 'localhost:8000/v1/books'
```
```json
{
  "books": [
    { "id": "GEN", "name": "Genesis", "testament": "OT", "chapter_count": 50, "canonical_order": 1 },
    { "id": "EXO", "name": "Exodus",  "testament": "OT", "chapter_count": 40, "canonical_order": 2 },
    ...
  ]
}
```

`chapter_count` is computed from the loaded verse data. **Caching:** immutable.

## `GET /v1/translations`

The loaded translations, ordered by id.

```bash
$ curl -s 'localhost:8000/v1/translations'
```
```json
{
  "translations": [
    { "id": "AKJV", "name": "American King James Version", "language": "en",
      "versification": "standard", "attribution": "The American King James Version is in the public domain." },
    ...
  ]
}
```

**Caching:** immutable.

## `GET /healthz`

Liveness plus row counts. Not under `/v1`; no caching headers.

```bash
$ curl -s 'localhost:8000/healthz'
```
```json
{ "status": "ok", "translation_count": 13, "verse_count": 404889, "cross_ref_count": 344799, "book_count": 66 }
```

The Docker healthcheck treats the container as healthy when this returns 200 with
`translation_count > 0`.

## Reference grammar

`{ref}` in `/verses` and `/cross-references` accepts these forms (URL-encode spaces):

| Form | Example |
|---|---|
| Single verse | `John 3:16` |
| Verse range | `John 3:16-18` |
| Verse list | `John 3:16,18,20` |
| Whole chapter | `John 3` |
| Chapter range | `John 3-4` |
| Cross-chapter range | `John 3:16-4:2` |
| Numbered books | `1 John`, `1John`, `1 Jn`, `I John`, `First John` |
| Separators | colon or period (`3:16` ≡ `3.16`) |

Two deliberate disambiguations: bare `jud` → **Jude**, while Judges is `jdg`/`judg`/`jg`.
Multi-reference strings joined by `;` are out of scope for v1. Malformed input →
`400 unparseable_reference`; an unknown book token → `404 unknown_book`.
