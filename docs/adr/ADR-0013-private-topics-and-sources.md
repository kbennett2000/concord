# ADR-0013: A second topical source, private — `source` on every topic

**Status:** Accepted

<!--
Records how the topical Bible (ADR-0006) grows from one committed source (Nave's) to several,
one of them private (v8: the Tyndale Verse Finder, docs/v8/SPEC.md §4.5). Format mirrors
ADR-0001..0012: Context / Options / Decision / Consequences.
-->

## Context

v8 serves a study Bible the operator owns. Its Tyndale Verse Finder is a topical index: a topic,
then the references it gives. Kris's call (1 Oct 2026): it goes **beside Nave's in the topics
data**, as a second source, private like the rest of the book (© 2000 Tyndale House Publishers,
so nothing of it ships). ADR-0006 deferred "multi-source merging"; this ADR lifts that
deferral, without merging anything: each source keeps its own topics.

What had to be settled:

1. **Where a private source lives.** ADR-0006's loader reads one committed directory.
2. **How a client tells the sources apart and filters by one.** The `topics` table already
   carries `source TEXT NOT NULL` (ADR-0006), but no response shows it.
3. **How ids stay apart.** Topic ids are URL path segments (`/v1/topics/{id}`) and the table's
   primary key; a private source must never collide with a committed one.
4. **Nave's must not change** — the same ids, names, verses and order.

## Options considered

**Path.**
- *(A) A second directory, `data/private/topics/`, scanned after `data/topics/`.* ADR-0004's
  notes pattern: the private path sits under the dual-ignored `data/private/`, so a clean build
  bakes none of it and no ignore file changes. **Chosen.**
- *(B) A separate table and endpoints for private topics.* Duplicates four endpoints and the
  reverse lookup, and a client would query two places for "the topics of this verse". Rejected.

**Naming and filtering a source.**
- *(A) The source's display name, as stored* ("Nave's Topical Bible", "Tyndale Verse Finder"),
  matched exactly by `?source=`; `/v1/topics` lists every loaded source with its count, so a
  client never hardcodes a name. **Chosen** — no new field to keep in step with the name.
- *(B) A short key beside the name* (`naves`, `verse-finder`). Friendlier in a URL, but a second
  identity for every source, carried in the data and every response. Rejected as unneeded.

**Keeping ids apart.**
- *(A) A loader-checked `id_prefix` declared by the file.* Would only ever run on an operator's
  machine (CI and the public build have no private file). Rejected after review.
- *(B) A prefix by convention, enforced where it can fail.* A private source's ids carry a short
  prefix of its own (the Verse Finder's `vf-`); the loader rejects an id seen twice across both
  directories, naming both files; a committed-data test proves no committed id starts with
  `vf-`; the converter asserts every id it writes. **Chosen.**

## Decision

- **Paths:** `build_database(topics_dirs=…)` replaces `topics_dir`; the CLI scans
  `[data/topics, data/private/topics]` (`_default_topics_dirs`), public first, files sorted within
  each; an absent directory loads nothing.
- **A file is one source.** Its `source` names it; a source name may appear in one file only.
  A file holds at least one topic. Every id matches `^[a-z0-9-]+$` (a URL path segment) and every
  `section` `^[A-Z]$`. Any violation, or an id seen twice, fails the build naming the file (and
  the file that claimed the id or source first). `see_also` may name any topic id, unchecked, as
  before (143 of Nave's own targets dangle).
- **Responses (ADR-0009: appended, never reordered):**
  - `source` on `TopicSummary` (the browse and the reverse lookup), on `TopicDetail` (after
    `verse_count`) and on the topic-verses page (after `verses`).
  - `GET /v1/topics` gains `?source=` (exact, trimmed; combines with `q` and `section`; unknown →
    `400 unknown_source`, `detail: {source, available}` — the places `?type=` pattern) and appends
    `source` (the echoed filter, else null) and `sources`: every loaded source with its count
    under the same `q`/`section` (ignoring `source`), 0 included, ordered by name.
  - The four endpoints declare their bodies, so `docs/openapi.json` carries them.
- **Order and paging** (amended by V8-S7a, 2 Oct 2026, Kris's call): **one A–Z list.** The
  browse and the reverse lookup order by `name COLLATE NOCASE, id`: names compare ignoring ASCII
  case, so every source's topics interleave in one alphabet, and `id` breaks a tie between names
  equal but for case, so paging stays stable. `total` counts every source; `?source=` pages one
  source. Nave's own order moves in exactly one place: "ANGEL (a spirit)" now comes before
  "ANGEL (Holy Trinity)" (0-based positions 298 and 299 of 5,319). As S6a shipped it, the order
  was `name, id` in binary collation, which put Nave's all-capitals names before every
  mixed-case name of the same letter.
- **The reverse lookup** (`/v1/verses/{ref}/topics`) returns the union of every source's topics
  that cite the reference, each with its `source`; no `?source=` there.
- **No schema change.** The `source` column exists already.

## Consequences

- Nave's is unchanged apart from `source`: every list page, detail, verse page and a sample of
  reverse lookups were compared byte for byte, keys removed, on a public build and on one with a
  made-up private source (S6a's dev-notes).
- An older client sees the private source's topics mixed into the browse, sections and reverse
  lookups and ignores the new keys (Songbird's schemas are non-strict). Bodies are cached
  `immutable`, so a client may hold a pre-ADR body without `source`: treat `source`/`sources` as
  optional. Unfiltered pages, reverse lookups and `sources` change whenever the private data is
  rebuilt.
- **The one A–Z list (V8-S7a)** changed 61 of 42,813 responses on a public build (every list,
  section and `?source=` page, detail, verse page, and the reverse lookup of every cited verse and
  chapter, compared with `main` through `TestClient`): the five pages holding the ANGEL pair and
  the 35 verse and 21 chapter lookups that cite both, each by that one adjacent swap; the rest
  are byte-identical. Bodies are cached `immutable`, so a client holding one of those bodies from
  before keeps the old order until it fetches again (ADR-0009).
- **Licensing:** a clean checkout bakes zero private topics, proven by a test; `data/topics/`
  stays out of every ignore file, proven by another. User flow: `docs/v8/topics-ingest.md`.
- **Still deferred:** sub-topics, per-verse annotations, "see also" between topics with verses of
  their own. The Verse Finder's statements and "see also" pointers, which this contract can't
  hold, are served as an EMB document instead (docs/v8/SPEC.md §4.5).
