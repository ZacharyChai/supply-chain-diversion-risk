# Semiconductor Trade Diversion Risk: one command reproduces everything end to end.
# `make all` runs the full pipeline from a clean clone.

VENV   := .venv
PYTHON := $(VENV)/bin/python
DB     := data/processed/trade.db

.PHONY: all setup fetch parse events score drivers clean help

all: setup fetch parse events score drivers ## Full pipeline: setup -> fetch -> parse -> events -> score -> drivers/charts

setup: $(VENV)/.installed ## Create venv and install requirements
$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(PYTHON) -m pip install -q --upgrade pip
	$(PYTHON) -m pip install -q -r requirements.txt
	touch $@

fetch: setup ## Pull Comtrade, Census cross-check, and Federal Register control dates into data/raw/
	$(PYTHON) src/fetch_comtrade.py
	$(PYTHON) src/fetch_census.py
	$(PYTHON) src/fetch_control_dates.py

parse: fetch ## Build one tidy long-format trade table -> SQLite
	$(PYTHON) src/build_trade_table.py

events: parse ## Merge the BIS control-date timeline against the trade series
	$(PYTHON) src/build_event_timeline.py

score: events ## Run the three-signal diversion risk scoring SQL
	sqlite3 $(DB) < src/build_risk_score.sql

drivers: score ## Driver analysis + export charts
	$(PYTHON) src/drivers.py

clean: ## Remove generated data (keeps raw downloads)
	rm -f $(DB) data/processed/*.csv
	rm -f analysis/charts/*.png

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
