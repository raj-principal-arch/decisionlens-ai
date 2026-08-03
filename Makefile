PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup setup-live check test coverage lint typecheck format demo ui record record-resume clean

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-13s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv and install the package with dev and UI dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev,ui]"
	@test -f .env || cp .env.example .env
	@echo "Ready. Run 'make demo' for a brief, or 'make ui' for the interface."
	@echo "No API key needed — runs from recorded output. For live: make setup-live"

# Optional. Everything DecisionLens demonstrates works without this: the default
# run replays recorded output, offline and free. This exists so the same workflow
# can be pointed at a live model when someone wants to see it actually thinking.
setup-live: ## Add the optional Anthropic SDK for live model runs
	$(BIN)/pip install --quiet -e ".[dev,ui,live]"
	@test -f .env || cp .env.example .env
	@echo "Installed. Two lines in .env switch DecisionLens to a live model:"
	@echo "  ANTHROPIC_API_KEY=sk-ant-..."
	@echo "  MODEL_PROVIDER=anthropic"
	@echo "Both are required. A key alone changes nothing, by design."
	@echo "Blank them out at any time to return to the free recorded demo."

check: lint typecheck test ## Run every validation gate

test: ## Run the test suite
	$(BIN)/pytest

# Kept out of `check` so the default gate stays fast. Run it when you want to
# know what the suite does not exercise, not on every edit.
coverage: ## Run the test suite with a line-coverage report
	$(BIN)/pytest --cov=decision_lens --cov-report=term-missing

lint: ## Check lint rules and formatting
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

typecheck: ## Run mypy
	$(BIN)/mypy

format: ## Apply formatting and safe lint fixes
	$(BIN)/ruff format .
	$(BIN)/ruff check --fix .

# The bundled synthetic case, offline, with no API key, against the
# problem-first question:
#   "Which intervention should the team prioritize to reduce delivery exceptions?"
# Exits 2 rather than 0 when the brief carries blocking errors — a run that
# produced an unusable brief should not look like a clean run to a script.
# These invoke the module rather than the `decisionlens` console script, and set
# PYTHONPATH themselves. The console script depends on the editable install's
# .pth file, which is fragile: a filesystem that duplicates files (iCloud sync
# produces "name 2.pth" beside "name.pth") leaves the package silently
# unimportable while everything looks installed. The same reasoning is already
# why pytest sets `pythonpath = ["src"]`. `decisionlens ...` still works when the
# install is healthy; these targets work either way.
DL := PYTHONPATH=src $(BIN)/python -m decision_lens.cli

# Exit 2 means the brief was produced but carries blocking errors — a real
# outcome worth showing, not a broken target. A genuine failure still exits 1.
demo: ## Produce a brief from the bundled case and write it to out/
	@$(DL) run --out out --format both || test $$? -eq 2

ui: ## Open the structured interface in a browser
	PYTHONPATH=src $(BIN)/streamlit run src/decision_lens/ui.py

# The one command that costs money, and the only way the demo cache is ever
# filled. Run it once with a key; every run after that is free and offline.
record: ## Call a real model once and record its responses for offline replay
	@$(DL) record || test $$? -eq 2

# After a prompt version changes, only the affected stages need re-recording.
# This exists as its own target because the alternative — remembering to type
# PYTHONPATH by hand — sends people to the `decisionlens` console script, which
# fails whenever the editable install is in the broken state described above.
record-resume: ## Re-record only the stages the cache can no longer replay
	@$(DL) record --resume || test $$? -eq 2

clean: ## Remove the virtualenv and build artifacts
	rm -rf $(VENV) build dist .pytest_cache .ruff_cache .mypy_cache
	rm -rf *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
