# Platform commands

This directory contains the N810 runtime commands and local checks. It does
not contain the old flasher, NAND-capture, kernel-build, or rescue scripts.

- **Power and display:** `n810-power`, `n810-powerd`, `n810-screen`,
  `n810-displayd`, `n810-backlightd.c`, `n810-wake.c`, `n810-ledd`.
- **Input and session:** `n810-keyboard`, `n810-fn-remap.c`, `n810-mode`,
  `n810-session`, `n810-tmux`, `n810-login`, `n810-dialog`.
- **Connections and apps:** `n810-wifi-service`, `n810-bluetooth`,
  `n810-communicator`, `n810-radio`, `n810-pocket`, `n810-setup`.
- **Checks:** `test-*` and `validate-*` run locally only where their
  requirements are met. No device acceptance follows from a host test.

`../device/` contains the service files and keymaps these commands use.
Relative source paths were adjusted from the local OS tree; no installation
claim is made for this new layout.
