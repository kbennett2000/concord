# Concord — production image (multi-stage).
#
# Builder: install deps non-editably into a venv and bake bible.db from the committed
# public-domain data. Runtime: a slim image carrying ONLY the venv + the baked database +
# the vendored offline docs assets (which ship inside the installed bible_api package) —
# no source, no data files, no loader, no build tools. A fresh container on a host with no
# internet serves the whole API, including /docs (SPEC §3). Build-time internet is fine;
# none leaks into runtime.

# --- builder ----------------------------------------------------------------------------
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv
ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_COMPILE_BYTECODE=1
WORKDIR /app

# Resolve dependencies first (cached layer) from manifests + lockfile only.
COPY pyproject.toml uv.lock ./
COPY bible-core/pyproject.toml bible-core/
COPY bible-api/pyproject.toml bible-api/
RUN uv sync --frozen --no-dev --no-install-workspace

# Sources, then install the workspace packages *non-editably* (code + vendored docs assets
# are copied into .venv, so the runtime stage needs no source tree).
COPY bible-core/ bible-core/
COPY bible-api/ bible-api/
RUN uv sync --frozen --no-dev --no-editable

# Bake bible.db from the committed translations + cross-references. Reproducible (Slice 2).
# Use the venv python directly — `uv run` would re-sync the env (editable + dev deps),
# undoing the --no-editable install and leaving the runtime unable to import the packages.
COPY data/ data/
RUN /app/.venv/bin/python -m bible_core.loader --output /app/bible.db

# --- runtime ----------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    BIBLE_DB_PATH=/app/bible.db
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/bible.db /app/bible.db

# Container always listens on 8000; the host port is remapped via compose.
EXPOSE 8000

# Healthy once /healthz returns 200 with a loaded corpus. Uses stdlib urllib (slim has no
# curl) and the venv python on PATH.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD python -c "import sys,json,urllib.request; \
d=json.load(urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2)); \
sys.exit(0 if d.get('translation_count', 0) > 0 else 1)"

CMD ["uvicorn", "bible_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
