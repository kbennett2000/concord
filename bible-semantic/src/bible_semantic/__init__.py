"""Concord's semantic layer.

ML-bearing but web-framework-free (onnxruntime + tokenizers + numpy). Embeds text into
normalized vectors for meaning-based Scripture search. Slice S0 ships the query-embedding
core (``model.py``); the store, search, and corpus build land in later slices.
"""

__version__ = "0.0.0"
