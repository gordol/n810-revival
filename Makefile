DOCS_ENV ?= .venv-docs
.PHONY: docs-install docs-check docs-serve pocket-smoke

docs-install:
	python3 -m venv $(DOCS_ENV)
	$(DOCS_ENV)/bin/python -m pip install -r requirements-docs.lock

docs-check:
	python3 tools/check-journal.py --tracked
	python3 tools/check-publication.py
	$(DOCS_ENV)/bin/python -m mkdocs build --strict

docs-serve:
	$(DOCS_ENV)/bin/python -m mkdocs serve -a 127.0.0.1:8010

pocket-smoke:
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_runtime_codec.py' -q
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_navigation_audit.py' -q
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_touch_worker.py' -q
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_launcher.py' -q
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_lazy_startup.py' -q
	cd pocket && python3 -B -m unittest discover -s tests -p 'test_panel_tray.py' -q

# Release checks and packaging share the container build definition.
.PHONY: release-check release-archives
release-check: container-check
release-archives:
	$(MAKE) container-check DOCKER_STAGE=archives DOCKER_CACHE_FLAGS="--output type=local,dest=$(CURDIR)/dist $(DOCKER_CACHE_FLAGS)"

# Docker's content-addressed layers reuse component builds when their inputs match.
# These targets never install host toolchains or mount operator/device state.
DOCKER_STAGE ?= release-check
DOCKER_CACHE_FLAGS ?=
.PHONY: container-check container-check-clean
container-check:
	@bash -o pipefail -c 'python3 tools/package-source.py --list-context | COPYFILE_DISABLE=1 tar --null -T - -czf - | docker build --progress=plain --file containers/release.Dockerfile --target $(DOCKER_STAGE) $(DOCKER_CACHE_FLAGS) -'
container-check-clean:
	$(MAKE) container-check DOCKER_CACHE_FLAGS="--no-cache $(DOCKER_CACHE_FLAGS)"
