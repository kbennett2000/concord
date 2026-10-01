"""Converter for an operator-owned Every Man's Bible PDF (Concord v8, docs/v8/SPEC.md).

Reads the PDF through ``pdftohtml -xml`` (poppler-utils) and writes the private translation
file ``data/private/EMB.json``. The package holds parsing rules only, never source text: the
text comes from the operator's own copy at run time and stays under ``data/private/``.

Run it through ``scripts/convert_emb.py``; see ``docs/v8/emb-ingest.md``.
"""
