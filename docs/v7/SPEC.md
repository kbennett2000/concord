# Concord v7 — Journeys / routes Build Spec

**Concord v7** adds **journeys**: a curated set of well-known biblical itineraries — Paul's
missionary journeys, the Exodus — as **ordered sequences of existing places**, so a consumer
(songbird's map) can draw them as polylines. Ask *what is Paul's first journey* and get an ordered
list of stops, each resolving to a real place with coordinates, plus the inverse: *what journeys
pass through Antioch*. It runs fully offline, like everything else.

This spec sits alongside `docs/SPEC.md` (v1, the read API) and `docs/v3/SPEC.md` (geography). v7 is
**purely additive** and reuses v3 — no new package, no ML, no runtime model — just two new data
tables in `bible-core` and new endpoints in `bible-api`. The `/v1` URL prefix stays; "v7" is the
milestone. v3 §3 named journeys "the next frontier"; this is it.

---

## 1. Goals & shape

The capability is **curated routes over existing geography**, served read-only and offline. For
each journey: a stable id, a name, the overall scripture range, an approximate dating, a sourced
route, and an **ordered sequence of stops** — each stop a reference into the v3 `places` table
(coordinates included via that data's honesty model). Plus the inverse: for any place, the journeys
that pass through it.

**This REUSES v3 — it does not rebuild geography.** v3 already provides stable, external-safe
place-ids and scholarly disambiguation (the two foundation requirements v3 §1 deliberately
satisfied *for this milestone*). A journey stop is a foreign key into `places`; new geography is
never minted here. The several "Antioch"s being distinct place-ids is exactly why Paul's first
journey can begin and end at Syrian Antioch (`ae41ab4`) while also stopping at Pisidian Antioch
(`a6c704a`).

## 2. Architecture

The calmest milestone since v3. Routes are pure reference data over existing data:

```
bible-core   (pure: stdlib sqlite3 — gains a journeys + journey_stops schema + read queries)
     ▲
bible-api    (web: gains the /v1/journeys* and /v1/places/{id}/journeys endpoints)
```

**No new package. No `bible-semantic`. No ML.** The journeys tables live in `bible.db` alongside
the verses, places, and cross-references — baked in at build by the existing flow, like v3's
geography. `bible-core` stays web-free and ML-free.

## 3. Decisions & non-goals

**THE SCOPE DISCIPLINE (the whole game).** The minimal cut is a curated handful of journeys, each
an ordered sequence of existing place-ids, with **ONE sourced canonical route**, dated as a whole.
The honesty model is extended to routes: each journey flags that it's one proposed reconstruction
and cites its source (`source` + `note`). The following are **deliberately deferred** and must not
be built without an explicit scope decision:

- **Competing routes / route variants** — a future `route_variants` layer and its own decision.
- **Per-segment dating debates** and segment-level link apparatus.
- **Region grouping / containment** (deferred with v3) and geometry rendering — the consumer draws
  the polyline from the ordered coordinates; Concord serves the ordered points, not the line.

**Route source = Scripture-derived.** The stop sequence comes straight from the public-domain
biblical narrative (Acts 13–14 for Paul's first journey). Place identifications/coordinates reuse
the already-attributed v3 OpenBible data. No new external dataset; provenance in `data/SOURCES.md`.
Dating is recorded as conventional/approximate.

**Per-stop scripture reference included.** Each stop carries an optional `reference` ("Acts 13:4") —
lightweight narrative grounding, *not* the deferred per-segment apparatus.

**Curated set.** Paul's first, second, and third journeys; the voyage to Rome; and the Exodus. The
Exodus is the honesty model in action: many of its stops are `unknown`/`symbolic` places with no
coordinates — surfaced honestly, the consumer simply can't pin them. (Paul's first journey lands
first, in S1; the rest fill in at S4.)

## 4. Data model

Two new tables in `bible.db`, owned by `bible-core` (additive — existing tables untouched).

**`journeys`**
| column | type | notes |
|---|---|---|
| `id` | TEXT | hand-minted stable slug (`paul-first`) — **external-safe PK** |
| `name` | TEXT | "Paul's First Missionary Journey" |
| `scripture` | TEXT | overall narrative range ("Acts 13–14") |
| `dating` | TEXT NULL | "c. AD 46–48 (conventional)"; NULL when genuinely debated |
| `source` | TEXT | provenance citation for the route (Scripture-derived) |
| `note` | TEXT | the honesty hedge: one proposed reconstruction |

**`journey_stops`**
| column | type | notes |
|---|---|---|
| `journey_id` | TEXT | FK → `journeys.id` |
| `ordinal` | INTEGER | 1-based sequence position |
| `place_id` | TEXT | FK → `places.id` — into EXISTING geography |
| `reference` | TEXT NULL | optional scripture citation for this leg |

Primary key `(journey_id, ordinal)`. `place_id` is a **repeatable** column (return legs revisit
cities), unlike the place/topic junction tables whose PK includes the place. An index on `place_id`
supports the reverse place→journeys direction, mirroring `idx_place_verses_bcv`.

## 5. The honesty model, extended to routes

v3 surfaced per-place confidence/status so a guess is never shown as fact. v7 extends that to the
route level:

- **A journey is one reconstruction.** `source` cites where the route comes from; `note` states
  plainly that it's one commonly proposed reconstruction and that variants are not modeled. The API
  surfaces both — the route-level analogue of v3's per-place `status`.
- **Stops inherit place honesty.** A stop's coordinates come straight from its place: an
  `identified` place yields a pin; an `unknown`/`symbolic` place yields `null` coordinates (with
  its `status` surfaced). The consumer draws the points it can and honestly omits the rest.

## 6. Endpoints

All read-only, all immutable-cacheable (the data is baked, never changes at runtime), so all reuse
v1's immutable `ETag` + `Cache-Control` machinery and the v1 error envelope.

**`GET /v1/journeys`** — browse/list journeys. `limit` (default 50, max 200) / `offset`. Returns
summaries (id, name, scripture, dating, stop_count).

**`GET /v1/journeys/{id}`** — a single journey's detail: its metadata (name, scripture, dating,
**source**, **note**) plus its **ordered stops**, each resolving to its place-id with name,
coordinates, confidence, status, and the leg's reference. Unknown id → 404 `unknown_journey`.
(Stops are embedded — the set is small; no separate `/stops` endpoint.)

**`GET /v1/places/{id}/journeys`** — the inverse: the journeys that pass through a place. Unknown id
→ 404 `unknown_place` (reusing v3's error). A place in no journey → 200 with an empty list.

## 7. Build plan — sliced for Claude Code

| # | Slice | Package(s) | Delivers |
|---|---|---|---|
| V7-S1 | Schema + loader + queries + Paul's first journey | core | `journeys` + `journey_stops` schema; the build-time loader (FK-validated against `places`, fail-loud); the read queries; `data/journeys/journeys.json` (paul-first); provenance + this spec + ADR-0008. Tested independent of HTTP. **No endpoints yet.** |
| V7-S2 | The two forward endpoints | api | `GET /v1/journeys` + `GET /v1/journeys/{id}`. Acceptance (forward). |
| V7-S3 | The reverse endpoint | api | `GET /v1/places/{id}/journeys`. Acceptance (reverse). |
| V7-S4 | Fill the curated set + docs | data, repo | Paul's 2nd & 3rd journeys, the voyage to Rome, the Exodus; README + `docs/API.md`; the "next frontier" update — curated journeys ship, competing routes remain deferred. |

## 8. Acceptance

`GET /v1/journeys/paul-first` returns ordered stops resolving to real place-ids with coordinates +
a source/dating + the one-reconstruction flag; `GET /v1/places/{a stop}/journeys` lists it; green.
(Forward in S2, reverse in S3; the rest of the curated set in S4.)
