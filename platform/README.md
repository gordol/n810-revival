# N810 platform files

These are OS-side sources for the tablet. This directory is not a virtual
machine and does not contain a disk image.

| Directory | Purpose |
|---|---|
| `scripts/` | Commands and helpers that run on the N810, plus local source tests. |
| `device/` | Init scripts, systemd units, keymaps, and configuration installed into the tablet's root filesystem. Older local notes called this directory `vm/`; the files themselves are device files. |
| `config/` | Package lists and configuration templates. |

This is the runtime source slice. It does not include the old rescue scripts,
flasher-VM setup, NAND capture tools, kernel builds, or a complete installer.
Pocket's current app packaging code is under `pocket/platform/n810/`.

The original OS development tree remains separate and unchanged. Moving these
files under `platform/` and renaming `vm/` to `device/` changed relative paths
in this snapshot; treat this as source pending an integrated device build,
not as a tested deployment bundle.
