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

All public domain. Fill in one row per committed translation.

| ID | Full name | Source edition / origin | Notes |
|---|---|---|---|
| KJV | King James Version | _(source)_ | Public domain |
| WEB | World English Bible | _(source)_ | Public domain |
| _…_ | _…_ | _…_ | _…_ |

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
