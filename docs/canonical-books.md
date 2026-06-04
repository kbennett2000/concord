# Canonical Books — Concord seed data

Authoritative reference data for the 66-book Protestant canon. This is the source of
truth for the **`books`** and **`book_aliases`** tables (Slice 1). Claude Code seeds
from this file — it does not invent codes, names, or aliases.

## Consumption contract

- **`books`** ← one row per entry below: `id` (USFM code), `name`, `testament`,
  `canonical_order`.
- **`book_aliases`** ← one row per alias, mapping the normalized alias → `book_id`.
- **`chapter_count` is NOT in this file.** The loader computes it from the actual verse
  data so it can never drift from reality (§8 of SPEC.md).
- Deuterocanonical books are intentionally absent. They arrive with the Catholic slice
  (`testament = DC`); the schema already supports them.

## Normalization contract (how aliases match)

Aliases are stored **normalized**, and the reference parser normalizes the incoming book
token the same way before lookup. Normalization is:

1. Lowercase.
2. Strip punctuation (periods, apostrophes).
3. Tokenize on whitespace.
4. **Leading ordinal → digit**: if the first token is an ordinal word, replace it with
   its digit — `i`/`first` → `1`, `ii`/`second` → `2`, `iii`/`third` → `3`. This is a
   leading-token step, applied before the tokens are joined, so `I Samuel` → `1samuel`
   while `Isaiah` stays `isaiah` (a bare leading `i` *inside* a word is never an ordinal).
5. Join the tokens, removing the internal whitespace (`1 sam` → `1sam`,
   `song of songs` → `songofsongs`).

Because of (4), the alias lists below carry only the digit-prefixed forms for numbered
books. Each book's own USFM code (lowercased) and its full name (normalized) are
included as aliases so both resolve.

### Two deliberate disambiguation choices

- **Judges vs Jude.** Bare `jud` resolves to **Jude**. Judges uses `jdg` / `judg` / `jg`
  only — never `jud`. (This follows common reference convention; the alternative
  silently sends `Jud 1:6` to the wrong book.)
- **Dropped ambiguous bare tokens.** `ez` (Ezra/Ezekiel), bare `ti` (Titus/Timothy), and
  bare `co` (Colossians/Corinthians) are intentionally omitted. Use the fuller forms
  listed instead. Numbered books always disambiguate via their digit prefix.

---

## Old Testament

| # | USFM | Name | Testament | Aliases (normalized) |
|---|---|---|---|---|
| 1 | GEN | Genesis | OT | gen, ge, gn, genesis |
| 2 | EXO | Exodus | OT | exo, ex, exod, exodus |
| 3 | LEV | Leviticus | OT | lev, le, lv, leviticus |
| 4 | NUM | Numbers | OT | num, nu, nm, nb, numbers |
| 5 | DEU | Deuteronomy | OT | deu, dt, deut, deuteronomy |
| 6 | JOS | Joshua | OT | jos, josh, jsh, joshua |
| 7 | JDG | Judges | OT | jdg, judg, jg, judges |
| 8 | RUT | Ruth | OT | rut, ru, rth, ruth |
| 9 | 1SA | 1 Samuel | OT | 1sa, 1sam, 1sm, 1s, 1samuel |
| 10 | 2SA | 2 Samuel | OT | 2sa, 2sam, 2sm, 2s, 2samuel |
| 11 | 1KI | 1 Kings | OT | 1ki, 1kgs, 1kin, 1k, 1kings |
| 12 | 2KI | 2 Kings | OT | 2ki, 2kgs, 2kin, 2k, 2kings |
| 13 | 1CH | 1 Chronicles | OT | 1ch, 1chr, 1chro, 1chron, 1chronicles |
| 14 | 2CH | 2 Chronicles | OT | 2ch, 2chr, 2chro, 2chron, 2chronicles |
| 15 | EZR | Ezra | OT | ezr, ezra |
| 16 | NEH | Nehemiah | OT | neh, ne, nehemiah |
| 17 | EST | Esther | OT | est, es, esth, esther |
| 18 | JOB | Job | OT | job, jb |
| 19 | PSA | Psalms | OT | psa, ps, pss, pslm, psalm, psalms |
| 20 | PRO | Proverbs | OT | pro, prov, pr, prv, proverbs |
| 21 | ECC | Ecclesiastes | OT | ecc, eccl, ec, qoh, eccles, ecclesiastes |
| 22 | SNG | Song of Solomon | OT | sng, song, sos, ss, cant, canticles, songofsolomon, songofsongs |
| 23 | ISA | Isaiah | OT | isa, is, isaiah |
| 24 | JER | Jeremiah | OT | jer, je, jr, jeremiah |
| 25 | LAM | Lamentations | OT | lam, la, lamentations |
| 26 | EZK | Ezekiel | OT | ezk, eze, ezek, ezekiel |
| 27 | DAN | Daniel | OT | dan, da, dn, daniel |
| 28 | HOS | Hosea | OT | hos, ho, hosea |
| 29 | JOL | Joel | OT | jol, jl, joel |
| 30 | AMO | Amos | OT | amo, am, amos |
| 31 | OBA | Obadiah | OT | oba, ob, obad, obadiah |
| 32 | JON | Jonah | OT | jon, jnh, jonah |
| 33 | MIC | Micah | OT | mic, mc, micah |
| 34 | NAM | Nahum | OT | nam, na, nah, nahum |
| 35 | HAB | Habakkuk | OT | hab, habakkuk |
| 36 | ZEP | Zephaniah | OT | zep, zph, zeph, zp, zephaniah |
| 37 | HAG | Haggai | OT | hag, hg, haggai |
| 38 | ZEC | Zechariah | OT | zec, zech, zc, zechariah |
| 39 | MAL | Malachi | OT | mal, ml, malachi |

## New Testament

| # | USFM | Name | Testament | Aliases (normalized) |
|---|---|---|---|---|
| 40 | MAT | Matthew | NT | mat, mt, matt, matthew |
| 41 | MRK | Mark | NT | mrk, mk, mr, mar, mark |
| 42 | LUK | Luke | NT | luk, lk, lu, luke |
| 43 | JHN | John | NT | jhn, jn, joh, john |
| 44 | ACT | Acts | NT | act, ac, acts |
| 45 | ROM | Romans | NT | rom, ro, rm, romans |
| 46 | 1CO | 1 Corinthians | NT | 1co, 1cor, 1c, 1corinthians |
| 47 | 2CO | 2 Corinthians | NT | 2co, 2cor, 2c, 2corinthians |
| 48 | GAL | Galatians | NT | gal, ga, galatians |
| 49 | EPH | Ephesians | NT | eph, ephes, ephesians |
| 50 | PHP | Philippians | NT | php, phil, pp, philippians |
| 51 | COL | Colossians | NT | col, cl, colossians |
| 52 | 1TH | 1 Thessalonians | NT | 1th, 1thes, 1thess, 1thessalonians |
| 53 | 2TH | 2 Thessalonians | NT | 2th, 2thes, 2thess, 2thessalonians |
| 54 | 1TI | 1 Timothy | NT | 1ti, 1tim, 1timothy |
| 55 | 2TI | 2 Timothy | NT | 2ti, 2tim, 2timothy |
| 56 | TIT | Titus | NT | tit, tt, titus |
| 57 | PHM | Philemon | NT | phm, phlm, philem, pm, philemon |
| 58 | HEB | Hebrews | NT | heb, hbr, hebrews |
| 59 | JAS | James | NT | jas, jm, jms, ja, james |
| 60 | 1PE | 1 Peter | NT | 1pe, 1pet, 1pt, 1p, 1peter |
| 61 | 2PE | 2 Peter | NT | 2pe, 2pet, 2pt, 2p, 2peter |
| 62 | 1JN | 1 John | NT | 1jn, 1joh, 1jo, 1j, 1john |
| 63 | 2JN | 2 John | NT | 2jn, 2joh, 2jo, 2j, 2john |
| 64 | 3JN | 3 John | NT | 3jn, 3joh, 3jo, 3j, 3john |
| 65 | JUD | Jude | NT | jud, jd, jude |
| 66 | REV | Revelation | NT | rev, re, rv, revelation |

---

## Review checklist (for Slice 1)

- 66 books, `canonical_order` 1–66, no gaps or duplicates.
- Every `id` is a valid 3-character USFM code.
- No alias maps to two different books (the disambiguation notes above are the only
  intentional near-collisions — verify they resolved as documented).
- Each book's lowercased USFM code and normalized full name both appear in its aliases.
- A round-trip test: for each book, the normalized full name resolves back to its `id`.
