.PHONY: format check

PYTHON ?= python3
PIP ?= $(PYTHON) -m pip

# Source and test trees (flat package under src/)
SRC := src
TESTS := tests

format:
	$(PYTHON) -m ruff format $(SRC) $(TESTS)
	$(PYTHON) -m black $(SRC) $(TESTS)

check:
	$(PYTHON) -m ruff format --check $(SRC) $(TESTS)
	$(PYTHON) -m ruff check $(SRC) $(TESTS)
	$(PYTHON) -m black --check $(SRC) $(TESTS)
	$(PYTHON) -m pytest

build:
	pip install -e ".[dev]"   # needs root README (restored)
	cd tui && npm run build
	cd .. && neutrino