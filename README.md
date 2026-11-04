# N810 revival

Debian and a terminal desktop on the Nokia N810. The tablet has 128 MB of RAM,
an 800 × 480 screen, and a slide-out keyboard. The work here is to make it a
useful general-purpose Linux computer again.

## Where things are

| Directory | Contents |
|---|---|
| [`pocket/`](pocket/) | Current terminal desktop and apps. `make -C pocket n810` runs it on a laptop. |
| [`platform/`](platform/) | N810 OS-side commands, configuration, and service files. `platform/device/` holds files intended for the tablet's filesystem. It is **not** a VM. |
| [`docs/`](docs/) | Project site and dated field notes. |

Pocket has its own Nokia packaging adapter in `pocket/platform/n810/`. The
top-level `platform/` directory is the lower-level OS work. The older X11
prototype and the separate packet-console history are not imported here.

## Read and run

- [Project site](docs/index.md) · [current status](docs/status.md) · [journal](docs/journal.md)
- [Pocket setup](pocket/docs/install.md) · [navigation](pocket/docs/navigation.md) · [connections](pocket/docs/connections.md)
- [Platform file map](platform/README.md)

```sh
make -C pocket n810    # laptop terminal, no Nokia required
make pocket-smoke       # focused local checks
make docs-check         # after make docs-install
```

This repository is source, not a ready-to-flash image or a complete clean-build
recipe for another N810. Device installation, radio operation, and kernel work
have separate evidence and recovery requirements. The [status page](docs/status.md)
says what was demonstrated and what remains open.

No device images, firmware, backups, credentials, personal tracks, or raw radio
logs are included. The [publication note](docs/publication.md) describes the
selection and the remaining license review. The site is not deployed by this
repository.
