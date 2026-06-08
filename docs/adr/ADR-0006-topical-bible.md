# ADR-0006: A browsable, bi-directional topical Bible (Nave's)

**Status:** Accepted

<!--
Records how a topical Bible (topics → verses, verse → topics) is added by cloning the v3
geography (places) pattern. Format mirrors ADR-0001..0005: Context / Options / Decision /
Consequences.
-->

## Context

Add a topical Bible: browse topics → curated verse lists, and look up a verse → the topics it
appears under. This is structurally **the geography (places) feature again** — a catalogue table
with a verse-link junction table serving both directions — so the cheapest, most consistent design
is to mirror it exactly: `topics` + `topic_verses` (cloning `places` + `place_verses`), four
endpoints (`/v1/topics`, `/v1/topics/{id}`, `/v1/topics/{id}/verses`, `/v1/verses/{ref}/topics`)
cloning the place endpoints, pure SQLite in bible-core, no ML.

**Source.** Nave's Topical Bible (Orville J. Nave, 1897) is public domain. The machine-readable
edition used is **BradyStephenson/bible-data → `NavesTopicalDictionary.csv`**, licensed **CC BY
4.0** over the compilation. Concord already ships CC BY 4.0 datasets (OpenBible cross-references and
geography) with attribution, so this is an established provenance pattern — the content **ships**
(committed `data/topics/`, scanned by the loader; **not** the private path). 5,319 topics; the CSV's
`entry` column carries references in prose using USFM-style codes.

Two design questions had real choices:
1. **Nave's "See X" redirects** (587 topics, e.g. `ANXIETY → "-See CARE"`) have no verses of their
   own — how should they appear?
2. **Topic structure** — Nave's entries nest sub-headings ("-WORLDLY", "-REMEDY FOR", …). Flat or
   hierarchical?

## Options considered

**Redirects.**
- *(A) `see_also` pointer, zero verses.* A redirect topic stores `see_also` = the target's id and
  carries no verses; `q=anxiety` still finds ANXIETY (with `see_also: care`), and the verses live
  under CARE. Faithful to the source, no duplication. **Chosen.**
- *(B) Follow "See" and materialise the target's verses.* ANXIETY would return CARE's verses and a
  verse would reverse-map to both. Makes `anxiety` directly useful but duplicates links and makes
  the reverse index noisier/less honest (synonyms multiply). Rejected for v1.
- *(C) Drop redirect-only topics.* Loses discoverability (`q=anxiety` finds nothing). Rejected.

**Structure.**
- *(A) Flat — one verse union per topic.* Sub-headings are flattened; a topic owns the union of all
  verses cited anywhere in its entry. Simple, matches the places shape. **Chosen.**
- *(B) Hierarchical sub-topics.* Richer, but a different data model than places and unjustified for
  v1. Deferred.

**Parsing.** Reference extraction from prose is done in a committed parser script
(`scripts/convert_naves_topics.py`, the WEB-footnotes precedent), emitting clean committed data;
the loader just validates + inserts. Verse-level references only — **chapter-only** refs (`GEN 1`)
are skipped (whole-chapter expansion would bloat the table and make the reverse index noisy);
unresolvable/prose tokens are skipped + counted.

## Decision

Clone the places pattern for topics:

- **Schema:** `topics(id, name, section, see_also, source)` + `topic_verses(topic_id, book_id,
  chapter, verse)` with the composite PK (dedups links) and `idx_topic_verses_bcv` for the reverse
  direction — exactly mirroring `places`/`place_verses`.
- **Data:** committed `data/topics/naves.json`, produced by `scripts/convert_naves_topics.py` from
  the CC BY 4.0 CSV. Book codes resolve through Concord's alias table (parsed from
  `docs/canonical-books.md` + a tiny documented override for `1JHN→1JN` etc.). Deterministic.
- **Loader:** `bible_core.topics.load_topics` (cloning `geo.load_places`), wired into
  `build_database(topics_dir=…)`; `main()` sets `data/topics`. Skips + counts unresolved links.
- **Queries/API:** `list_topics`/`get_topic`/`get_topic_verses`/`get_topics_for_reference` clone
  the place queries; the four endpoints clone the place endpoints (`include_text`, pagination,
  ETag/304); `UnknownTopicError` → 404 `unknown_topic`. A redirect or empty topic returns
  `verses: []` (200), and a valid reference citing no topic returns an empty list (200).
- **Redirects:** `see_also` pointer with zero verses (option A). **Flat** topics (option A).

## Consequences

- **No existing endpoint changes** — purely additive tables + new endpoints; the OpenAPI diff is
  four new paths. Maximum reuse of the audited places code → minimal new surface.
- **Bi-directional** by construction: the `topic_verses` PK + `idx_topic_verses_bcv` serve
  topic→verses and verse→topics, as `place_verses` does.
- **Provenance:** CC BY 4.0 attribution in `data/SOURCES.md`, `THIRD_PARTY_NOTICES`, and the README,
  alongside the existing OpenBible CC BY entries. The raw CSV is re-derivable and not committed; the
  derived `data/topics/naves.json` is committed and ships.
- **Deferred:** hierarchical sub-topics, multi-source merging (Torrey's, etc.), and chapter-level
  topic links remain out of scope — addable later without changing this shape.
