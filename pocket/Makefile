PYTHON ?= python3
INSTANCE ?= default
EXTRA ?=
ADDRESS ?= $(or $(LINK),$(SSH_TARGET))
SSH_KEY ?=
.PHONY: shell n810 test check native dist fcc-data setup
shell n810:
	$(PYTHON) shell/launch.py --instance "$(INSTANCE)" $(if $(strip $(ADDRESS)),--connection-address "$(ADDRESS)") $(if $(strip $(SSH_KEY)),--connection-key "$(SSH_KEY)") $(EXTRA)
test:
	$(PYTHON) -B -m unittest discover -s tests -v
check: test

native:
	$(PYTHON) tools/build_native.py

dist:
	$(PYTHON) tools/release.py

# Explicit preparation; starting Pocket never downloads a database.
fcc-data:
	PYTHONPATH=shell $(PYTHON) -m fcc_download $(FCC_ARGS)
setup:
	$(PYTHON) shell/launch.py --instance "$(INSTANCE)" --setup $(EXTRA)

# Area-selected map acquisition and local derived levels.
include maps.mk
