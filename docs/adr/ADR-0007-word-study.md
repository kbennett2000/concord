# ADR-0007: Word study — Strong's lexicon, original-language texts & tagged tokens (v6)

**Status:** Accepted

<!--
Records the architecture for Concord v6 (word study): original-language texts loaded as
translations, plus an additive Strong's lexicon and per-verse tagged tokens cloning the v3
geography (places) pattern. Format mirrors ADR-0001..0006: Context / Options / Decision /
Consequences. Decided up front for the whole milestone; implemented across slices S1–S5.
-->

## Context

Add **word study**: a Strong's lexicon, the original-language texts, and per-verse tagged tokens —
answering "the Strong's entry for *agapē* (G26)", "every verse where G26 appears", and "the tagged
tokens of John 3:16". All lookup is **exact data → pure SQLite → bible-core**, not bible-semantic
(no embeddings; Strong's/lemma/morphology are precise reference data). This is **Concord v6** (v5 =
search completeness; the next milestone folder). Designed in [`docs/v6/SPEC.md`](../v6/SPEC.md).

Two structural ideas, both reusing audited machinery:
1. **Original-language text as a translation** — the Greek NT (`SBLGNT`, later Hebrew `OSHB`) loads
   through the existing translations/verses pipeline; it is just another `data/translations/*.json`.
2. **Lexicon + tagging as the places pattern again** — `strongs_entries` (catalogue) +
   `word_tokens` (verse-link junction) mirror `places`/`place_verses`, serving both directions.

Real choices had to be made on **source**, **shipping mechanism**, **Greek-NT identity**,
**Strong's id granularity**, and **versification sequencing**.

## Options considered

**Source (lexicon + tagged text).**
- *(A) All-STEPBible-Data, CC BY 4.0.* `TBESG`/`TBESH` lexicons + `TAGNT`/`TAHOT` tagged texts —
  one provider, Strong's + morphology + lemma/translit/gloss inline, matching Concord's existing
  CC BY data (cross-refs, geography, Nave's). **Chosen.**
- *(B) Public-domain text + STEPBible lexicon.* Byzantine Robinson-Pierpont (PD) text/tokens, but
  the only clean modern Strong's dictionary alternative (OpenScriptures) is **GPL-3.0**
  (unshippable), so the lexicon would still be STEPBible. Less coherent; Byzantine less
  "modern-standard" than SBL. Rejected.
- *(C) Fully public-domain.* Removes all redistribution ambiguity but the PD Strong's data is
  thin/messy vs STEPBible's curated extended-Strong's lexicon. Rejected.

**Shipping mechanism for the STEPBible-derived data.** STEPBible's CC BY files carry a polite
"refer others to our repo; please do not redistribute it yourself" note (CC BY legally permits
redistribution regardless).
- *(A) Commit the slimmed derived JSON* (like Nave's/geo), bake at build; raw `.txt` re-derivable
  and not committed; honour the note with prominent attribution + linking github.com/STEPBible.
  **Chosen** — consistent with every other Concord data feature.
- *(B) Fetch-at-build, gitignored* (like the ONNX model weights). More faithful to "refer to our
  repo" but breaks the committed-data pattern and offline-build friendliness. Rejected.

**Greek-NT identity.** `TAGNT` is an *amalgamated* text marking, per word, which printed editions
contain it. Keep only the **SBL-edition** words (id `SBLGNT`) — recognizable, and the user's stated
acceptance verb. The spelling is STEPBible's (NA-based), so this is the SBL *word selection*, not a
byte-faithful printed-SBLGNT reproduction; the `copyright` metadata and attribution say so. Text is
**NFC-normalized** (the canonical form for a Greek text API). Alternative (load the full
amalgamated/NA-base text under an obscure id) rejected as less recognizable.

**Strong's id granularity.** Key on the **collapsed base** number (`G0026`→`G26`, `G2455N`→`G2455`)
— one lexicon entry per base (primary sense); tokens store the same base so the reverse link joins.
Disambiguated senses (`G0011G`, multi-sense splits) are **deferred** — the "flat topics" precedent.

**Versification sequencing.** The loader's `_update_chapter_counts` requires *every* translation to
agree on chapter count per book. The Greek NT's NRSV chapter counts match the English NT, so
**SBLGNT loads with zero loader changes**. The Hebrew OT does **not** (Joel 4≠3, Malachi 3≠4), so
the OT is the **last slice (S5)**, which relaxes the check to group by `translations.versification`
(the column already exists, unused) and adds RTL `direction` support.

## Decision

- **Source:** all-STEPBible-Data (CC BY 4.0) — `TAGNT`/`TAHOT` texts+tokens, `TBESG`/`TBESH`
  lexicons. Committed derived JSON; raw `.txt` under gitignored + dockerignored `data/original/`.
- **OL as translation:** the Greek NT loads as `SBLGNT` (SBL-edition word selection from TAGNT,
  NFC-normalized) via `scripts/convert_step_tagnt.py` → `data/translations/SBLGNT.json`, served by
  the existing `/v1/verses` and `/v1/translations` — no schema or loader changes (S1).
- **Schema (additive, S2–S3):** `strongs_entries(strongs_id PK, language, lemma, transliteration,
  gloss, definition, source)` + `word_tokens(text_id, book_id, chapter, verse, position,
  surface_form, strongs_id, morph_code)` with composite PK + `idx_word_tokens_strongs` (Strong's→
  verses) and `idx_word_tokens_bcv` (verse→tokens), mirroring `places`/`place_verses`.
- **Endpoints (S2 + S4):** `/v1/strongs`, `/v1/strongs/{id}`, `/v1/strongs/{id}/verses`,
  `/v1/verses/{ref}/words` clone the place endpoints; `UnknownStrongsError` → 404 `unknown_strongs`.
- **Strong's id:** collapsed base; flat (disambiguated senses deferred).
- **Hebrew OT (S5):** `TAHOT`/`TBESH`; versification grouped per `translations.versification`; RTL.

## Consequences

- **Maximum reuse, minimal new surface.** The Greek text rides the existing translations pipeline;
  the lexicon/tokens clone the audited places code. S1's only "changes" to existing code are three
  integration-test counts (13→14 translations) — no production-code edits.
- **Bi-directional** by construction: `word_tokens`' PK + indexes serve Strong's→verses and
  verse→tokens, as `place_verses` does.
- **Provenance:** CC BY 4.0 attribution to STEP Bible / Tyndale House (and SBL/Logos for SBLGNT) in
  `data/SOURCES.md`, `THIRD_PARTY_NOTICES`, and the README, alongside the existing CC BY entries.
  The raw STEPBible files are re-derivable and not committed; the derived JSON ships.
- **Deferred (held):** English-word→original-token alignment, disambiguated Strong's senses, and
  Hebrew prefix/suffix sub-token splitting — addable later without changing this shape.
