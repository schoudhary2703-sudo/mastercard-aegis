# AEGIS developer commands. Every command below must work from a clean clone.
.DEFAULT_GOAL := help
PY ?= python3

.PHONY: help install install-dev test test-cov lint format typecheck check verify clean tree

help: ## Show available commands
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Install the package (runtime deps only)
	$(PY) -m pip install -e .

install-dev: ## Install the package with dev tooling
	$(PY) -m pip install -e ".[dev]"

test: ## Run the test suite
	$(PY) -m pytest

test-cov: ## Run tests with coverage
	$(PY) -m pytest --cov=aegis --cov-report=term-missing

lint: ## Lint with ruff
	$(PY) -m ruff check .

format: ## Auto-format and auto-fix with ruff
	$(PY) -m ruff format .
	$(PY) -m ruff check . --fix

typecheck: ## Static type check with mypy
	$(PY) -m mypy

check: lint typecheck test ## Lint + typecheck + test

verify: ## Smoke-check the installation and contract surface
	$(PY) scripts/verify_setup.py

clean: ## Remove caches and build artifacts
	rm -rf build dist .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name "*.egg-info" -prune -exec rm -rf {} +

tree: ## Print the repository tree (excluding caches)
	@find . -not -path "*/.git/*" -not -path "*/__pycache__/*" -not -path "*/.*cache/*" | sort
