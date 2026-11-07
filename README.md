# N810 revival

Debian and a terminal desktop on the Nokia N810. The tablet has 128 MB of RAM,
an 800 × 480 screen, and a slide-out keyboard. The work here is to make it a
useful general-purpose Linux computer again.

## Where things are

| Directory | Contents |
|---|---|
| [`pocket/`](pocket/) | Current terminal desktop and apps. `make -C pocket n810` runs it on a laptop. |
| [`platform/`](platform/) | N810 kernel build inputs, OS commands, configuration, and service files. `platform/device/` holds files intended for the tablet's filesystem. |
| [`hardware/htit/`](hardware/htit/) | Hub and microReticulum executor firmware, board inputs and tests. |
| [`graphics/mbx/`](graphics/mbx/) | Imported MBX/Mesa source checkpoint; GPU bring-up continues. |
| [`docs/`](docs/) | Project site and dated field notes. |

Pocket has its own Nokia packaging adapter in `pocket/platform/n810/`. The
top-level `platform/` directory is the lower-level OS work. Pocket bundles the packet-console code used by its current applications.

## Read and run

- [Project site](docs/index.md) · [guides](docs/guides.md) · [current status](docs/status.md) · [chronological journal](docs/journal.md)
- [Pocket setup](pocket/docs/install.md) · [navigation](pocket/docs/navigation.md) · [connections](pocket/docs/connections.md)
- [Platform file map](platform/README.md) · [kernel build](docs/how-to/build-kernel.md)

```sh
make -C pocket n810    # laptop terminal, no Nokia required
make pocket-smoke       # focused local checks
make docs-check         # after make docs-install
```

The kernel build reconstructs the maintained Linux source and produces matching
modules from repository inputs plus a checksum-pinned upstream archive. Device
installation also depends on the intended storage layout, firmware, calibration
and recovery procedure. The [status page](docs/status.md) records demonstrated
results and remaining installation work.

Download and build offline map data with `make maps-download`, `make maps`, and
`make maps-terrain` from `pocket/`. The [map build guide](docs/how-to/build-map-data.md)
covers dependencies, selected-area elevation and source attribution. Map downloads
and generated packs are excluded from the source repository.

## Contributing and review

Read [CONTRIBUTING.md](CONTRIBUTING.md) for the branch, test, privacy, and
attribution workflow. [AGENTS.md](AGENTS.md) records the rules for automated work.
Run `make release-archives` to build and check the source and documentation archives
in Docker. GitHub Actions runs the same container build.

## License

Read the [software GPL grant](licenses/ORIGINAL-CODE-GPL.md), the [documentation license](LICENSE.md), and the [component boundaries](LICENSING.md). Copyright © 2026 Thomas Gordon Lowrey IV for covered original material. HAIL ERIS.

Contributor credit is recorded in [CONTRIBUTORS.md](CONTRIBUTORS.md). The [original software grant](licenses/ORIGINAL-CODE-GPL.md) permits GPL-compliant commercial distribution. The optional [Contributor Agreement](CONTRIBUTOR-AGREEMENT.md) requires explicit acceptance for additional rights in identified contributions. [License review](docs/license-review.md) records existing terms and remaining clearance work.
