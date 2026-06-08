# Data Sources & Attribution

Provenance and licensing for the data committed to this repo. The committed
translations are public domain; the cross-reference dataset is included under its own
license with attribution.

**Source PDFs are not in this repo.** The JSON in `data/translations/` was derived from
source editions; those source files are archived separately. This file records *where
each translation came from* in text form — that's the provenance worth keeping, not the
binaries.

**Non-distributable translations are not listed here.** Any translation in the
gitignored `data/private/` directory is local-only and intentionally absent from this
public record.

---

## Translations (`data/translations/`)

One row per committed translation. Source-edition detail below is drawn from each file's
JSON `copyright` metadata; all are freely redistributable (public domain, except BSB,
whose publisher dedicates the text to free use/redistribution).

| ID | Full name | Source edition / origin | Notes |
|---|---|---|---|
| AKJV | American King James Version | Public-domain modernization of the KJV | Public domain |
| ASV | American Standard Version | 1901 | Public domain |
| BSB | Berean Standard Bible | Bible Hub / Berean Bible Translation Committee | Publisher-dedicated to free use & redistribution |
| CPDV | Catholic Public Domain Version | Ronald L. Conte Jr. | Public domain |
| DBT | Darby Bible Translation | 1890 | Public domain |
| DRB | Douay-Rheims Bible | Challoner Revision | Public domain |
| ERV | English Revised Version | 1885 | Public domain |
| JPS | JPS Tanakh / Weymouth NT | JPS Tanakh 1917 (OT) + Weymouth NT 1903 (NT) | Public domain |
| KJV | King James Version | Standard public-domain text | Public domain |
| SLT | Smith's Literal Translation | 1876 | Public domain |
| WBT | Webster's Bible Translation | 1833 | Public domain |
| WEB | World English Bible | Standard public-domain text | Public domain |
| YLT | Young's Literal Translation | 1898 | Public domain |

> The `attribution` column in the `translations` table is populated from this record
> (or the translation JSON metadata) during the loader slice.

## Cross-references (`data/cross-references/`)

| Field | Value |
|---|---|
| File | `cross_references.txt` (TSV: `From Verse` · `To Verse` · `Votes`; 344,799 rows) |
| Source | OpenBible.info cross-reference dataset — <https://www.openbible.info/labs/cross-references/> |
| License | Creative Commons Attribution (CC BY) |
| Attribution | **Cross-reference data courtesy of [OpenBible.info](https://www.openbible.info/labs/cross-references/), licensed under a Creative Commons Attribution (CC BY) license.** |

This dataset is redistributable under CC BY, so it is committed to the repo with the
attribution above. The file's header line carries `#www.openbible.info CC-BY <date>`. The
attribution line **must appear in the README** (Slice 9).

If the cross-reference dataset's license does not permit redistribution, it must move to
`data/private/` (gitignored) and be loaded locally only.

## Geography / places (`data/geography/`)

| Field | Value |
|---|---|
| Files | `ancient.jsonl` (biblical places, with verse links and confidence) + `modern.jsonl` (modern locations with coordinates) |
| Source | OpenBible.info Bible-Geocoding-Data — <https://github.com/openbibleinfo/Bible-Geocoding-Data> |
| License | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| Attribution | **Place data courtesy of [OpenBible.info](https://github.com/openbibleinfo/Bible-Geocoding-Data), licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license.** |

This dataset is redistributable under CC BY 4.0, so the source `.jsonl` files are committed
to the repo with the attribution above. The geography loader (`bible_core.geo`) ingests a
**disciplined subset** of these files into the `places` + `place_verses` tables (SPEC v3
§4); the bulk of the dataset's scholarly apparatus is deliberately not used. The attribution
line **must appear in the README** (Slice V3-S2).

## Public-domain translator's notes (`data/notes/`) — committed & shipped

| Field | Value |
|---|---|
| Files | `data/notes/<TRANSLATION>.json` (one per translation; see [docs/v4/notes-ingest.md](../docs/v4/notes-ingest.md) for the JSON shape) |
| WEB | `data/notes/WEB.json` — the World English Bible's own translator footnotes |
| Source | eBible.org **engwebp** (World English Bible, Protestant Edition), USFM distribution — <https://ebible.org/find/details.php?id=engwebp> (download: <https://ebible.org/Scriptures/engwebp_usfm.zip>) |
| License | **Public domain** — "The World English Bible is in the Public Domain" (the footnotes are PD along with the text; `data/translations/WEB.json` declares the same) |
| Derivation | Footnotes **only** (not verse text) extracted by [scripts/convert_web_footnotes.py](../scripts/convert_web_footnotes.py); verse-level anchor (`char_offset` 0), `type` null, no cross-references for v1 (ADR-0004) |
| Status | **Committed and baked into the public image** — NOT gitignored/dockerignored |

This path (ADR-0004) is the public, ship-by-default counterpart to the private notes below: the
WEB's footnotes are public domain and *meant* to ship, so the derived `data/notes/WEB.json` is
committed and baked into `bible.db` by the loader (which scans `data/notes/` alongside
`data/private/notes/`). The raw USFM is re-derivable and not committed (documented above). See
[../THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES).

## Translator's notes (`data/private/notes/`) — NOT committed

| Field | Value |
|---|---|
| Files | `data/private/notes/<TRANSLATION>.json` (one per translation; see [docs/v4/notes-ingest.md](../docs/v4/notes-ingest.md) for the JSON shape) |
| Source | User-supplied — parsed locally from a translation the user legally owns (e.g. the NET Bible) |
| License | Translation-specific. NET notes are **© Biblical Studies Press, "all rights reserved"** — **not redistributable** |
| Status | **Gitignored + dockerignored** (`data/private/`); never committed, never baked into the public image |

Translator's notes (SPEC v4) follow the same never-distributed pipeline as restricted
*translations*: the richest source (NET) is copyrighted and may not be redistributed, so its
notes are **user-supplied** and live only under the gitignored `data/private/` tree. The notes
loader (`bible_core.notes`) bakes them into a *local* `bible.db`; the published image ships
**zero private** notes (proven by `test_notes_loader.test_clean_build_bakes_public_notes_but_zero_private_notes`
and the dual-ignore guard `test_licensing_safety`). The MIT-licensed parser that produces the
notes JSON is code only — its restricted *output* never enters this repo. See
[../THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES).
