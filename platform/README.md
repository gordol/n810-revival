# N810 platform files

These are operating-system sources and build inputs for the tablet.

| Directory | Purpose |
|---|---|
| `kernel/` | Maintained Linux 5.15.224 source changes, configuration, pinned inputs, and a portable Linux build script. |
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
A complete root-filesystem image additionally needs a Debian root, firmware and
installation policy. The [status page](../docs/status.md) records the build and
device checks completed for these components.
