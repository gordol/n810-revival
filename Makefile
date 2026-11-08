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
SD_BUILD_FLAGS ?=
export SSH_PUBLIC_KEY SD_OUTPUT SD_SIZE_MIB SD_USER SD_JOBS SD_DOCKER_IMAGE
.PHONY: sd-image
sd-image:
	@test -t 0 || { echo 'Run make sd-image in a terminal for the local password prompt.' >&2; exit 1; }
	@test -n "$$SSH_PUBLIC_KEY" && test -f "$$SSH_PUBLIC_KEY" || { echo 'Set SSH_PUBLIC_KEY to your Ed25519 .pub file.' >&2; exit 1; }
	@test ! -e "$$SD_OUTPUT" || { echo 'SD_OUTPUT must be a new directory.' >&2; exit 1; }
	docker build $(SD_BUILD_FLAGS) --progress=plain -f containers/sd-image.Dockerfile --build-arg JOBS="$$SD_JOBS" -t "$$SD_DOCKER_IMAGE" .
	@umask 077; mkdir -p "$$SD_OUTPUT"
	@docker run --rm -it --mount "type=bind,src=$$(cd "$$(dirname "$$SSH_PUBLIC_KEY")" && pwd)/$$(basename "$$SSH_PUBLIC_KEY"),dst=/run/owner.pub,readonly" \
		--mount "type=bind,src=$$(cd "$$SD_OUTPUT" && pwd),dst=/output" \
		-e OUTPUT_UID="$$(id -u)" -e OUTPUT_GID="$$(id -g)" \
		-e SD_USER -e SD_SIZE_MIB "$$SD_DOCKER_IMAGE" sh -ec '\
		arch-test armel; \
		python3 platform/bootstrap/build_sd.py --work /work/image --kernel-package /build/kernel/package --ssh-key /run/owner.pub --user "$$SD_USER" --size-mib "$$SD_SIZE_MIB"; \
		find /work/image -maxdepth 1 -type f -exec cp -p {} /output/ \;; \
		chown "$$OUTPUT_UID:$$OUTPUT_GID" /output/*; \
		echo "Finished SD kit exported to the selected output directory."'
