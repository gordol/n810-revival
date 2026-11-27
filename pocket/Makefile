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

# Independent pixel frontend. Terminal launch is unchanged.
.PHONY: tui gui graphics-native graphics-check
tui: shell
graphics-native:
	$(PYTHON) graphics/build.py
graphics-check: graphics-native
	$(PYTHON) graphics/check.py $(EXTRA)
# Keep Mac graphics dependencies in the ignored build tree.
GUI_PYTHON = $(PYTHON)
ifeq ($(shell uname -s),Darwin)
GUI_PYTHON = build/mac-gui/bin/python
MAC_GUI_BOOTSTRAP = build/mac-gui/.installed
$(MAC_GUI_BOOTSTRAP): requirements-graphics-macos.txt Makefile
	@command -v brew >/dev/null || { echo "Install Homebrew, then retry." >&2; exit 1; }
	brew install sdl2 python@3.12
	"$$(brew --prefix python@3.12)/bin/python3.12" -m venv build/mac-gui
	$(GUI_PYTHON) -m pip install Pillow -r requirements-graphics-macos.txt
	touch $@
gui explore: export SDL_RENDER_DRIVER ?= opengl
endif

gui: $(MAC_GUI_BOOTSTRAP)
	$(GUI_PYTHON) graphics/gui.py $(EXTRA)

.PHONY: explore
explore: $(MAC_GUI_BOOTSTRAP)
	$(MAKE) terrain-prepare PYTHON="$(GUI_PYTHON)"
	$(GUI_PYTHON) graphics/gui.py --explore $(EXTRA)

# Area-selected map acquisition and local derived levels.
include maps.mk

# Explicit optional game preparation; app opening never downloads data.
.PHONY: doom
doom:
	$(PYTHON) shell/apps/doom-app/build.py $(EXTRA)

# N810 managed graphics session; APP=chess or APP=snakes.
APP ?= chess
.PHONY: symbian
symbian:
	$(PYTHON) shell/symbian_launch.py "$(APP)"

.PHONY: symbian-install
symbian-install:
	$(PYTHON) shell/symbian_install.py "$(PACKAGE)"

# Use the portable terminal renderer on Android; extra options follow the defaults.
.PHONY: termux termux-gui
termux:
	POCKET_TERMUX=1 POCKET_PHONE_RADIO="$(PHONE_RADIO)" $(PYTHON) shell/launch.py --instance "$(INSTANCE)" --no-native --no-animation $(if $(strip $(ADDRESS)),--connection-address "$(ADDRESS)") $(if $(strip $(SSH_KEY)),--connection-key "$(SSH_KEY)") $(EXTRA)

termux-gui mobile:
	@set -e; \
	export DISPLAY="$${DISPLAY:-:1}"; \
	if [ -z "$${VK_DRIVER_FILES:-}$${VK_ICD_FILENAMES:-}$${GALLIUM_DRIVER:-}$${MESA_LOADER_DRIVER_OVERRIDE:-}" ]; then \
		for icd in "$$PREFIX"/share/vulkan/icd.d/freedreno_icd*.json; do \
			if [ -f "$$icd" ]; then \
				export VK_DRIVER_FILES="$$icd" MESA_LOADER_DRIVER_OVERRIDE=zink GALLIUM_DRIVER=zink; \
				break; \
			fi; \
		done; \
		if [ -z "$$VK_DRIVER_FILES" ] && [ "$$(getprop ro.product.device 2>/dev/null)" = FP4 ]; then \
			echo "Fairphone 4 Vulkan driver missing. Run pkg install mesa-vulkan-icd-freedreno." >&2; exit 1; \
		fi; \
	fi; \
	POCKET_TERMUX=1 POCKET_PHONE_RADIO="$(PHONE_RADIO)" SDL_VIDEODRIVER=x11 $(PYTHON) graphics/gui.py $(if $(strip $(ADDRESS)),--connection-address "$(ADDRESS)") $(if $(strip $(SSH_KEY)),--connection-key "$(SSH_KEY)") $(EXTRA)

.PHONY: mobile
mobile: override EXTRA += --mobile-shell
mobile: mobile-map-deps mobile-api-deps

.PHONY: mobile-api-deps
mobile-api-deps:
	@if ! command -v termux-vibrate >/dev/null; then \
		pkg install -y termux-api || echo "Phone haptics unavailable. Retry with pkg install termux-api." >&2; \
	fi

TERRAIN_REGIONS ?= sound hoh rainier
.PHONY: terrain-prepare mobile-prepare-terrain mobile-update
terrain-prepare:
	PYTHONPATH=graphics:shell:shell/apps/landscape-lab:shell/apps/surface-renderer $(PYTHON) -m pnw $(TERRAIN_REGIONS)

mobile-prepare-terrain: mobile-map-deps
	POCKET_TERMUX=1 $(MAKE) terrain-prepare

mobile-update:
	@branch=$$(git branch --show-current); case "$$branch" in \
	  feat/offline-field-companion|feat/ohanapecosh-wildlife) git pull --ff-only origin "$$branch" ;; \
	  *) echo "Switch to a Pocket mobile feature branch to update this build." >&2; exit 1 ;; \
	esac
	$(MAKE) mobile-prepare-terrain || echo "Terrain preparation incomplete. Retry with make mobile-prepare-terrain." >&2
	$(MAKE) mobile
