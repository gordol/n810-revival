# Select an area once with maps-configure, or supply MAP_BBOX explicitly.
MAP_REQUIREMENTS ?= ../requirements-maps.txt
MAP_SOURCE ?=
MAP_URL ?=
MAP_BBOX ?=
MAP_WORKERS ?= 2
MAP_SPACING ?= 15
MAP_ARGS = $(if $(strip $(MAP_SOURCE)),--source "$(MAP_SOURCE)") $(if $(strip $(MAP_URL)),--url "$(MAP_URL)") $(if $(strip $(MAP_BBOX)),--bbox $(MAP_BBOX))
.PHONY: maps-deps maps-configure maps-plan maps-download maps maps-build maps-elevation maps-terrain
maps-deps:
	$(PYTHON) -m pip install -r $(MAP_REQUIREMENTS)
maps-configure:
	$(PYTHON) tools/maps.py configure $(MAP_ARGS)
maps-plan:
	$(PYTHON) tools/maps.py plan $(MAP_ARGS) --spacing-m $(MAP_SPACING)
maps-download:
	$(PYTHON) tools/maps.py download $(MAP_ARGS)
maps:
	$(MAKE) maps-download
	$(MAKE) maps-build
	$(MAKE) maps-elevation
maps-build:
	$(PYTHON) tools/maps.py build $(MAP_ARGS)
maps-elevation:
	$(PYTHON) tools/maps.py elevation $(MAP_ARGS) --spacing-m $(MAP_SPACING) --workers $(MAP_WORKERS)
# Offline derivation: never downloads a second coarse DEM or local crop.
maps-terrain:
	$(PYTHON) tools/maps.py terrain $(MAP_ARGS) --spacing-m $(MAP_SPACING) --workers $(MAP_WORKERS)
