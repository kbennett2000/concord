# ADR-0009: Adding fields to an already-published `/v1` response

**Status:** Accepted

<!--
Records when an existing /v1 response may grow new fields rather than a new endpoint, prompted
by issue #69 (verse labels on word-study tokens). Format mirrors ADR-0001..0008:
Context / Options / Decision / Consequences.
-->

## Context

Issue #69: `GET /v1/verses/{ref}/words` returns a flat token list carrying `position`,
`surface_form`, `strongs_id`, `morph_code` and the joined lexicon fields — but no verse label.
For a multi-verse reference (`John 21:15-17`, 90 tokens across three verses) the only
boundary signal is `position` restarting at 1, so a client cannot tell which verse a token
belongs to. concord-mcp's `word_study` tool works around it by splitting on position resets and
labelling blocks only when the count happens to match the requested reference — a guard that
gives up on token-less verses, whole-chapter refs and cross-chapter spans.

The data was never missing: `word_tokens` stores `book_id`, `chapter`, `verse` on every row, and
`get_words_for_reference` already ordered by them. Only the SELECT list and the response model
omitted them.

The awkward part is precedent, not implementation. This repo has said three slightly different
things about changing a published response:

- **ROADMAP rule 1** — "Additive only… Prefer a *new* endpoint over mutating an existing
  response; if you must add a field, additive fields only."
- **ADR-0005** rejected an additive field on `/v1/chapters` in favour of a dedicated endpoint,
  because "`/v1/chapters` is part of the `/v1` contract (the committed `docs/openapi.json`), so
  any change there carries contract risk for a purely additive feature."
- **ADR-0003** did widen `/v1/search`, but only behind a new `?translations=` parameter, with the
  old response preserved **byte-for-byte** when the parameter is absent.

Read strictly, ADR-0005 would push #69 toward a second endpoint
(`/v1/verses/{ref}/words/grouped`, or similar) and ADR-0003 toward an opt-in flag. Both are
disproportionate to "the row already knows its verse".

## Options considered

- **(A) Append the fields unconditionally to the existing token object. Chosen.** A JSON object
  gaining keys breaks no client that reads the keys it asked for. The endpoint has no modes, so
  there is no parameter for an opt-in to hang off.
- **(B) A new endpoint or a `?format=grouped` variant.** Follows ADR-0005's letter, but yields a
  second shape to document, test and keep in sync forever — for data that belongs on the token
  it describes. Grouping is a client-side `groupby` once the labels exist.
- **(C) An opt-in parameter (ADR-0003's shape), old bytes preserved when absent.** Defensible,
  but ADR-0003's flag existed because single- and multi-translation search are genuinely
  different *modes*. Here there is one mode; a flag would exist only to avoid changing bytes,
  and every caller would have to learn to set it.

## Decision

**New keys may be added to an existing `/v1` response object without a new endpoint or an opt-in
flag — provided they are _appended_, so no already-published key changes position.**

ADR-0005's new-endpoint bias governs *new features* that would otherwise distort a response's
shape (per-translation headings nested inside a multi-translation chapter). It does not govern
*completing* an object with an attribute of the thing it already represents. ADR-0003's
append-and-omit discipline generalises: append, never reorder, never repurpose.

Concretely, for #69: each token of `/v1/verses/{ref}/words` gains `book`, `chapter`, `verse` and
`reference`, declared after `gloss`. Note this is the reverse of the field order in
`TranslatorNote`, `StrongsVerse`, `SearchHit` and the other verse-labeled models, which all lead
with the label — those models were *born* that way; this one is being widened, and the seven
shipped fields keep their positions. A test pins the token key order so the next widening is a
choice rather than a side effect.

## Consequences

- **The `/v1` promise holds.** No key removed, renamed, retyped or moved. A client reading
  `token["position"]` is unaffected; a client that enumerates keys sees four more at the end.
- **The ETag takes care of itself.** It is hashed from the emitted bytes (`caching.py`), so it
  changes with the body; there is no server-side response cache to purge.
- **But `immutable` caching hides the change from anything that caches.** These responses ship
  `Cache-Control: public, max-age=31536000, immutable`, which tells a client not to revalidate
  *even on reload*. A browser or proxy holding an old `/words` body can serve the label-less
  shape for up to a year, with no signal that its server was upgraded. This is the real cost of
  widening an endpoint whose entire caching story is "this never changes", and it argues for
  doing such widenings rarely and in batches. Non-caching consumers (concord-mcp's httpx client,
  `curl`, a restarted container) are unaffected. Release-note item, not a code fix.
- **Payload cost, measured** against the real corpus rather than guessed: `John 21:15-17`
  13,575 → 19,155 B (**+41.1%**); `Genesis 1-50` — a legal reference, since this endpoint has no
  pagination — 3.24 → 4.56 MB (**+40.8%**). Most of that is `book` and `reference`, which repeat
  per token although a reference is single-book. Kept anyway: a token that names its own verse
  can be handed onward without its envelope, matching `TranslatorNote`, which repeats
  `book`/`chapter`/`verse` per note under a per-chapter envelope. Concord is LAN-first and the
  trade is deliberate — but the number belongs in writing, and if word-study payloads ever become
  a problem, hoisting `book` to the envelope (as `NotesResponse` does) is where to start.
- **`docs/openapi.json` cannot record this.** The handler returns a raw `Response` with no
  `response_model=`, so its `200` is `"schema": {}` and neither `WordTokenOut` nor
  `VerseWordsResponse` appears in `components.schemas` — as ADR-0003 already noted for
  `/v1/search`. `make openapi-check` therefore passes unchanged, and cannot serve as the drift
  guard for a body-shape change on these endpoints. **`docs/API.md` is the field enumeration for
  them.** Wiring response models into the schema is a repo-wide change, deliberately not made
  here; this ADR records the gap so the next reader isn't misled by a green `openapi-check`.
