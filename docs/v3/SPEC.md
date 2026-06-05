# Concord v3 — Geography Build Spec

**Concord v3** adds **biblical geography**: where places in Scripture are, and the
bi-directional link between places and the verses that mention them. Ask *where is
Capernaum* and get coordinates; ask *what places appear in Acts 17* and get them back. It
runs fully offline, like everything else.

This spec sits alongside `docs/SPEC.md` (v1, the read API) and `docs/v2/SPEC.md` (semantic
search). v3 is **purely additive** and the **calmest architecture of the three**: no new
package, no ML, no runtime model — just new data tables in `bible-core` and new endpoints
in `bible-api`. The `/v1` URL prefix stays; "v3" is the milestone.

This is **Lean** scope by deliberate decision (see §3): places, coordinates, the
place↔verse links, and honest confidence — the genuinely useful core. **Journeys and routes
are explicitly deferred to a future version**, and the two foundation requirements below
exist precisely so that future is buildable without retrofitting.

---

## 1. Goals & shape

The capability is **place data + bi-directional verse linking**, served read-only and
offline. For each identifiable biblical place: a stable id, its name(s), its type, its
best-known coordinates *with an honest confidence indicator*, and the verses that mention
it. Plus the inverse: for any verse, the places it names.

Two **foundation requirements** are load-bearing — not for Lean's own sake, but so a future
journeys/routes version can reference this data instead of rebuilding it. Both are satisfied
by the source dataset (§4), so they cost nothing beyond doing the work consciously:

- **Stable, external-safe place IDs.** Place IDs must be durable identifiers safe to
  reference from outside (and from a future journeys layer) — **not** row positions that
  shift on a data rebuild.
- **Proper disambiguation.** Distinct places that share a name (the several "Antioch"s and
  "Bethlehem"s) must be distinct, separately-identified entries — never collapsed into one
  fuzzy place.

## 2. Architecture

The calmest version yet. Geography is pure reference data, so it lives where the rest of
the canonical data lives:

```
bible-core      (pure: stdlib sqlite3 — gains a places + place_verses schema + read queries)
     ▲
bible-api       (web: gains the /v1/places* and /v1/verses/{ref}/places endpoints)
```

**No new package. No `bible-semantic` involvement. No ML, no model, no runtime inference.**
The geography tables live in `bible.db` alongside the verses, books, and cross-references —
exactly as v1's Slice 6 added the cross-reference tables to `bible.db`. They are baked into
the image at build by the existing build flow. `bible-core` stays web-free and ML-free;
adding data tables doesn't change that.

## 3. Decisions & non-goals

**Dataset: OpenBible.info Bible-Geocoding-Data** (§4) — CC-BY 4.0, the same source family as
our cross-references, covering the Protestant canon (matches our v1 canon). It already
provides stable IDs and scholarly disambiguation, satisfying both §1 foundation
requirements.

**Lean scope.** v3 ships: places with names/types, best-known coordinates, an honest
confidence/status indicator, and bi-directional place↔verse linking. That's the useful 80%,
and it ships clean.

**Adopt OpenBible's IDs as our place IDs.** OpenBible's seven-digit ancient `id` (e.g.
`a15257a`) becomes our place primary key — stable and external-safe by construction. We do
**not** mint our own row-based IDs. We preserve the `friendly_id` ("Aphek 1", "Aphek 2") so
consumers can distinguish same-named places. Both §1 requirements, satisfied by the data.

**Honest uncertainty, surfaced (§6).** Coordinates come with a confidence indicator and a
status (identified / disputed / unknown / symbolic). A shaky guess is never presented as
fact; an unknown place (the Garden of Eden) is honestly marked unknown with no coordinates.
This mirrors how v1 surfaced cross-reference vote counts.

**Place `type` included** (cheap win). The source carries a single top-level `type` string
per place ("settlement", "body of water", "region", …). Including it costs one column and
lets the API distinguish a city from a river from a region. (This is *not* the deferred
"Plus" work — that was region *grouping* and elaborate confidence modeling, both omitted.)

**Geography data lives in `bible.db`**, baked at build via the existing flow — the
cross-references pattern from v1 Slice 6.

**Out of scope for v3** (no build without an explicit scope decision):
- **Journeys / routes** (Paul's missionary journeys, the Exodus path) — ordered sequences,
  competing proposed routes, segment-level links, and dating debates are a distinct
  data-and-modeling problem. **Deferred to a future version**, which will *reference* this
  place data (hence the §1 foundation requirements). This is the named next frontier.
- **Region grouping / containment** (places-within-a-region) — the source has
  `contained_in`/`contains`, but modeling the hierarchy is deferred.
- **The full scholarly apparatus** — see §4's "what we deliberately ignore."
- Geometry rendering (paths/polygons/isobands), images, linked-data, place *people*/*events*
  associations.

## 4. The dataset — and the discipline of the subset

**Source:** `github.com/openbibleinfo/Bible-Geocoding-Data`, **CC-BY 4.0**. JSON Lines files;
the relevant ones are `ancient.jsonl` (biblical places, disambiguated, with verse links and
confidence) and `modern.jsonl` (modern locations with coordinates and precision).

> **The single most important constraint in this spec.** This dataset is *far* richer than
> Lean needs — its own README warns "The structure of the JSON is somewhat complex. Sorry!"
> The ingestion MUST extract a disciplined subset and **deliberately ignore** the rest.
> Attempting to model the full dataset is the primary risk of v3.

**What we extract** (per ancient place):
- `id` → our stable place id.
- `friendly_id` → the disambiguated display/disambiguation name ("Aphek 1").
- a clean display `name` and `url_slug`.
- `type` → the place type.
- `preceding_article` → "the" or "".
- **Best coordinates + confidence**, resolved from `modern_associations` (the summary object
  listing associated modern locations with an adjusted `score`) → take the highest-scoring
  association, read its `lonlat` from `modern.jsonl`. The score drives the confidence
  indicator (§6).
- **Status**, derived from the resolution kind: a confident modern association →
  *identified*; low-scoring or competing → *disputed*; a `special` resolution of
  `unknown_place` → *unknown*; `nonspecific_place` → *symbolic*; `multiple_locations` →
  itinerant/multiple (§6).
- **Verse links** from the `verses` array — map each verse to our USFM book id + chapter +
  verse via the `sort` key (BBCCCVVV, BB = 01 Genesis … 66 Revelation, a direct map to our
  canonical book order) or `osis`.

> **Field reality (verified against the live dataset, V3-S0).** The data's field *shapes*
> differ from the names above; the ingest honors reality, not the labels:
> - The top-level `name` and `type` (singular) fields are **`null` for every record.** The
>   display **`name` is derived from `friendly_id`** by stripping a trailing disambiguation
>   index ("Aroer 2" → "Aroer"); the **`type` comes from the `types` array** (plural,
>   100%-populated — settlement, region, mountain, river, …) as `types[0]`.
> - `modern.jsonl`'s **`lonlat` is `"longitude,latitude"` order** — longitude first. The
>   loader assigns `longitude = parts[0]`, `latitude = parts[1]`.
> - The `special` marker lives at `identifications[].resolutions[].special`. Alongside the
>   five kinds in §6 the data carries a sixth, **`recursive`** (a resolution-path loop ⇒ no
>   usable coordinate); it is folded into **`unknown`**.
> - The adjusted `score` range is wider than the upstream "0–1000" note: observed **−87 …
>   1169** (negative = the weight of scholarship judges the identification *wrong*; see §6).

**What we deliberately ignore** (present in the data; *not* ingested for Lean): time-weighted
confidence regressions (`time_*` scores), multi-path resolution detail (`paths`,
`best_path_score`), isoband and polygon/path geometry (`geometry.jsonl`, GeoJSON/KML files),
images (`image.jsonl`, thumbnails), linked-data connections (`linked_data` — Wikidata,
Pleiades, etc.), the 400+ sources (`source.jsonl`), Palestine-1923 grid coordinates
(`epsg_28191`), alternate transliterations beyond the display name, and the per-translation
spelling/instance apparatus beyond what verse-linking needs.

**Edges to handle in ingestion:**
- **`not_a_place` / `not_a_proper_name`** entries (a name some translations treat as a place
  but may not be) — decide whether to exclude or flag (Open Questions §9).
- **`alternate_verses`** (a translation places the name in a different verse than ESV) — for
  Lean, link the primary `sort`-based reference; alternates can be simplified (Open
  Questions).
- A place with **only a `special` resolution** has no coordinates — that's a *feature* (the
  honesty model), not a gap.

**Attribution:** CC-BY 4.0, credited in the README and `data/SOURCES.md` verbatim alongside
the existing cross-reference attribution. The source data committed to the repo under
`data/` like the cross-reference data.

## 5. Data model

Two new tables in `bible.db`, owned by `bible-core` (additive — existing tables untouched),
mirroring the cross-reference tables' style.

**`places`**
| column | type | notes |
|---|---|---|
| `id` | TEXT | OpenBible ancient id (`a…`) — **stable PK, external-safe** |
| `friendly_id` | TEXT | disambiguated name ("Aphek 1") |
| `name` | TEXT | clean display name |
| `url_slug` | TEXT | ascii lowercase slug |
| `type` | TEXT | "settlement", "body of water", "region", … |
| `preceding_article` | TEXT | "the" or "" |
| `latitude` | REAL NULL | best-resolution coordinate; **NULL when unknown/symbolic** |
| `longitude` | REAL NULL | best-resolution coordinate; NULL when unknown/symbolic |
| `confidence` | TEXT | bucketed: high / medium / low (NULL when no coordinate) |
| `confidence_score` | INTEGER NULL | the raw adjusted score, for transparency |
| `status` | TEXT | identified / disputed / unknown / symbolic / multiple |
| `modern_name` | TEXT NULL | the identified modern location's name, when applicable |

**`place_verses`**
| column | type | notes |
|---|---|---|
| `place_id` | TEXT | FK → `places.id` |
| `book_id` | TEXT | USFM code, matches the verses/books tables |
| `chapter` | INTEGER | |
| `verse` | INTEGER | |

Primary key `(place_id, book_id, chapter, verse)`. This one table serves **both**
directions — place→verses (`WHERE place_id = ?`) and verse→places (`WHERE book_id/chapter/
verse = ?`) — exactly as `cross_refs` does. An index supporting the verse→places direction.

## 6. The honesty model

The point of surfacing confidence is to never present a guess as a fact.

**Two independent axes (decided V3-S0).** `confidence` and `status` are *not* the same thing
and must not be collapsed into each other:

- **`confidence`** (high / medium / low) is **evidence strength**, read straight off the
  best association's adjusted `score` bucket — calibrated against the real distribution
  (median ≈ 577): **high ≥ 500 · medium 100–499 · low < 100** (negatives included as low).
- **`status`** (identified / disputed / unknown / symbolic / multiple) comes from the
  **resolution kind**, *not* from the confidence bucket. A modestly-attested place is
  `identified` with `confidence` `low` — honestly hedged, but not falsely labelled a
  scholarly controversy. `disputed` is reserved for genuine contest, not mere low score.

Status derivation:

- **identified** — a real modern association with a **non-negative** best score. Coordinates
  present; `confidence` reflects the score bucket (high / medium / low). (Jerusalem, Capernaum.)
- **disputed** — either **competing** identifications (a runner-up association in near-tie
  with the top), **or** a best score that is **net-negative** (the weight of scholarship
  judges the identification wrong — never surfaced as `identified`). Best-guess coordinates
  present but clearly hedged; `confidence` medium/low.
- **unknown** — `special` resolution `unknown_place` (or `recursive`). No coordinates;
  honestly marked. (Nod — "the land of Nod, east of Eden". Note: the dataset does **not** mark
  the Garden of Eden itself unknown — it carries a tentative resolution; V3-S0 records this.)
- **symbolic** — `special` resolution `nonspecific_place` (symbolic/prophetic). No
  coordinates. A non-physical `special` marker takes precedence over a weak association.
- **multiple** — `special` resolution `multiple_locations` (e.g. the tabernacle during the
  exodus). No single coordinate.

The API responses surface `status`, `confidence`, and (for transparency) `confidence_score`
(the raw adjusted score, which may be negative), so a consumer can show only high-confidence
pins, or display disputed locations with appropriate hedging. This is the v3 analogue of v1's
cross-reference vote counts.

## 7. Endpoints

All read-only, all immutable-cacheable (the geo data is baked, never changes at runtime), so
all reuse v1's immutable `ETag` + `Cache-Control` machinery.

**`GET /v1/places`** — browse/list places.
| param | default | notes |
|---|---|---|
| `type` | *(none)* | optional filter ("settlement", "region", …); unknown → 400 |
| `status` | *(none)* | optional filter (identified / disputed / unknown / symbolic / multiple) |
| `q` | *(none)* | optional name substring match |
| `limit` | 50 (max 200) | pagination |
| `offset` | 0 | pagination |

Returns place summaries (id, friendly_id, name, type, lat/lon, confidence, status). Mirrors
v1's list endpoints.

**`GET /v1/places/{id}`** — a single place's detail (all `places` columns, plus its verse
count). Unknown id → 404 `unknown_place`.

**`GET /v1/places/{id}/verses`** — the verses that mention this place.
| param | default | notes |
|---|---|---|
| `translation` | `CONCORD_DEFAULT_TRANSLATION` | which translation's text to hydrate |
| `include_text` | `true` | hydrate verse text (reuse v1's `get_verses`) |
| `limit` / `offset` | 50 / 0 | pagination |

Unknown id → 404. Reuses v1's verse-hydration + reference-formatting machinery.

**`GET /v1/verses/{ref}/places`** — the inverse: places named in a given verse or range.
Uses v1's existing reference parser for `{ref}`. Returns the place summaries whose
`place_verses` rows fall in the range. An unparsable ref → 400; a valid ref with no places →
200 with an empty list.

**Response shape** (Pydantic, matching v1's style) — e.g. a place summary:
```json
{
  "id": "a15257a",
  "friendly_id": "Jerusalem",
  "name": "Jerusalem",
  "type": "settlement",
  "latitude": 31.777,
  "longitude": 35.234,
  "confidence": "high",
  "confidence_score": 500,
  "status": "identified"
}
```
An unknown place surfaces honestly: `"latitude": null, "longitude": null, "confidence":
null, "status": "unknown"`.

**Errors** reuse the v1 envelope: unknown `type`/`status` filter → 400; unknown place id →
404 `unknown_place`; unparsable verse ref → 400 (consistent with v1's ref handling).

## 8. Build / ingestion notes

- The geo loader runs at **build time**, ingesting `ancient.jsonl` + `modern.jsonl` from the
  committed `data/` source into `bible.db` — the same build flow that loads translations and
  cross-references. Idempotent; rebuilds from scratch.
- **Reference mapping:** map OpenBible's `sort` (BBCCCVVV) → USFM book id via the canonical
  book order already in the `books` table; `osis` is the fallback. Do not parse the
  human-readable `readable` string.
- **Coordinate resolution:** take the highest-scoring `modern_associations` entry; read its
  `lonlat` from `modern.jsonl`; null coordinates for `special`-only resolutions.
- Source data committed under `data/` (like the cross-reference data); attribution in
  `data/SOURCES.md` + README.

## 9. Inputs needed / open questions for the build

1. **`not_a_place` / `not_a_proper_name` handling** — exclude from `places`, or include with
   a clear status? (Lean lean: exclude pure non-places; flag borderline.)
2. **Confidence bucket thresholds** — calibrate high/medium/low against the actual
   `modern_associations` score distribution.
3. **`alternate_verses` handling** — primary `sort` reference only (simplest), or record
   alternates? (Lean lean: primary only.)
4. **`{ref}/places` range semantics** — a single verse vs a multi-verse/chapter range:
   confirm it returns the union of places across the range.

None block starting; they're resolved in the loader slice's plan.

## 10. Build plan — sliced for Claude Code

Lighter than v1/v2 — three slices, same discipline.

| # | Slice | Package(s) | Delivers | Depends on | Review focus |
|---|---|---|---|---|---|
| V3-S0 | Places schema & geo ingestion | core | `places` + `place_verses` schema (additive to `bible.db`); the build-time loader ingesting the **disciplined subset** of OpenBible's `ancient.jsonl` + `modern.jsonl`; ref mapping (sort→USFM); confidence/status derivation; source data + CC-BY attribution committed; baked into `bible.db` via the existing build. **Updates CLAUDE.md**: geography into scope, journeys named as the deferred frontier. Tests: place count, a known identified place (Jerusalem: coords + high confidence), a known unknown (Nod: null coords + status unknown; the dataset does not mark Eden itself unknown), a **disambiguation check** (the multiple Antiochs are distinct rows with distinct ids), a **stable-id** assertion, verse-link round-trip. | v2 shipped | The extraction discipline (subset, not the full apparatus); ref mapping; the honesty derivation; the two foundation requirements |
| V3-S1 | Places endpoints | api | `/v1/places`, `/v1/places/{id}`, `/v1/places/{id}/verses`, `/v1/verses/{ref}/places`; honest confidence/status surfacing; verse hydration + ref formatting (reuse v1); immutable ETag caching (reuse v1); error envelope. | V3-S0, v1 read API | Bi-directional linking; the honesty surfacing in responses; reuse of v1 machinery |
| V3-S2 | Documentation | repo | README + `docs/API.md` for the places endpoints (same voice/structure as v1/v2); the CC-BY attribution; **move geography to shipped, name journeys/routes as the next frontier**; dev-notes ship marker. | V3-S1 | Accuracy; attribution; voice match; the honesty framing |

**No Docker slice needed** — the geo data rides into `bible.db` via the existing build flow
(the cross-references precedent), and the v2 image already serves `bible-api`. A
verification that the built image includes the geo tables can fold into V3-S0's build step
or V3-S2.

**Flagged combined slice — V3-S1.** Four endpoints in one slice, like v1's Slice 7 bundled
`/books` + `/translations` + `/random`. They're one coherent places surface over two
tables with shared shaping; splitting would fragment the shared response model. Every other
v3 slice stays at the smallest load-bearing unit.
