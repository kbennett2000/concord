"""Normalize a book token to its canonical alias form.

Implements the *Normalization contract* in ``docs/canonical-books.md``: the alias table
stores normalized forms, and the reference parser (Slice 3) normalizes incoming book
tokens the same way before lookup. Pure function, standard library only.

Note on step ordering: the contract lists "remove internal whitespace" before "leading
ordinal -> digit", but a faithful implementation must detect the ordinal as a *leading
whitespace-delimited token* before collapsing whitespace. Collapsing first would make
``I Samuel`` -> ``isamuel`` indistinguishable from a genuine leading ``i`` in a word
like ``Isaiah`` (which must stay ``isaiah``, not become ``1saiah``). The final output
matches every example in the contract.
"""

from __future__ import annotations

# Leading ordinal tokens -> digit. Roman numerals, English words, and digits all map to
# the digit form the alias table stores. Matched only as a standalone leading token.
_ORDINALS = {
    "i": "1",
    "ii": "2",
    "iii": "3",
    "first": "1",
    "second": "2",
    "third": "3",
    "1": "1",
    "2": "2",
    "3": "3",
}

# Punctuation the contract strips: periods and apostrophes (straight and curly).
_PUNCTUATION = str.maketrans("", "", ".'’")


def normalize(token: str) -> str:
    """Return the normalized alias form of a book ``token``.

    Lowercase, strip periods/apostrophes, fold a leading ordinal token to its digit,
    and remove all internal whitespace. Idempotent.
    """
    lowered = token.lower().translate(_PUNCTUATION)
    parts = lowered.split()
    if not parts:
        return ""
    if len(parts) > 1 and parts[0] in _ORDINALS:
        parts[0] = _ORDINALS[parts[0]]
    return "".join(parts)
