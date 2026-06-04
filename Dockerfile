# Concord — DEV image (single-stage). Builds and runs bible-api.
#
# Production hardening (multi-stage build, baked bible.db, self-hosted offline Swagger
# assets, healthcheck) is Slice 8 — deliberately NOT solved here. The build phase may
# reach the internet; that is fine (one-time setup). See docs/SPEC.md §3.

FROM python:3.12-slim

# uv: copy the static binary from the official image (pinned major for reproducibility).
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /bin/uv

ENV UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Resolve dependencies first (cached layer) from manifests + lockfile only.
COPY pyproject.toml uv.lock ./
COPY bible-core/pyproject.toml bible-core/
COPY bible-api/pyproject.toml bible-api/
RUN uv sync --frozen --no-install-workspace --no-dev

# Then the sources, and install the workspace packages themselves.
COPY bible-core/ bible-core/
COPY bible-api/ bible-api/
RUN uv sync --frozen --no-dev

# Container always listens on 8000; the host port is the configurable knob (compose).
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "bible_api.app:app", "--host", "0.0.0.0", "--port", "8000"]
