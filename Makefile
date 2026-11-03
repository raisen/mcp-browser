# Common operations. Run `make help`. Needs GNU make 3.81+ (the macOS default works).
#
# Dev targets run inside the devcontainer (IN). Without it: `make test IN=` uses local uv.
# Product targets (run, start, stop, status, open) always run on the HOST with local uv:
# the tool must see your real client configs, and the container cannot reach your browser.

IN ?= devcontainer exec --workspace-folder .
PORT ?= 8765
PYINSTALLER ?= 6.22.3# same pin as .github/workflows/*.yml
ARGS ?=

.DEFAULT_GOAL := help
.PHONY: help up sync lock test lint fmt typecheck lines check build bundle clean \
	run start stop status open

help: ## Show this help
	@echo "Usage: make <target> [IN=] [PORT=$(PORT)] [ARGS=...]"
	@echo "Dev targets run in the devcontainer (IN=); 'make test IN=' uses local uv."
	@echo "Product targets (run start stop status open) run on the host."
	@echo
	@grep -E '^[a-z]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

up: ## Start the devcontainer
	devcontainer up --workspace-folder .

sync: ## Install locked dependencies for all packages
	$(IN) uv sync --all-packages --locked

lock: ## Update uv.lock
	$(IN) uv lock

test: ## Run pytest (ARGS="-k name" passes extra arguments)
	$(IN) uv run pytest $(ARGS)

lint: ## ruff check and format check (no changes)
	$(IN) uv run ruff check .
	$(IN) uv run ruff format --check .

fmt: ## Format and auto-fix with ruff
	$(IN) uv run ruff format .
	$(IN) uv run ruff check --fix .

typecheck: ## Run pyright
	$(IN) uv run pyright

lines: ## Fail if a source file exceeds 250 lines
	$(IN) uv run python scripts/check_lines.py

check: sync lint typecheck test lines ## Everything CI checks, in CI's order

build: ## Build sdists and wheels of the three packages into dist/
	$(IN) uv build --package mcp-browser-core --out-dir dist
	$(IN) uv build --package mcp-browser-server --out-dir dist
	$(IN) uv build --package mcp-browser --out-dir dist

bundle: ## Build the PyInstaller zip into dist/
	$(IN) uv run --with pyinstaller==$(PYINSTALLER) python packaging/build.py --out dist

clean: ## Remove dist, build and tool caches (never .venv or logs)
	rm -rf dist build .pytest_cache .ruff_cache .pyright
	find . -name __pycache__ -type d -not -path './.git/*' -not -path './.venv/*' -prune -exec rm -rf {} +

run: ## HOST: run in the foreground on PORT
	uv run mcp-browser serve --port $(PORT)

start: ## HOST: run in the background on PORT
	uv run mcp-browser start --port $(PORT)

stop: ## HOST: stop the background server
	uv run mcp-browser stop --port $(PORT)

status: ## HOST: print running or stopped
	uv run mcp-browser status --port $(PORT)

open: ## HOST: open the running server's page
	uv run mcp-browser open --port $(PORT)
