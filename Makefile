PYTHON ?= python3
CONFIG ?= example-config.yml

.PHONY: run test check

run:
	$(PYTHON) -m app.server --config $(CONFIG)

test:
	$(PYTHON) -m unittest discover -s tests -v

check: test
