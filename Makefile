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

# Personalized images stay local. Only the public key and output directory mount.
SD_OUTPUT ?= $(CURDIR)/dist/n810-sd
SD_SIZE_MIB ?= 2048
SD_USER ?= nokia
SD_JOBS ?= 4
SD_DOCKER_IMAGE ?= n810-sd-builder:local
MAEMO_BACKUP ?=
SD_FIRMWARE_OFFLINE ?= 0
SD_FIRMWARE_CACHE ?= n810-sd-firmware
SD_BUILD_FLAGS ?=
export SSH_PUBLIC_KEY SD_OUTPUT SD_SIZE_MIB SD_USER SD_JOBS SD_DOCKER_IMAGE MAEMO_BACKUP SD_FIRMWARE_OFFLINE SD_FIRMWARE_CACHE
.PHONY: sd-image
sd-image:
	@test -t 0 || { echo 'Run make sd-image in a terminal for the local password prompt.' >&2; exit 1; }
	@test -n "$$SSH_PUBLIC_KEY" && test -f "$$SSH_PUBLIC_KEY" || { echo 'Set SSH_PUBLIC_KEY to your Ed25519 .pub file.' >&2; exit 1; }
	@test -z "$$MAEMO_BACKUP" || test -d "$$MAEMO_BACKUP" || { echo "MAEMO_BACKUP must name a backup directory." >&2; exit 1; }
	@test "$$SD_FIRMWARE_OFFLINE" = 0 || test "$$SD_FIRMWARE_OFFLINE" = 1 || { echo "SD_FIRMWARE_OFFLINE must be 0 or 1." >&2; exit 1; }
	@test ! -e "$$SD_OUTPUT" || { echo 'SD_OUTPUT must be a new directory.' >&2; exit 1; }
	docker build $(SD_BUILD_FLAGS) --progress=plain -f containers/sd-image.Dockerfile --build-arg JOBS="$$SD_JOBS" -t "$$SD_DOCKER_IMAGE" .
	@umask 077; mkdir -p "$$SD_OUTPUT"
	@set --; if test -n "$$MAEMO_BACKUP"; then set -- --mount "type=bind,src=$$(cd "$$MAEMO_BACKUP" && pwd),dst=/backup,readonly"; fi; \
	docker run --rm -it "$$@" --mount "type=bind,src=$$(cd "$$(dirname "$$SSH_PUBLIC_KEY")" && pwd)/$$(basename "$$SSH_PUBLIC_KEY"),dst=/run/owner.pub,readonly" \
		--mount "type=bind,src=$$(cd "$$SD_OUTPUT" && pwd),dst=/output" \
		-e OUTPUT_UID="$$(id -u)" -e OUTPUT_GID="$$(id -g)" \
		--mount "type=volume,src=$$SD_FIRMWARE_CACHE,dst=/cache/firmware" \
		-e SD_USER -e SD_SIZE_MIB -e SD_FIRMWARE_OFFLINE "$$SD_DOCKER_IMAGE" sh -ec '\
		arch-test armel; \
		set --; if test -d /backup; then set -- --backup /backup; fi; if test "$$SD_FIRMWARE_OFFLINE" = 1; then set -- "$$@" --offline; fi; \
		python3 platform/bootstrap/firmware.py --output /work/firmware --cache /cache/firmware "$$@"; \
		python3 platform/bootstrap/build_sd.py --work /work/image --kernel-package /build/kernel/package --ssh-key /run/owner.pub --firmware /work/firmware --user "$$SD_USER" --size-mib "$$SD_SIZE_MIB"; \
		find /work/image -maxdepth 1 -type f -exec cp -p {} /output/ \;; \
		chown "$$OUTPUT_UID:$$OUTPUT_GID" /output/*; \
		echo "Finished SD kit exported to the selected output directory."'

SD_CARD ?=
.PHONY: sd-card-check sd-card-write
sd-card-check:
	@test -n "$(SD_CARD)" || { echo 'Set SD_CARD to the whole removable disk identifier, such as disk4.' >&2; exit 1; }
	python3 platform/bootstrap/write_card.py "$(SD_OUTPUT)" "$(SD_CARD)"
sd-card-write:
	@test -n "$(SD_CARD)" || { echo 'Set SD_CARD to the whole removable disk identifier, such as disk4.' >&2; exit 1; }
	python3 platform/bootstrap/write_card.py "$(SD_OUTPUT)" "$(SD_CARD)" --write

# The same pinned flasher source builds on the Mac, Linux, or the Nokia itself.
FLASHER_OUTPUT ?= $(CURDIR)/dist/flasher
FLASHER_CC ?= cc
FLASHER_TARGET ?= native
export FLASHER_CC FLASHER_USB_FLAGS
.PHONY: flasher flasher-help
flasher:
	python3 platform/flasher/build.py --output "$(FLASHER_OUTPUT)" --target "$(FLASHER_TARGET)"
flasher-help: flasher
	"$(FLASHER_OUTPUT)/0xFFFF" -h

FLASHER_HELPER_OUTPUT ?= $(FLASHER_OUTPUT)-helper
.PHONY: flasher-helper-prepare
flasher-helper-prepare: flasher
	python3 platform/flasher/prepare_macos_helper.py --build "$(FLASHER_OUTPUT)" --output "$(FLASHER_HELPER_OUTPUT)"

FLASHER_PREFIX ?= /usr/local
.PHONY: flasher-install
flasher-install: flasher
	install -d "$(DESTDIR)$(FLASHER_PREFIX)/bin" "$(DESTDIR)$(FLASHER_PREFIX)/share/doc/0xffff"
	install -m 755 "$(FLASHER_OUTPUT)/0xFFFF" "$(DESTDIR)$(FLASHER_PREFIX)/bin/0xFFFF"
	install -m 644 "$(FLASHER_OUTPUT)/BUILD.json" "$(FLASHER_OUTPUT)/source.tar.gz" "$(DESTDIR)$(FLASHER_PREFIX)/share/doc/0xffff/"
	@if test -f "$(FLASHER_OUTPUT)/COPYING"; then install -m 644 "$(FLASHER_OUTPUT)/COPYING" "$(DESTDIR)$(FLASHER_PREFIX)/share/doc/0xffff/"; fi
	install -m 644 platform/flasher/usb-host.patch platform/flasher/macos-nolo.patch "$(DESTDIR)$(FLASHER_PREFIX)/share/doc/0xffff/"

# Guided internal-storage installation stages share one backend with Pocket Setup.
INTERNAL_KIT ?= $(CURDIR)/dist/n810-internal
INTERNAL_PLAN ?=
INTERNAL_SIZE_MIB ?= 1536
INTERNAL_DOCKER_IMAGE ?= n810-internal-builder:local
INTERNAL_DOCKER_FLAGS ?=
INTERNAL_FIRMWARE_CACHE ?= n810-internal-firmware
INTERNAL_PASSWORD_STDIN ?= 0
N810_FLASHER ?= $(FLASHER_OUTPUT)/0xFFFF
N810_INSTALLER_HOST ?= 169.254.81.1
N810_INSTALLER_KEY ?=
N810_INSTALLER ?= python3 platform/bootstrap/internal_installer.py
.PHONY: n810-build-internal n810-check n810-identify n810-boot-installer n810-write-internal n810-flash-kernel
n810-build-internal:
	@if test -n "$(INTERNAL_PLAN)"; then \
		python3 platform/bootstrap/build_internal_image.py --plan "$(INTERNAL_PLAN)" --output "$(INTERNAL_KIT)"; \
	else \
		if test "$(INTERNAL_PASSWORD_STDIN)" != 1; then test -t 0 || { echo 'Run in a terminal for the local nokia password prompt.' >&2; exit 1; }; fi; \
		test -n "$(SSH_PUBLIC_KEY)" -a -f "$(SSH_PUBLIC_KEY)" || { echo 'Set SSH_PUBLIC_KEY to an Ed25519 public key file.' >&2; exit 1; }; \
		test -d "$(abspath $(dir $(INTERNAL_KIT)))" -a ! -e "$(INTERNAL_KIT)" || { echo 'Choose a new INTERNAL_KIT below an existing directory.' >&2; exit 1; }; \
		git diff --quiet HEAD && git diff --cached --quiet || { echo 'Commit source changes before building an identified kit.' >&2; exit 1; }; \
		disk_id=$$(python3 -c 'import secrets; print(secrets.token_hex(4))'); \
		bash -o pipefail -c 'python3 tools/package-source.py --list-context | COPYFILE_DISABLE=1 tar --null -T - -czf - | docker build $(INTERNAL_DOCKER_FLAGS) --progress=plain --file containers/internal-image.Dockerfile --build-arg DISK_ID=$$1 --build-arg SOURCE_COMMIT=$$2 -t $(INTERNAL_DOCKER_IMAGE) -' -- "$$disk_id" "$$(git rev-parse HEAD)" || exit; \
		set --; if test -n "$(MAEMO_BACKUP)"; then set -- --mount "type=bind,src=$$(cd "$(MAEMO_BACKUP)" && pwd),dst=/backup,readonly"; fi; \
		attach=-it; if test "$(INTERNAL_PASSWORD_STDIN)" = 1; then attach=-i; fi; \
		docker run --rm "$$attach" "$$@" \
			--mount "type=bind,src=$$(cd "$$(dirname "$(SSH_PUBLIC_KEY)")" && pwd)/$$(basename "$(SSH_PUBLIC_KEY)"),dst=/run/owner.pub,readonly" \
			--mount "type=bind,src=$(abspath $(dir $(INTERNAL_KIT))),dst=/output" \
			--mount "type=volume,src=$(INTERNAL_FIRMWARE_CACHE),dst=/cache/firmware" \
			-e SUDO_UID="$$(id -u)" -e SUDO_GID="$$(id -g)" \
			"$(INTERNAL_DOCKER_IMAGE)" python3 platform/bootstrap/build_internal_sources.py \
			--output "/output/$(notdir $(INTERNAL_KIT))" --ssh-key /run/owner.pub \
			--firmware-cache /cache/firmware --size-mib "$(INTERNAL_SIZE_MIB)" \
			$$(if test "$(INTERNAL_PASSWORD_STDIN)" = 1; then printf '%s' '--password-stdin'; fi) \
			$$(if test -n "$(MAEMO_BACKUP)"; then printf '%s' '--backup /backup'; fi) \
			$$(if test "$(SD_FIRMWARE_OFFLINE)" = 1; then printf '%s' '--offline'; fi); \
	fi
.PHONY: n810-install
n810-install: flasher
	$(N810_INSTALLER) install --kit "$(INTERNAL_KIT)" --flasher "$(N810_FLASHER)" --host "$(N810_INSTALLER_HOST)" $(if $(strip $(N810_INSTALLER_KEY)),--key "$(N810_INSTALLER_KEY)")
n810-check:
	$(N810_INSTALLER) check --kit "$(INTERNAL_KIT)"
n810-identify: flasher
	$(N810_INSTALLER) identify --flasher "$(N810_FLASHER)"
n810-boot-installer: flasher
	$(N810_INSTALLER) boot --kit "$(INTERNAL_KIT)" --flasher "$(N810_FLASHER)"
n810-write-internal:
	$(N810_INSTALLER) write --kit "$(INTERNAL_KIT)" --host "$(N810_INSTALLER_HOST)" $(if $(strip $(N810_INSTALLER_KEY)),--key "$(N810_INSTALLER_KEY)")
n810-flash-kernel: flasher
	$(N810_INSTALLER) flash-kernel --kit "$(INTERNAL_KIT)" --flasher "$(N810_FLASHER)"

.PHONY: n810-write-macos-internal
n810-write-macos-internal:
	@test -n "$(N810_DISK)" -a -n "$(N810_USB_LOCATION)" || { echo 'Set N810_DISK and N810_USB_LOCATION from the identified new tablet.'; exit 1; }
	python3 platform/bootstrap/write_macos_internal.py --kit "$(INTERNAL_KIT)" --disk "$(N810_DISK)" --usb-location "$(N810_USB_LOCATION)" $(if $(filter 1,$(N810_ERASE)),--write)

.PHONY: n810-install-macos
n810-install-macos: flasher
	$(N810_INSTALLER) install-macos --kit "$(INTERNAL_KIT)" --disk "$(N810_DISK)" --usb-location "$(or $(N810_USB_LOCATION),0)" --flasher "$(N810_FLASHER)"
