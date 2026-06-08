# ADR-0008: Curated journeys / routes as ordered sequences over existing places

**Status:** Accepted

<!--
Records how curated biblical journeys (Paul's missionary journeys, the Exodus) are added by
referencing the v3 geography (places) feature rather than rebuilding it. Format mirrors
ADR-0001..0007: Context / Options / Decision / Consequences. Designed in docs/v7/SPEC.md.
-->

## Context

Add **journeys**: a curated handful of well-known biblical itineraries — Paul's missionary journeys,
the Exodus — as **ordered sequences of existing places**, so a consumer (songbird's map) can draw
them as polylines. This is the "next frontier" v3 §3 named and deferred.

It is structurally a thin layer over v3 geography: an entry table (`journeys`) plus an **ordered**
junction table (`journey_stops`) whose stops are foreign keys into the existing `places` table. v3
deliberately satisfied two foundation requirements *for this milestone* — stable external-safe
place-ids and proper disambiguation — so journeys can reference place data instead of rebuilding it.
The several "Antioch"s being distinct place-ids is precisely what lets Paul's first journey start
and end at Syrian Antioch (`ae41ab4`) while also stopping at Pisidian Antioch (`a6c704a`).

The dominant risk is **scope balloon**: journeys invite competing-route reconstructions,
route-variant modeling, per-segment dating debates, and a full scholarly apparatus. The whole game
is holding the minimal cut.

Three design questions had real choices:
1. **Geography — reference or duplicate?** Do stops reference existing place-ids, or carry their own
   coordinates?
2. **The "one reconstruction" honesty.** How is it surfaced — a machine-readable enum, or sourced
   text?
3. **Route source / provenance.** Where does the route (and its license) come from?

## Options considered

**Geography.**
- *(A) Reference existing place-ids (FK into `places`).* A stop is `(ordinal, place_id, reference)`;
  coordinates/status come from the place via a join. No new geography; the v3 honesty model rides
  along for free (an `unknown`/`symbolic` stop has null coords). **Chosen.**
- *(B) Stops carry their own coordinates.* Duplicates geography, drifts from v3's curated/disputed
  data, and abandons the disambiguation foundation. Rejected.

**Honesty.**
- *(A) Per-journey `source` + `note` text.* Every journey states plainly that it's one proposed
  reconstruction and cites where the route comes from — the route-level analogue of v3's per-place
  `status`/`confidence` surfacing. Readable, per-journey customizable, and forward-compatible with a
  future variants layer. **Chosen.**
- *(B) A boolean `is_reconstruction` enum.* Less informative (every route is one reconstruction in
  the minimal cut, so the flag is constant) and can't carry the source. Rejected.

**Source.**
- *(A) Scripture-derived.* The stop sequence is the public-domain biblical narrative (Acts 13–14 for
  Paul's first); place identifications/coordinates reuse the already-attributed v3 OpenBible data. No
  new external dependency; dating recorded as conventional/approximate. **Chosen.**
- *(B) An external public-domain atlas/handbook.* More scholarly provenance but a new source to
  attribute and a specific reconstruction to pin to. Unnecessary for the minimal cut. Rejected.

## Decision

A thin route layer over v3 places:

- **Schema:** `journeys(id, name, scripture, dating, source, note)` + `journey_stops(journey_id,
  ordinal, place_id REFERENCES places(id), reference)` with PK `(journey_id, ordinal)` and
  `idx_journey_stops_place` for the reverse direction. `place_id` is a **repeatable** column
  (return legs revisit cities) — the one deliberate departure from the place/topic junction shape,
  whose PK includes the place.
- **Data:** committed, hand-authored `data/journeys/journeys.json`. Scripture-derived itinerary;
  ids are hand-minted stable slugs (`paul-first`). Deterministic → byte-identical rebuilds.
- **Loader:** `bible_core.journeys.load_journeys` (cloning `geo.load_places`), wired into
  `build_database(journeys_dir=…)` and run **after** `load_places` (FK ordering). Hand-curated data
  is held to a higher bar than the skip-and-count datasets: it **fails loud** (`LoaderError`) on an
  unknown `place_id`, a duplicate journey id or ordinal, or empty stops.
- **Queries/API:** `list_journeys`/`get_journey`/`get_journey_stops`/`get_journeys_for_place` clone
  the place queries; three endpoints (`/v1/journeys`, `/v1/journeys/{id}` with embedded ordered
  stops, `/v1/places/{id}/journeys`) clone the place endpoints (pagination, ETag/304);
  `UnknownJourneyError` → 404 `unknown_journey`; the reverse reuses `UnknownPlaceError`.
- **Honesty:** per-journey `source` + `note` (option A); a stop inherits its place's coordinates and
  `status`, so unidentified stops surface null coords honestly.

## Consequences

- **No existing endpoint changes** — purely additive tables + new endpoints; the OpenAPI diff is
  three new paths. Maximum reuse of the audited places code → minimal new surface.
- **Geography is referenced, never rebuilt.** Stops are FKs into `places`; the v3 honesty model and
  disambiguation foundation carry through unchanged.
- **Bi-directional** by construction: `idx_journey_stops_place` serves place→journeys as
  `journey_id` serves journey→stops.
- **Provenance:** Scripture-derived itinerary documented in `data/SOURCES.md`; place data keeps its
  existing OpenBible CC BY 4.0 attribution. The committed `journeys.json` ships.
- **Deferred (held firm):** competing routes / route variants (a future `route_variants` layer and
  its own decision), per-segment dating debates, region grouping, and geometry rendering remain out
  of scope — addable later without changing this shape.
