# Concord API reference

Every endpoint, with real request/response examples. All examples were captured from a
running instance loaded with the 13 bundled public-domain English translations plus the SBL
Greek New Testament (`SBLGNT`).

- **Base URL:** `http://<host>:<port>` (default `http://localhost:8000`)
- **Versioning:** data endpoints live under `/v1`. That prefix is a stability contract.
- **Machine-readable schema:** the full OpenAPI spec is committed at
  [`docs/openapi.json`](openapi.json) (also served live at `/openapi.json`), versioned with the
  release and CI-checked against the code — build clients against it with confidence.
- **Responses:** JSON (`application/json`). Verse text is returned exactly as stored —
  Unicode, editorial brackets (`[is]`), and punctuation are preserved untouched.

## Contents

- [Conventions](#conventions)
- [Errors](#errors)
- [`GET /v1/verses/{ref}`](#get-v1versesref)
- [`GET /v1/chapters/{book}/{chapter}`](#get-v1chaptersbookchapter)
- [`GET /v1/search`](#get-v1search)
- [`GET /v1/semantic-search`](#get-v1semantic-search)
- [`GET /v1/cross-references/{ref}`](#get-v1cross-referencesref)
- [`GET /v1/places`](#get-v1places)
- [`GET /v1/places/{id}`](#get-v1placesid)
- [`GET /v1/places/{id}/verses`](#get-v1placesidverses)
- [`GET /v1/verses/{ref}/places`](#get-v1versesrefplaces)
- [`GET /v1/translations/{translation}/notes/{book}/{chapter}`](#get-v1translationstranslationnotesbookchapter)
- [`GET /v1/notes/search`](#get-v1notessearch)
- [`GET /v1/topics`](#get-v1topics)
- [`GET /v1/topics/{id}`](#get-v1topicsid)
- [`GET /v1/topics/{id}/verses`](#get-v1topicsidverses)
- [`GET /v1/verses/{ref}/topics`](#get-v1versesreftopics)
- [`GET /v1/strongs`](#get-v1strongs)
- [`GET /v1/strongs/{id}`](#get-v1strongsid)
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
| `unknown_place` | 404 | A place id in a path resolves to no place (`/places/nope`). `detail.place_id` echoes it. |
| `unknown_type` | 400 | A `/places?type=` filter value isn't a known place type; `detail.available` lists the valid types. |
| `unknown_status` | 400 | A `/places?status=` filter value isn't one of identified / disputed / unknown / symbolic / multiple. |
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

Full-text search, backed by SQLite FTS5. Searches **one** translation by default; add
`?translations=` to search **several at once**, deduped by canonical verse (see
[Multi-translation search](#multi-translation-search) below).

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — (required) | FTS5 query; see syntax below. |
| `translation` | string | default translation | Single translation (single-translation mode). |
| `translations` | string | — | **Multi-translation mode.** Comma-separated ids (`KJV,WEB,ASV`), or `*` for all loaded. When present it takes precedence over `translation`; absent/blank keeps single-translation mode. |
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

### Multi-translation search

Pass `?translations=` (a comma-separated list, or `*` for all loaded) to search several
translations at once. Results are **deduped by canonical verse**: one hit per verse that matched in
at least one of the requested translations, ranked by its **best (max) relevance** across them, with
the same canonical tiebreak. `total` counts distinct matching **verses**, not (verse, translation)
pairs.

Each hit gains a `matches` map — `{ "<TRANSLATION>": "<marked snippet>", … }` — carrying every
translation that matched and its snippet. The response also echoes the searched set as
`translations`.

```bash
$ curl -s 'localhost:8000/v1/search?q=lovingkindness&translations=KJV,ASV&limit=1'
```
```json
{
  "query": "lovingkindness", "translation": "KJV", "book": null,
  "limit": 1, "offset": 0, "total": 1,
  "hits": [
    { "book": "PSA", "chapter": 63, "verse": 3, "reference": "Psalms 63:3",
      "snippet": "Because thy <mark>lovingkindness</mark> [is] better than life, ...",
      "matches": {
        "KJV": "Because thy <mark>lovingkindness</mark> [is] better than life, ...",
        "ASV": "Because thy <mark>lovingkindness</mark> is better than life, ..."
      }
    }
  ],
  "translations": ["KJV", "ASV"]
}
```

A few shape notes (the rationale is recorded in
[ADR-0003](adr/ADR-0003-search-multi-translation-shape.md)):

- The `matches` map is **authoritative** — it's the full per-translation detail.
- The flat top-level `snippet` on each hit echoes that hit's **top-ranked** translation's snippet, so
  a client that reads only `snippet` still gets something sensible (it may name a different
  translation per hit).
- The result-level `translation` is the **primary** — the first id you requested (so `translation`
  stays a single non-null id in both modes). The searched set is in `translations`.

**Additive and backward-compatible.** This is a purely additive widening: with `translations` absent
the response is **byte-for-byte** the single-translation shape above — no `matches`, no
`translations` field. Existing single-translation clients are unaffected.

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
carries the SQLite message) · `404 unknown_translation` (an unknown id in `translation` **or** any
id in `translations`) · `400 unknown_book` (filter). **Caching:** immutable.

## `GET /v1/semantic-search`

Meaning-based search: find verses by idea, not keyword. The query is embedded with a local
model and compared against precomputed verse vectors by cosine similarity; the closest verses
come back ranked. Runs fully offline — the model is baked into the image.

Search runs over **one embedded translation, the World English Bible (WEB)**, in meaning-space.
The matches are verse *references*, so `?translation=` controls which translation's **text** is
returned without changing the ranking (see "search in WEB, read in any translation" below).

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — (required) | Natural-language query, e.g. `verses about anxiety`. |
| `limit` | int | `20` | 1–100. Number of results. |
| `translation` | string | `WEB` | Which translation's **text** to return. Search always runs in WEB space. |
| `min_score` | float | — | Optional cosine floor in `[-1, 1]`; drops weaker matches. |
| `include_text` | bool | `true` | When `false`, results carry refs + scores and `text` is `null`. |

```bash
$ curl -s 'localhost:8000/v1/semantic-search?q=do+not+be+anxious&limit=3'
```
```json
{
  "query": "do not be anxious", "translation": "WEB", "count": 3,
  "results": [
    { "book": "DEU", "chapter": 1, "verse": 29, "reference": "Deuteronomy 1:29", "score": 0.9174,
      "text": "Then I said to you, “Don’t dread, neither be afraid of them." },
    { "book": "HAG", "chapter": 2, "verse": 5, "reference": "Haggai 2:5", "score": 0.8967,
      "text": "This is the word that I covenanted with you when you came out of Egypt, ..." },
    { "book": "1TH", "chapter": 5, "verse": 20, "reference": "1 Thessalonians 5:20", "score": 0.8952,
      "text": "Don’t despise prophesies." }
  ]
}
```

`score` is cosine similarity in `[-1, 1]` (higher is closer), rounded to 4 places; results are
ranked descending.

**Search in WEB, read in any translation.** The matched references are hydrated in the
requested `translation`. A verse absent there (a versification gap) comes back with
`text: null` — the match still ranks; only its text in that translation is missing. Searching
`the good shepherd` matches John 10 in WEB space and renders it in the KJV:

```bash
$ curl -s 'localhost:8000/v1/semantic-search?q=the+good+shepherd&translation=KJV&limit=2'
```
```json
{
  "query": "the good shepherd", "translation": "KJV", "count": 2,
  "results": [
    { "book": "JHN", "chapter": 10, "verse": 11, "reference": "John 10:11", "score": 0.9421,
      "text": "I am the good shepherd: the good shepherd giveth his life for the sheep." },
    { "book": "JHN", "chapter": 10, "verse": 14, "reference": "John 10:14", "score": 0.9111,
      "text": "I am the good shepherd, and know my [sheep], and am known of mine." }
  ]
}
```

**Empty results** return `200` with `"count": 0` and `"results": []` — never a 404.

**Errors:** `422 invalid_parameter` (missing/empty `q`, `limit` out of 1–100, `min_score`
outside `[-1, 1]`) · `404 unknown_translation`. **Caching:** immutable (body-hash ETag, like
`/v1/search`).

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

## `GET /v1/places`

Browse and filter the geography dataset (1,340 places), ordered by name.

| Param | Type | Default | Notes |
|---|---|---|---|
| `type` | string | — | Filter by place type (`settlement`, `region`, `mountain`, `river`, …). Unknown → `400 unknown_type`. |
| `status` | string | — | Filter by status: `identified`, `disputed`, `unknown`, `symbolic`, `multiple`. |
| `q` | string | — | Case-insensitive substring match on the display name. |
| `limit` | int | `50` | 1–200. |
| `offset` | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/places?type=settlement&limit=2'
```
```json
{
  "type": "settlement", "status": null, "q": null,
  "limit": 2, "offset": 0, "total": 843,
  "places": [
    { "id": "a72a1ff", "friendly_id": "Abdon", "name": "Abdon", "type": "settlement",
      "latitude": 33.047692, "longitude": 35.161916,
      "confidence": "high", "confidence_score": 826, "status": "identified" },
    { "id": "abffcaa", "friendly_id": "Abel-beth-maacah", "name": "Abel-beth-maacah", "type": "settlement",
      "latitude": 33.258051, "longitude": 35.581007,
      "confidence": "high", "confidence_score": 756, "status": "identified" }
  ]
}
```

Each place carries named **`latitude`/`longitude`** fields (never a bare ordered pair), a
`confidence` (`high`/`medium`/`low`, or `null`), the raw `confidence_score`, and a `status`
(see [`GET /v1/places/{id}`](#get-v1placesid) for what each status means). Results are ordered
by `name` then `id`, so `limit`/`offset` pages don't overlap; `total` is the full filtered count.

**Empty results** return `200` with `"total": 0` and `"places": []`.

**Errors:** `400 unknown_type` (with `detail.available`) · `400 unknown_status` ·
`422 invalid_parameter` (`limit` out of 1–200, negative `offset`). **Caching:** immutable.

## `GET /v1/places/{id}`

One place's full detail, by its stable id, plus how many verses mention it.

| Param | In | Type | Notes |
|---|---|---|---|
| `id` | path | string | The OpenBible place id (e.g. `a15257a`). |

```bash
$ curl -s 'localhost:8000/v1/places/a15257a'
```
```json
{
  "id": "a15257a", "friendly_id": "Jerusalem", "name": "Jerusalem", "url_slug": "jerusalem",
  "type": "settlement", "preceding_article": "",
  "latitude": 31.776667, "longitude": 35.234167,
  "confidence": "high", "confidence_score": 1000, "status": "identified",
  "modern_name": "Jerusalem", "verse_count": 955
}
```

**The honesty model.** `status` is how confidently the place is located, and Concord never
fabricates coordinates:

| `status` | Meaning | Coordinates |
|---|---|---|
| `identified` | A confident location. | present |
| `disputed` | Scholars place it differently; a best guess is given but flagged. | present (hedged) |
| `unknown` | The location is genuinely lost to history. | `null` |
| `symbolic` | A name used non-literally (prophetic/figurative). | `null` |
| `multiple` | Itinerant — refers to several places (e.g. the tabernacle). | `null` |

An `unknown` place is honest about it — the land of Nod returns null coordinates rather than a
fabricated pin:

```bash
$ curl -s 'localhost:8000/v1/places/a1ad8e1'
```
```json
{
  "id": "a1ad8e1", "friendly_id": "Nod", "name": "Nod", "url_slug": "nod",
  "type": "region", "preceding_article": "",
  "latitude": null, "longitude": null,
  "confidence": null, "confidence_score": null, "status": "unknown",
  "modern_name": null, "verse_count": 1
}
```

Distinct places that share a name are distinct entries with distinct ids — the several Antiochs
and Bethlehems each have their own id and `friendly_id` (`Antioch 1`, `Antioch 2`).

**Errors:** `404 unknown_place` (`detail.place_id` echoes the id). **Caching:** immutable.

## `GET /v1/places/{id}/verses`

The verses that mention a place, in canonical order, optionally with text. This is one direction
of the **bi-directional** link; the inverse is [`GET /v1/verses/{ref}/places`](#get-v1versesrefplaces).

| Param | Type | Default | Notes |
|---|---|---|---|
| `id` | path · string | — | The place id. |
| `translation` | string | default translation | Which translation's text to hydrate. Only consulted when `include_text=true`. |
| `include_text` | bool | `true` | When `false`, `translation` is `null` and each `text` is `null`. |
| `limit` | int | `50` | 1–200. |
| `offset` | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/places/a15257a/verses?translation=KJV&limit=2'
```
```json
{
  "id": "a15257a", "translation": "KJV", "include_text": true,
  "limit": 2, "offset": 0, "total": 955,
  "verses": [
    { "book": "JOS", "chapter": 10, "verse": 1, "reference": "Joshua 10:1",
      "text": "Now it came to pass, when Adonizedek king of Jerusalem had heard how Joshua had taken Ai ..." },
    { "book": "JOS", "chapter": 10, "verse": 2, "reference": "Joshua 10:2",
      "text": "That they feared greatly, because Gibeon [was] a great city ..." }
  ]
}
```

A verse absent in the chosen translation comes back with `text: null`. With `include_text=false`,
the response carries just the references — `translation` is `null` and every `text` is `null`.
`total` is the place's full verse count, independent of the page.

**Errors:** `404 unknown_place` · `404 unknown_translation` (with `include_text=true`) ·
`422 invalid_parameter` (`limit` out of 1–200). **Caching:** immutable.

## `GET /v1/verses/{ref}/places`

The inverse lookup: the places named anywhere in `{ref}` — a verse, a range, or a whole chapter.

| Param | In | Type | Notes |
|---|---|---|---|
| `ref` | path | string | A reference per the [grammar](#reference-grammar) (URL-encode spaces). |

```bash
$ curl -s 'localhost:8000/v1/verses/Acts%2017/places'
```
```json
{
  "reference": "Acts 17", "total": 6,
  "places": [
    { "id": "a4bdea7", "friendly_id": "Amphipolis", "name": "Amphipolis", "type": "settlement",
      "latitude": 40.820159, "longitude": 23.847209,
      "confidence": "high", "confidence_score": 1000, "status": "identified" },
    { "id": "ab20df9", "friendly_id": "Apollonia", "name": "Apollonia", "type": "settlement",
      "latitude": 40.623703, "longitude": 23.469685,
      "confidence": "high", "confidence_score": 1000, "status": "identified" }
  ]
}
```

The result is the **deduped union** across the reference's range — a place named in several
verses of the passage appears once — ordered by `name` then `id`. A reference that names no place
returns `200` with `"total": 0` and `"places": []` (never a 404).

**Errors:** `400 unparseable_reference` · `404 unknown_book`. **Caching:** immutable.

## `GET /v1/translations/{translation}/notes/{book}/{chapter}`

Translator's notes for a passage in one translation — study / translator's / text-critical notes
anchored to a point in the verse text, each with its own cross-references. Ordered by `verse`,
then `ordinal`.

> **Notes are user-supplied and never shipped.** The published image contains **zero** notes
> (the richest source, NET, is copyrighted — see [notes-ingest](v4/notes-ingest.md)), so on a
> stock image this endpoint returns `200` with an empty list for every translation. A note set
> appears only after a user bakes their own legally-obtained notes into `bible.db` locally.
>
> **To supply your own:** drop a `<TRANSLATION>.json` file into the gitignored
> `data/private/notes/` directory and rebuild (`make build-db`); the loader picks it up
> automatically, and the file never enters the public repo or a shared image. See
> [`examples/notes-sample.json`](../examples/notes-sample.json) for a minimal, runnable example
> of the file shape, and [notes-ingest](v4/notes-ingest.md) for the full contract (field rules,
> aliases, validation).

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `translation` | path | string | — | A loaded translation id (case-insensitive). Unknown → `404`. |
| `book` | path | string | — | A book id or alias per the [grammar](#reference-grammar). Unknown → `404`. |
| `chapter` | path | int | — | ≥ 1. |
| `verse` | query | int | — | ≥ 1. Narrows to a single verse; omit for the whole chapter. |

```bash
$ curl -s 'localhost:8000/v1/translations/NET/notes/John/3?verse=16'
```
```json
{
  "translation": "NET", "book": "JHN", "chapter": 3, "verse": 16, "total": 1,
  "notes": [
    {
      "book": "JHN", "chapter": 3, "verse": 16, "reference": "John 3:16",
      "type": "tn", "text": "Or 'this is how much God loved the world.'",
      "char_offset": 8, "marker": "23", "ordinal": 1,
      "cross_references": [
        { "to_book": "ROM", "to_chapter": 5, "to_verse_start": 8, "to_verse_end": null,
          "reference": "Romans 5:8" }
      ]
    }
  ]
}
```

Each note carries its **canonical anchor** (`book`/`chapter`/`verse` + a human `reference`), the
`type` (`tn` translator's · `sn` study · `tc` text-critical · `map` · or `null` for a plain
footnote), the `text`, the **`char_offset`** (a point — where the marker attaches in the verse
text — not a span), the source `marker`, the `ordinal` (stable order within a verse), and the
note's own `cross_references` (each a target by canonical coords, `to_verse_end` null for a single
verse, set for a range).

**Empty results** return `200` with `"total": 0` and `"notes": []` — a translation with no notes
loaded (every translation on the public image) is a normal state, **not** a 404. Likewise a valid
book + chapter (or `?verse`) that simply has no notes returns empty.

**Errors:** `404 unknown_translation` · `404 unknown_book` · `422 invalid_parameter`
(`chapter`/`verse` < 1). **Caching:** immutable.

## `GET /v1/notes/search`

Full-text keyword search over translator-note **bodies** (the `notes_fts` FTS5 mirror), across all
loaded note translations by default. The counterpart to [`/v1/search`](#get-v1search) for notes; the
read endpoint above fetches notes by passage, this one finds them by text.

> **Notes are user-supplied and never shipped.** The published image contains **zero** notes (the
> richest source, NET, is copyrighted — see [notes-ingest](v4/notes-ingest.md)), so on a stock image
> this endpoint returns `200` with an empty list for **every** query. A populated example like the
> one below requires a user to bake their own legally-obtained notes into `bible.db` locally: drop a
> `<TRANSLATION>.json` into the gitignored `data/private/notes/` directory and rebuild
> (`make build-db`). See [`examples/notes-sample.json`](../examples/notes-sample.json) and
> [notes-ingest](v4/notes-ingest.md) for the file shape and contract.

| Param | Type | Default | Notes |
|---|---|---|---|
| `q` | string | — (required) | FTS5 query; same syntax as [`/v1/search`](#get-v1search). |
| `translation` | string | — (all) | Optional **filter** to one notes translation (e.g. `NET`). Case-insensitive. Omitted ⇒ all loaded. |
| `type` | string | — (all) | Optional filter: `tn` (translator's) · `sn` (study) · `tc` (text-critical) · `map` · `other`. |
| `book` | string | — | Optional filter; USFM id or alias. |
| `limit` | int | `20` | 1–100. |
| `offset` | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/notes/search?q=Greek&translation=NET&type=tn&limit=1'
```
```json
{
  "query": "Greek", "translation": "NET", "type": "tn", "book": null,
  "limit": 1, "offset": 0, "total": 1,
  "hits": [
    { "book": "JHN", "chapter": 3, "verse": 16, "reference": "John 3:16",
      "translation": "NET", "type": "tn", "char_offset": 8, "marker": "23", "ordinal": 1,
      "snippet": "The <mark>Greek</mark> construction here indicates result, not purpose." }
  ]
}
```

Each hit carries the note's **canonical anchor** (`book`/`chapter`/`verse` + a human `reference`),
the owning `translation`, the `type` (or `null` for a plain footnote), the `char_offset`, source
`marker`, `ordinal`, and a `<mark>`-tagged `snippet` of the note body. The note's own
`cross_references` are **omitted** here for leanness — fetch the full note (with its cross-references)
via the [passage read](#get-v1translationstranslationnotesbookchapter) above. Results are
relevance-ranked (FTS5 `rank`) with a canonical tiebreak (verse → ordinal → id).

**Empty results** return `200` with `"total": 0` and `"hits": []` — never a 404. This is the normal
state on the public image (no notes loaded) and for any query with no matches.

**Errors:** `404 unknown_translation` · `400 unknown_type` (unknown `type`; `detail.available` lists
the valid types) · `400 unknown_book` (filter) · `400 invalid_search_query` (malformed FTS5 —
`detail.fts5_error`) · `422 invalid_parameter` (missing/empty `q`, `limit` out of 1–100).
**Caching:** immutable.

## `GET /v1/topics`

Browse topical-Bible subjects from [Nave's Topical Bible](https://github.com/BradyStephenson/bible-data)
(public domain, 1897). Optionally filter by name substring (`q`, case-insensitive) and `section`
(the A–Z index letter). Ordered by `name`, then `id`.

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `q` | query | string | — | Case-insensitive name substring. |
| `section` | query | string | — | The A–Z index letter (e.g. `F`). |
| `limit` | query | int | `50` | 1–200. |
| `offset` | query | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/topics?q=faith&limit=2'
```
```json
{
  "q": "faith", "section": null, "limit": 2, "offset": 0, "total": 4,
  "topics": [
    { "id": "faith", "name": "FAITH", "section": "F", "see_also": null },
    { "id": "faithfulness", "name": "FAITHFULNESS", "section": "F", "see_also": null }
  ]
}
```

`see_also` is the id of another topic when this one is a "See X" redirect (Nave's points
`ANXIETY` at `CARE`); such topics carry no verses of their own. **Caching:** immutable.

## `GET /v1/topics/{id}`

One topic's detail, including its `verse_count` (0 for a redirect).

| Param | In | Type | Notes |
|---|---|---|---|
| `id` | path | string | A topic id (slug). Unknown → `404 unknown_topic`. |

```bash
$ curl -s 'localhost:8000/v1/topics/care'
```
```json
{ "id": "care", "name": "CARE", "section": "C", "see_also": null, "verse_count": 53 }
```

**Errors:** `404 unknown_topic` (`detail.topic_id`). **Caching:** immutable.

## `GET /v1/topics/{id}/verses`

The verses curated under a topic, in canonical order, optionally hydrated with text.

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `id` | path | string | — | A topic id. Unknown → `404 unknown_topic`. |
| `translation` | query | string | default translation | Used only when `include_text=true`. |
| `include_text` | query | bool | `true` | When `false`, `text` is null and `translation` is echoed as null. |
| `limit` | query | int | `50` | 1–200. |
| `offset` | query | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/topics/care/verses?translation=KJV&limit=2'
```
```json
{
  "id": "care", "translation": "KJV", "include_text": true, "limit": 2, "offset": 0, "total": 53,
  "verses": [
    { "book": "PSA", "chapter": 37, "verse": 5, "reference": "Psalms 37:5",
      "text": "Commit thy way unto the LORD; trust also in him; and he shall bring it to pass." },
    { "book": "PSA", "chapter": 39, "verse": 6, "reference": "Psalms 39:6", "text": "…" }
  ]
}
```

A verse absent in the chosen translation hydrates as `text: null` (not an error). A redirect or
empty topic returns `"total": 0`, `"verses": []`. **Errors:** `404 unknown_topic`.
**Caching:** immutable.

## `GET /v1/verses/{ref}/topics`

The inverse lookup: the topics that cite any verse in `{ref}` — a verse, a range, or a chapter.

| Param | In | Type | Notes |
|---|---|---|---|
| `ref` | path | string | A reference per the [grammar](#reference-grammar) (URL-encode spaces). |

```bash
$ curl -s 'localhost:8000/v1/verses/Philippians%204:6/topics'
```
```json
{
  "reference": "Philippians 4:6", "total": 5,
  "topics": [
    { "id": "care", "name": "CARE", "section": "C", "see_also": null },
    { "id": "commandments", "name": "COMMANDMENTS", "section": "C", "see_also": null },
    { "id": "prayer", "name": "PRAYER", "section": "P", "see_also": null }
  ]
}
```

The **deduped union** across the reference's range, ordered by `name` then `id`. A reference citing
no topic returns `200` with `"total": 0`, `"topics": []`. **Errors:** `400 unparseable_reference` ·
`404 unknown_book`. **Caching:** immutable.

## `GET /v1/strongs`

Browse the Strong's lexicon (the Greek lexicon from [STEPBible](https://github.com/STEPBible/STEPBible-Data),
CC BY 4.0). Optionally filter by `q` (a case-insensitive substring of the lemma, transliteration,
or gloss) and `language` (`grc` for Greek). Ordered by Strong's number within language.

| Param | In | Type | Default | Notes |
|---|---|---|---|---|
| `q` | query | string | — | Substring of lemma, transliteration, or gloss. |
| `language` | query | string | — | ISO 639-3 code (`grc`). |
| `limit` | query | int | `50` | 1–200. |
| `offset` | query | int | `0` | ≥ 0. |

```bash
$ curl -s 'localhost:8000/v1/strongs?q=love&language=grc&limit=2'
```
```json
{
  "q": "love", "language": "grc", "limit": 2, "offset": 0, "total": 18,
  "entries": [
    { "strongs_id": "G25", "language": "grc", "lemma": "ἀγαπάω", "transliteration": "agapaō", "gloss": "to love" },
    { "strongs_id": "G26", "language": "grc", "lemma": "ἀγάπη", "transliteration": "agapē", "gloss": "love" }
  ]
}
```

**Caching:** immutable.

## `GET /v1/strongs/{id}`

One lexicon entry in full, including the definition. The id is normalized — the leading letter is
upper-cased and any zero-padding dropped, so `g0026`, `g26`, and `G26` all resolve to `G26`.

| Param | In | Type | Notes |
|---|---|---|---|
| `id` | path | string | A Strong's number (e.g. `G26`). Unknown → `404 unknown_strongs`. |

```bash
$ curl -s 'localhost:8000/v1/strongs/G26'
```
```json
{
  "strongs_id": "G26", "language": "grc", "lemma": "ἀγάπη", "transliteration": "agapē",
  "gloss": "love", "definition": "ἀγάπη, -ης, ἡ … love, goodwill, esteem. …",
  "source": "STEP Bible (Tyndale House)"
}
```

**Errors:** `404 unknown_strongs` (`detail.strongs_id`). **Caching:** immutable.

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
{
  "status": "ok",
  "translation_count": 14, "verse_count": 412806, "cross_ref_count": 344799, "book_count": 66,
  "place_count": 1340,
  "semantic": {
    "enabled": true, "translation": "WEB", "embedding_count": 31054,
    "model": "ibm-granite/granite-embedding-311m-multilingual-r2", "dim": 768
  }
}
```

The `semantic` block reports semantic-search readiness: the embedded translation, the vector
count, and the model. When semantic search is disabled (`CONCORD_SEMANTIC_SEARCH=0`) it is
`{ "enabled": false }`. The Docker healthcheck treats the container as healthy when this
returns 200 with `translation_count > 0` and semantic search ready.

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
