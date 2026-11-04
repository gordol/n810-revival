DOCS_ENV ?= .venv-docs
.PHONY: docs-install docs-check docs-serve pocket-smoke

docs-install:
	python3 -m venv $(DOCS_ENV)
	$(DOCS_ENV)/bin/python -m pip install -r requirements-docs.lock

docs-check:
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
