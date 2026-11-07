# Historical sidebar desktop

This is the retained Xorg/fbdev, Matchbox and XFCE prototype described in the 5 October journal entry. `n810-rail.c` implements the 48-pixel application rail. `kbdconfig` supplies its hardware-key bindings; `xorg-config.py` derives the touch mapping from a supplied calibration file. The `xfce/` directory contains the XFCE proof-of-concept settings.

The [journal checkpoint guide](../../docs/how-to/test-journal-checkpoints.md#check-the-sidebar-and-phone-terminal) gives the host dependencies, virtual-display tests and ARM build command. `build-armel.sh` uses the platform helpers in this repository and checksum-pinned Debian X11 libraries. `test-rail.sh` checks the application rail on an isolated virtual display. The other display and session scripts document attended tablet operations.

The original prototype's source was imported for historical study. Pocket's terminal desktop has its own launcher and packaging under `pocket/`.
