PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup setup-live check test coverage lint typecheck format clean

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv and install the package with dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"
	@test -f .env || cp .env.example .env
	@echo "Ready. Run 'make check'."
	@echo "No API key needed — runs from recorded output. For live: make setup-live"

# Optional. Everything DecisionLens demonstrates works without this: the default
# run replays recorded output, offline and free. This exists so the same workflow
# can be pointed at a live model when someone wants to see it actually thinking.
setup-live: ## Add the optional Anthropic SDK for live model runs
	$(BIN)/pip install --quiet -e ".[dev,live]"
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

# A `demo` target arrives in Phase 9, once the CLI and the structured Streamlit
# interface exist. It will run the bundled synthetic case offline, with no API
# key, against the problem-first question:
#   "Which intervention should the team prioritize to reduce delivery exceptions?"

clean: ## Remove the virtualenv and build artifacts
	rm -rf $(VENV) build dist .pytest_cache .ruff_cache .mypy_cache
	rm -rf *.egg-info src/*.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
