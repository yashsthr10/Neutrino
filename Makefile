.PHONY: format check build test help

PYTHON ?= python3

# Python trees covered by format/lint/tests
SRC := src
TESTS := tests

# Minimum total line coverage for `make check` (override: make check COVERAGE_MIN=70)
COVERAGE_MIN ?= 65

help:
	@echo "Targets:"
	@echo "  make format  — format Python (ruff format + lint autofix)"
	@echo "  make check   — format check, lint, pytest+coverage, TUI typecheck/tests"
	@echo "  make test    — pytest only (no coverage gate)"
	@echo "  make build   — install editable +[dev] and build the TUI"

format:
	$(PYTHON) -m ruff format $(SRC) $(TESTS)
	$(PYTHON) -m ruff check --fix --unsafe-fixes $(SRC) $(TESTS)

check:
	$(PYTHON) -m ruff format --check $(SRC) $(TESTS)
	$(PYTHON) -m ruff check $(SRC) $(TESTS)
	$(PYTHON) -m pytest \
		--cov=$(SRC) \
		--cov-report=term-missing:skip-covered \
		--cov-fail-under=$(COVERAGE_MIN)
	cd tui && npm run typecheck
	cd tui && npm test

test:
	$(PYTHON) -m pytest

build:
	$(PYTHON) -m pip install -e ".[dev]"
	cd tui && npm run build
