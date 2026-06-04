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
| Source | _(e.g. OpenBible.info cross-reference dataset)_ |
| License | _(e.g. CC BY 4.0)_ |
| Attribution | _(required credit line — must travel with the data and appear in the README)_ |

If the cross-reference dataset's license does not permit redistribution, it must move to
`data/private/` (gitignored) and be loaded locally only.
