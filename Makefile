PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup check test lint typecheck format clean

help: ## Show available targets
	@grep -hE '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

setup: ## Create .venv and install the package with dev dependencies
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --quiet --upgrade pip
	$(BIN)/pip install --quiet -e ".[dev]"
	@echo "Ready. Run 'make check'."

check: lint typecheck test ## Run every validation gate

test: ## Run the test suite
	$(BIN)/pytest

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
