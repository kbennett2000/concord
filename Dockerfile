# Concord — production image (multi-stage), with semantic search (v2).
#
# Builder: install deps non-editably into a venv, bake bible.db from the committed
# public-domain data, fetch the int8 embedding model (pinned revision), and bake the int8
# embeddings.db. Runtime: a slim image carrying ONLY the venv + the baked databases + the
# baked int8 model + the vendored offline docs assets — no source, no loader, no build
# tools. A fresh container on a host with no internet serves the whole API, including
# /v1/semantic-search and /docs (SPEC §3-§8). Build-time internet is fine (the model is
# fetched then baked); none leaks into runtime.
#
# int8 only: the 1.25 GB fp32 weights never enter the image (S3a). The model + embeddings.db
# are baked, so the precision/model guard (S3a) catches a stale artifact at boot.

# --- builder ----------------------------------------------------------------------------
# Base images are pinned by digest for byte-reproducible builds; the tag in each comment is
# the human-readable equivalent (refresh the digest when bumping the tag).
# python:3.12-slim (3.12.13-slim-trixie)
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS builder

# ghcr.io/astral-sh/uv:0.11
COPY --from=ghcr.io/astral-sh/uv:0.11@sha256:b46b03ddfcfbf8f547af7e9eaefdf8a39c8cebcba7c98858d3162bd28cf536f6 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
WORKDIR /app

# The packages install --no-editable into the venv (site-packages), so bible_semantic's
# repo-relative path defaults can't resolve — pin every artifact path explicitly, exactly
# as v1 pins BIBLE_DB_PATH. fetch_model.py / build_embeddings.py honor these envs.
ENV BIBLE_DB_PATH=/app/bible.db \
    CONCORD_MODEL_PATH=/app/model \
    CONCORD_EMBEDDINGS_PATH=/app/embeddings.db

# Resolve dependencies first (cached layer) from manifests + lockfile only. Every workspace
# member's pyproject is needed for `uv sync --frozen` to resolve the workspace.
COPY pyproject.toml uv.lock ./
COPY bible-core/pyproject.toml bible-core/
COPY bible-api/pyproject.toml bible-api/
COPY bible-semantic/pyproject.toml bible-semantic/
RUN uv sync --frozen --no-dev --no-install-workspace

# Sources, then install the workspace packages *non-editably* (code + vendored docs assets
# are copied into .venv, so the runtime stage needs no source tree). This installs
# bible-semantic + onnxruntime/tokenizers/numpy — the ONNX runtime baked into the image.
COPY bible-core/ bible-core/
COPY bible-api/ bible-api/
COPY bible-semantic/ bible-semantic/
RUN uv sync --frozen --no-dev --no-editable

# Bake bible.db from the committed translations + cross-references. Reproducible (Slice 2).
# Use the venv python directly — `uv run` would re-sync (editable + dev deps), undoing the
# --no-editable install and leaving the runtime unable to import the packages.
COPY data/ data/
RUN /app/.venv/bin/python -m bible_core.loader --output /app/bible.db

# Fetch the int8 model (pinned revision; ~313 MB) then bake the int8 embeddings.db from the
# WEB corpus. Late layers: the ~21-min embed re-runs only when the model, data, or semantic
# code change. The model is baked into the image; runtime never downloads it.
COPY scripts/ scripts/
RUN /app/.venv/bin/python scripts/fetch_model.py
RUN /app/.venv/bin/python scripts/build_embeddings.py

# --- runtime ----------------------------------------------------------------------------
# python:3.12-slim (3.12.13-slim-trixie) — pinned by digest (see builder stage).
FROM python:3.12-slim@sha256:090ba77e2958f6af52a5341f788b50b032dd4ca28377d2893dcf1ecbdfdfe203 AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    BIBLE_DB_PATH=/app/bible.db \
    CONCORD_MODEL_PATH=/app/model \
    CONCORD_EMBEDDINGS_PATH=/app/embeddings.db
WORKDIR /app

# Run as a non-root system user, not root. Create it before the COPYs so the baked assets
# land owned by it. The service is read-only at runtime — bible.db is opened mode=ro and
# embeddings.db is only SELECTed once at boot (no journal/WAL written), logs go to stdout —
# so no writable directory is ever needed; the user just needs to read the venv + the two
# databases + the model.
RUN groupadd --system app && useradd --system --no-create-home --gid app app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/bible.db /app/bible.db
COPY --from=builder --chown=app:app /app/embeddings.db /app/embeddings.db
COPY --from=builder --chown=app:app /app/model /app/model

# Container always listens on 8000; the host port is remapped via compose.
EXPOSE 8000

# Drop root for everything below (healthcheck + CMD both run as this user).
USER app

# Healthy once /healthz returns 200 with a loaded corpus AND semantic search primed. Uses
# stdlib urllib (slim has no curl) and the venv python on PATH. The long start-period covers
# the embedding-model warm-up at boot (slower on a no-AVX2 CPU).
HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
    CMD python -c "import sys,json,urllib.request; \
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)); \
sys.exit(0 if d.get('translation_count', 0) > 0 and (d.get('semantic') or {}).get('enabled') else 1)"

CMD ["uvicorn", "bible_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
