# ADR-0010: Accepting `book c1-c2:v2` reference ranges

**Status:** Accepted

<!--
Records why the reference grammar now accepts a bare chapter on the left of a range when the
right side carries a verse ("Judges 13-14:11"), reversing a Slice 3 policy-table call.
Prompted by issue #73. Format mirrors ADR-0001..0009: Context / Options / Decision /
Consequences.
-->

## Context

Issue #73: songbird's sermon-sources scan hands every reference-shaped string it finds to
`GET /v1/verses/{ref}` and treats a refusal as "that string was not a reference". Cornerstone
Chapel writes its passages as `Judges 13-14:11` — a bare chapter, a dash, then
`chapter:verse` — meaning Judges 13:1 through 14:11. Concord answered
`400 unparseable_reference`, so eight of that channel's sermons landed in a review queue
instead of being placed. songbird never interprets references itself; it asks Concord and
believes the answer.

The refusal was deliberate. `_parse_range` dispatches on whether each side of the `-` carries
a `:`, and the `chapter` / `chapter:verse` combination raised:

> ambiguous range '13-14:11' in 'Judges 13-14:11': a bare chapter on the left and
> chapter:verse on the right; write it as C:V-C:V

That call was recorded in the Slice 3 edge-case policy table (`docs/dev-notes.md`, the
`3-4:2` row) and mirrored by a `REJECTS` row in `test_parser_edge_cases.py`. It was never a
SPEC §5 decision — §5 lists supported forms and says nothing about this one.

Two facts reframe it. First, the span is not novel: `Judges 13:1-14:11` already parses to
`Span(13, 1, 14, 11)` and `queries._span_predicate` already serves it through the
cross-chapter linear branch, so nothing downstream needs to learn a new shape. Second, the
form is not actually ambiguous. The ambiguity the old message worried about belongs to a
*different* cell of the grammar — `John 3:16-18`, where a bare right bound means a verse.
Here the bare bound is on the **left**, where no competing reading exists.

## Options considered

- **(A) Read a bare left chapter as starting at verse 1. Chosen.** `c1-c2:v2` becomes
  `Span(c1, 1, c2, v2)` — one new branch, four lines, no new span shape, no query change,
  and the canonical echo (`Judges 13:1-14:11`) already round-trips.
- **(B) Keep rejecting; tell clients to normalize.** This is the status quo, and it puts the
  work on every consumer. songbird's whole design principle is that it does not interpret
  references — the moment it rewrites `13-14:11` into `13:1-14:11` it is guessing at
  Scripture semantics, which is exactly what Concord exists to own. A reference format that
  churches actually publish is Concord's problem.
- **(C) Also make the mirror form work — read `John 3:16-4` as 3:16 through the end of ch 4.**
  Rejected on two independent grounds. It collides head-on with `John 3:16-18`, whose
  bare-right-bound-is-a-verse reading is load-bearing and shipped. And "the end of chapter 4"
  is a verse count — a database fact. `bible-core`'s parser is pure by hard invariant (no DB,
  no I/O); teaching it chapter lengths would break the property that makes it embeddable.
- **(D) Represent the open end as `Span(3, 16, 4, None)`.** Violates the `Span` invariant
  (verse bounds are set together or both `None`), trips the assertion in `_span_predicate`,
  and needs a fourth predicate branch plus an echo case — a strictly larger change for a form
  nobody reported.

## Decision

**A bare chapter on the left of a range starts at verse 1: `book c1-c2:v2` resolves to
`Span(c1, 1, c2, v2)`, rejecting only `c2 < c1` as descending. `book c:v1-v2` is untouched.**

The rule that makes this principled rather than a special case, and that explains why the
mirror form stays rejected:

> An omitted verse at a range **start** is inferable — it is always 1, a constant. At a range
> **end** it would mean "through the end of that chapter", which requires that chapter's
> verse count: a DB fact this parser is not allowed to know.

The asymmetry is therefore load-bearing, not an oversight. It is stated in a comment on the
branch itself, in the `docs/dev-notes.md` policy table, and here, because a future reader
looking at `3-4:2` accepting and `3:16-4` rejecting will reasonably be tempted to "fix" it.

`John 3:16-4`'s error message now names the alternative spelling rather than only reporting
the descent, since teaching users `13-14:11` makes that neighbour more reachable.

## Consequences

- **The `/v1` contract only widens.** Inputs that returned 200 return the same 200, byte for
  byte. The branch this replaces raised unconditionally, so no reference that parsed before
  can change meaning — the entire risk surface was inputs that used to 400, and they now
  resolve to a span that was already reachable by another spelling.
- **Nothing is superseded.** The reversed call lived in the dev-notes policy table and a test
  row, not in an ADR, so no prior ADR's `Status` changes. That table row is marked amended
  rather than deleted, so the history of the decision survives.
- **`reference` echoes the canonical spelling.** `Judges 13-14:11` comes back as
  `Judges 13:1-14:11`, because the echo is computed from the normalized spans, not the input.
  A client that round-trips the echo gets an identical `Reference`, and the two spellings
  produce identical bodies and identical ETags. Clients that compare their request string to
  the returned `reference` will see them differ — as they already do for `John 3.16` and
  every other non-canonical input.
- **No new query cost.** `Span(c1, 1, c2, v2)` is the same shape `John 3:16-4:2` produces, so
  it takes the same linear `(chapter, verse)` predicate. That predicate does drop the chapter
  constraint out of the index seek and filter instead — but that is pre-existing for every
  cross-chapter range, unchanged by this ADR, and the worst realistic case (`Psalms 1-150:6`
  across 19 translations, 44,298 rows) measures ~82 ms.
- **`docs/openapi.json` cannot record this**, as with ADR-0003 and ADR-0009: the `ref` path
  parameter carries no description and the grammar appears in no schema, so
  `make openapi-check` stays green and is not the drift guard here. **`docs/API.md` is the
  grammar of record** — its table gained a row, and the mirror-form asymmetry is spelled out
  beneath it.
- **One neighbour is now more reachable and still fails.** `Judges 13-14:11,13` — the new form
  inside a verse list — remains rejected, because a comma wins the parse dispatch before the
  range branch is reached, and it fails with a message about chapter numbers. Ranges in lists
  were already unsupported (`John 3:16-18,20`); this is consistent, is pinned by a test, and
  a clearer message is worth its own issue rather than scope here.
