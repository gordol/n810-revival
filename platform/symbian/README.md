# Native Symbian runtime

The N810 runs application ARM code through a compatibility layer built from
EKA2L1. `runtime/` supplies native execution, input and MBX rendering adapters.

## Launch an installed application

The managed GPU desktop and Symbian launcher must be installed on the tablet.
Open **Symbian** from Pocket's application menu, then press Enter for ChessGenius
or S for Snakes. Closing the application returns to the saved Pocket desktop.

From a checkout on the N810:

```sh
cd pocket
make symbian APP=chess
make symbian APP=snakes
```

Both commands request the existing desktop owner. The owner serializes desktop
and application execution and keeps the GPU and display session under its control.

## Private inputs

Place the compiled runtime at
`~/.local/share/symbian-private/code/symbian-runtime`. The prepared system
libraries and installed applications live under
`~/.local/share/symbian-private/runtime/`.
Users supply compatible system libraries and application installers privately.

## Source

`PROVENANCE.json` pins EKA2L1. Apply `eka2l1.patch` to that revision, copy
`upstream-additions/` over its source tree, and add the `runtime/` adapters.
A portable dependency/bootstrap build recipe remains to be completed.
EKA2L1-derived source retains the accompanying GPL terms.
