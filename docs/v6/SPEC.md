# Concord v6 — Word study: Strong's lexicon, original-language texts & tagged tokens (design spec)

Concord learns to support **word study** — answering "what does the Greek word behind *love* in
John 3:16 mean?", "every verse where *agapē* (G26) appears", and "show me the tagged tokens of a
verse". This is a **Scripture-domain capability**, so it belongs in Concord (the foundation), not
in any app on top of it.

All lookup is **exact data → pure SQLite → `bible-core`**, *not* `bible-semantic` — there are no
embeddings here; Strong's numbers, lemmas, and morphology are precise reference data. v1 (read
API), v2 (semantic search), v3 (geography), v4 (translator's notes), and v5 (search completeness)
are shipped and unchanged. This is **Concord v6** (v5 = search completeness; the next milestone
folder number). Journeys / routes remains the deferred next frontier and is **not** this work.

This is delivered as a **sequence of slices**, each its own PR. Acceptance for the shippable
word-study cut (S1–S4) is Greek-NT-first; the Hebrew OT follows in S5.

---

## 1. Two ideas, both reusing what exists

1. **Original-language text as a translation.** The Greek NT (`SBLGNT`, later Hebrew `OSHB`) loads
   through the existing translations/verses machinery — it is just another committed
   `data/translations/*.json` file, so `/v1/verses/{ref}?translation=SBLGNT` and
   `/v1/translations` work with no new endpoints. The Greek NT needs **zero loader changes**
   because its NRSV chapter counts match the standard English NT.
2. **Additive lexicon + tagging, mirroring places/topics.** Two new tables — `strongs_entries`
   (the lexicon) and `word_tokens` (per-verse tagged tokens) — mirror the
   `places`/`place_verses` and `topics`/`topic_verses` pattern: an entry table plus a link table
   whose composite PK and reverse index serve **both directions** (Strong's→verses and
   verse→tokens).

## 2. Source — STEPBible-Data (CC BY 4.0)

One provider for everything, consistent with how Concord already ships CC BY data (cross-refs,
geography, Nave's): **STEPBible-Data** (github.com/STEPBible/STEPBible-Data, CC BY 4.0), which
tags every word with a disambiguated Strong's number, morphology, lemma, transliteration, and
gloss.

| Need | File | Slice |
|---|---|---|
| Greek NT text + tokens | `TAGNT` (Translators Amalgamated Greek NT) | S1, S3 |
| Greek lexicon | `TBESG` (Translators Brief lexicon of Extended Strongs for Greek) | S2 |
| Hebrew OT text + tokens | `TAHOT` | S5 |
| Hebrew lexicon | `TBESH` | S5 |

The raw STEPBible `.txt` files are re-derivable and **not committed** (gitignored + dockerignored
`data/original/`); the committed parsers under `scripts/` emit slimmed **derived JSON** that
ships. STEPBible asks that others refer to github.com/STEPBible as the canonical source — the
attribution (in `data/SOURCES.md`, `THIRD_PARTY_NOTICES`, README) does. See ADR-0007.

## 3. Schema (additive)

```sql
strongs_entries(strongs_id PK, language, lemma, transliteration, gloss, definition, source)
word_tokens(text_id, book_id, chapter, verse, position, surface_form, strongs_id, morph_code,
            PRIMARY KEY (text_id, book_id, chapter, verse, position))
  + idx_word_tokens_strongs (strongs_id)                       -- Strong's → verses
  + idx_word_tokens_bcv (text_id, book_id, chapter, verse)     -- verse → tokens
```

**Strong's id normalization (flat v1):** key on the collapsed base — `G0026`→`G26`, `H0430`→
`H430`, `G2455N`→`G2455` (letter + number, no zero-padding, no disambiguation suffix); one
lexicon entry per base (primary sense). Disambiguated senses are **deferred** (the "flat topics"
precedent). `word_tokens.strongs_id` stores the same base so the reverse link joins; it is a plain
column (no FK) so a token's Strong's needn't appear in the collapsed lexicon.

## 4. Endpoints (mirror places; S2 + S4)

- `GET /v1/strongs` — browse the lexicon (`q` over lemma/gloss, optional `language`, pagination).
- `GET /v1/strongs/{id}` — one entry (404 `unknown_strongs`).
- `GET /v1/strongs/{id}/verses` — occurrences (the Strong's→verses direction); `?text=` (default
  `SBLGNT`), `include_text` + `?translation=` hydration, pagination.
- `GET /v1/verses/{ref}/words` — the tagged tokens of a passage (verse→tokens direction): surface
  form, Strong's, morphology, and (joined from the lexicon) lemma/translit/gloss.

The original-language *text* itself is served by the existing `/v1/verses` and `/v1/translations`.

## 5. Slices

- **V6-S1 — Greek NT as a translation. ✅** `scripts/convert_step_tagnt.py` →
  `data/translations/SBLGNT.json` (7,917 verses, the SBL-edition word selection from TAGNT,
  NFC-normalized). No schema change. `/v1/verses/John 3:16?translation=SBLGNT` returns the Greek;
  `/v1/translations` lists it.
- **V6-S2 — lexicon. ✅ (this slice)** `strongs_entries` + loader + `convert_strongs_lexicon.py`
  (TBESG → `data/strongs/lexicon.json`, 10,846 entries keyed on the collapsed-base Strong's number)
  + `GET /v1/strongs` & `/v1/strongs/{id}` + `UnknownStrongsError`. Acceptance ①: `/v1/strongs/G26`
  → ἀγάπη "love".
- **V6-S3 — tokens + queries. ✅ (this slice)** `word_tokens` table + `load_word_tokens`;
  `convert_step_tagnt.py` extended to also emit `data/strongs/tokens-sblgnt.json` (137,121 tagged
  tokens: surface form, collapsed Strong's, morph); `get_strongs_verses` (Strong's→verses) and
  `get_words_for_reference` (verse→tokens, lexicon gloss joined) tested in `bible-core`. No new
  endpoints — those are S4.
- **V6-S4 — the two remaining endpoints.** `/v1/strongs/{id}/verses` + `/v1/verses/{ref}/words`.
  Acceptance ② & ③.
- **V6-S5 — Hebrew OT.** `TAHOT` → `OSHB.json` + tokens; `TBESH` → lexicon. Relax
  `_update_chapter_counts` to group by `translations.versification` (Hebrew chapter counts differ
  — Joel 4≠3, Malachi 3≠4); add `direction` (rtl) to the translation JSON format + loader +
  `/v1/translations`.

## 6. Out of scope (held)

- **English-word → original-token alignment** ("click an English word → its Greek") — a separate
  per-translation alignment project; word study lands fully useful without it.
- Disambiguated Strong's senses / multi-sense lexicon splits.
- Hebrew prefix/suffix sub-token splitting (tokens stay whole-word in v1).
- Journeys / routes (the standing deferred frontier).
