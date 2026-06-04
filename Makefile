# Concord dev tasks. Every check is one command from the repo root, over both packages.
.PHONY: install lint fmt fmt-check typecheck test check run build-db

install:           ## Create the shared .venv and editable-install both packages
	uv sync

lint:              ## Ruff lint
	uv run ruff check .

fmt:               ## Ruff format (write)
	uv run ruff format .

fmt-check:         ## Ruff format (check only)
	uv run ruff format --check .

typecheck:         ## Pyright (strict)
	uv run pyright

test:              ## Pytest (both packages; excludes integration)
	uv run pytest

check: lint fmt-check typecheck test  ## Run the full gate

run:               ## Run the API locally (honors BIBLE_API_PORT, default 8000)
	uv run uvicorn bible_api.app:app --host 0.0.0.0 --port $${BIBLE_API_PORT:-8000}

build-db:          ## Build bible.db from data/translations (+ local data/private)
	uv run python -m bible_core.loader
