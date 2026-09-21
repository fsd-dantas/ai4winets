PYTHON ?= python

.PHONY: test schemas

test:
	$(PYTHON) -m unittest discover -s tests -v

schemas:
	$(PYTHON) -m ecora schema --output data/schemas/ecora-v1.schema.json
	$(PYTHON) -m ecora fixtures --output data/fixtures/contracts-v1.json
