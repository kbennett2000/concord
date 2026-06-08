# Data Sources & Attribution

Provenance and licensing for the data committed to this repo. The committed English
translations are public domain; the cross-reference, geography, topical, and
original-language datasets are included under their own licenses with attribution.

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
whose publisher dedicates the text to free use/redistribution, and SBLGNT, CC BY 4.0 —
see [Original-language texts](#original-language-texts-datatranslationssblgntjson) below).

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
| SBLGNT | SBL Greek New Testament | STEPBible TAGNT (SBL edition word-selection) | **CC BY 4.0** — see below |

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

## Topical Bible (`data/topics/`)

| Field | Value |
|---|---|
| Files | `naves.json` (topics → curated verse links), derived by [scripts/convert_naves_topics.py](../scripts/convert_naves_topics.py) |
| Work | Nave's Topical Bible (Orville J. Nave, 1897) — the underlying topical work is **public domain** |
| Source edition | BradyStephenson/bible-data — `NavesTopicalDictionary.csv` — <https://github.com/BradyStephenson/bible-data> |
| License | Creative Commons Attribution 4.0 International (CC BY 4.0) over the compilation |
| Attribution | **Topical data from [Nave's Topical Bible](https://github.com/BradyStephenson/bible-data) (public domain; 1897), via BradyStephenson/bible-data, licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0) license.** |

The 1897 work is public domain; the machine-readable compilation is CC BY 4.0, redistributable
with attribution (same treatment as the cross-reference and geography datasets above). The parser
extracts **verse-level** references only (chapter-only and unresolvable refs are skipped + counted)
into the committed `data/topics/naves.json`, which the loader (`bible_core.topics`) bakes into the
`topics` + `topic_verses` tables. The **raw CSV is re-derivable and not committed**; the derived
JSON is committed and ships. The attribution line **must appear in the README**.

## Original-language texts (`data/translations/SBLGNT.json`)

| Field | Value |
|---|---|
| File | `data/translations/SBLGNT.json` — the Greek NT loaded as an ordinary translation, derived by [scripts/convert_step_tagnt.py](../scripts/convert_step_tagnt.py) |
| Source | STEPBible-Data — `TAGNT` (Translators Amalgamated Greek NT) — <https://github.com/STEPBible/STEPBible-Data> |
| License | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| Attribution | **Greek New Testament data created by [STEPBible.org](https://github.com/STEPBible/STEPBible-Data) based on work at Tyndale House Cambridge, licensed CC BY 4.0; the SBLGNT is © 2010 Society of Biblical Literature & Logos Bible Software, CC BY 4.0.** |

The original-language word-study feature (SPEC v6) loads the Greek NT as a translation so it
reads through the existing `/v1/verses` and `/v1/translations` machinery. STEPBible's TAGNT is an
*amalgamated* text marking, per word, which printed editions contain it; the parser keeps only the
**SBL edition** words (so e.g. the Textus-Receptus-only αὐτοῦ in John 3:16 is dropped and the
TR/Byz-only John 5:4 is absent) and joins them, NFC-normalized, into verse text. This is the SBL
*word selection* with STEPBible's (NA-based) spelling, not a byte-faithful reproduction of the
printed SBLGNT — the `copyright` metadata says so. NRSV versification (NT chapter counts are
standard, so it loads beside the English Bibles). The **raw `TAGNT` files are re-derivable and not
committed** — they live under the gitignored + dockerignored `data/original/`; only the derived
`SBLGNT.json` is committed and ships. STEPBible asks that others refer to github.com/STEPBible as
the canonical source, which the attribution above does. See [../THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES).
The tagged tokens (`word_tokens`) land in a later v6 slice.

## Strong's lexicon (`data/strongs/`)

| Field | Value |
|---|---|
| File | `data/strongs/lexicon.json` (Strong's number → lemma, transliteration, gloss, definition), derived by [scripts/convert_strongs_lexicon.py](../scripts/convert_strongs_lexicon.py) |
| Source | STEPBible-Data — `TBESG` (Translators Brief lexicon of Extended Strongs for Greek) — <https://github.com/STEPBible/STEPBible-Data> |
| License | Creative Commons Attribution 4.0 International (CC BY 4.0) |
| Attribution | **Lexicon data created by [STEPBible.org](https://github.com/STEPBible/STEPBible-Data) based on work at Tyndale House Cambridge (the Brief lexicon draws on Abbott-Smith), licensed CC BY 4.0. The underlying Strong's numbering (1890) is public domain.** |

The word-study feature (SPEC v6) loads the Greek Strong's lexicon into the additive
`strongs_entries` table, served by `/v1/strongs` and `/v1/strongs/{id}`. Each entry is keyed on the
**collapsed-base** Extended Strong's number (`G0026` → `G26`); where TBESG splits a number into
disambiguated senses (`G0001G`, `G0001H`), the first/primary sense is kept (later slices may expose
the splits). The HTML in the definition column is stripped to plain text. The **raw `TBESG` file is
re-derivable and not committed** — it lives under the gitignored + dockerignored `data/original/`;
only the derived `lexicon.json` is committed and ships. STEPBible asks that others refer to
github.com/STEPBible as the canonical source, which the attribution above does. See
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
**zero** notes (proven by `test_notes_loader.test_clean_build_with_no_private_data_yields_zero_notes`
and the dual-ignore guard `test_licensing_safety`). The MIT-licensed parser that produces the
notes JSON is code only — its restricted *output* never enters this repo. See
[../THIRD_PARTY_NOTICES](../THIRD_PARTY_NOTICES).
