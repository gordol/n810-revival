# N810 platform files

These are operating-system sources and build inputs for the tablet.

| Directory | Purpose |
|---|---|
| `kernel/` | Maintained Linux 5.15.224 source changes, configuration, pinned inputs, and a portable Linux build script. |
| `bootstrap/` | Linux builder for a personalized Debian armel SD-card image, using a matching kernel package. |
| `patches/` | Historical source patches retained for the journal, including the earlier RGB console extension. |
| `scripts/` | Commands and helpers that run on the N810, plus local source tests. |
| `device/` | Init scripts, systemd units, keymaps, and configuration installed into the tablet's root filesystem. |
| `config/` | Package lists and configuration templates. |

The [kernel guide](../docs/how-to/build-kernel.md) builds a kernel, generated device
tree, matching modules and a result manifest. Pocket's application packaging
adapter lives under `pocket/platform/n810/`.

The runtime files use `device/` for their destination in the tablet filesystem.
The [journal checkpoint guide](../docs/how-to/test-journal-checkpoints.md) covers
the console harness, flash readers, ARM helper build and platform tests.
The [fresh SD guide](../docs/how-to/prepare-fresh-n810.md) builds a Debian root
and card image. Device-specific firmware, a verified NOLO procedure, and a first
boot on another N810 remain separate. The [status page](../docs/status.md)
records the checks completed for these components.
