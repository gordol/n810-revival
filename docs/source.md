# What is in this repository

## Pocket

`pocket/` is the current terminal desktop. It has the shell, bundled app
domains, local and remote service adapters, source tests, and the Nokia package
adapter. On a laptop, `make -C pocket n810` opens a local shell. Connections
and radio activation are explicit.

The Pocket tree omits local histories, experiments, hardware work folders,
private provenance notes, and prepared regional map data. Some map and scene
views therefore need a separately installed data pack. The code is here;
private or location-specific datasets are not.

## Platform

`platform/` contains OS-side runtime source. Its `device/` directory is made
of files destined for the N810 root filesystem: init scripts, systemd units,
keymaps, and policy configuration. `scripts/` contains commands and tests;
`config/` holds templates and package lists. There is no VM image here.

The platform slice is not a complete installer. Its original development tree
and recovery material stay local. The [platform README](https://github.com/gordol/n810-revival/blob/main/platform/README.md)
lists the file groups and their use.

## Not in this snapshot

The older `pocket-x11` prototype, separate packet-console Git history,
firmware, kernel trees, device backups, raw captures, and internal engineering
ledgers are not imported. [Publication boundary](publication.md).
