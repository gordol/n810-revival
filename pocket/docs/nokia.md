# Nokia console installation

The portable source release runs through `make n810` on the Nokia as well as
on a desktop when Make is installed. Without Make, run
`python3 shell/launch.py --instance default`, the same entrypoint. Python 3.11
or newer is required for the portable shell. Optional
native composition improves performance on the Nokia.

For an N810 already using the guarded Pocket console supervisor, build an
installable version with:

```
python3 tools/package_nokia.py --files --platform-release /path/to/5e63c3f/nokia.tar.gz --native-reticulum /path/to/tested-arm-build
```

The platform archive is an explicit build input, not a neighboring source
checkout. The packager verifies its original manifest and engine identity,
reuses the original platform libraries when compositor sources are unchanged.
For a rebuilt compositor, supply `--native-compositor /path/to/arm-build`; the
packager verifies its source hashes, binary hash and ARM soft-float ABI.
All Python application code comes from the committed active tree.
The runtime payload excludes tests, benchmarks, packet-test fixtures and
compile-only Doom and native Reticulum sources. Licenses, runtime feature
assets and source inputs required for native-library verification remain.
`CONTENTS.json` lists the included/excluded file accounting. Full development
sources remain in the repository and source archive, outside the app payload.
Build that target with `python3 tools/build_native.py --arm-headers /path/to/extracted/usr/include --output /path/to/arm-build`
in a Linux environment with the ARM soft-float cross compiler and Debian ARM
Python 3.11 development headers. Add `--arm-vfp` for the N810 ARM1136 VFP
unit, retaining the soft-float calling convention. Verify `vfp` in the target
CPU features and run the native scene output tests before installing that build.
The build records compiler flags, CPU requirements and header hashes.

Nokia releases require the native microReticulum/microLXMF library. The packager
refuses a missing library or mismatched ARM provenance. See
[the native build instructions](../shell/native/reticulum/README.md) for the
cross-compile procedure. Python RNS/LXMF is not a Nokia runtime dependency and
is not a fallback: unsupported connections report an error. Nokia packages omit
the desktop Python stack loader. Shared owner code remains because the native
backend uses its service and messaging policies too. The shared source retains
the desktop Python backend and interoperability tests. A desktop launch
with `make n810` is still a desktop process; the Make target name does not select
the Nokia release policy.

For development, `--files` produces a `files/` tree, installer scripts and an
`INSTALL.json` receipt under `dist/pocket-COMMIT-files`. Sync them directly:

```
python3 tools/sync_nokia.py dist/pocket-COMMIT-files --ssh-key /path/to/n810-key
```

The sync uses compressed rsync with content comparisons and the installed app
as a local copy basis. Only changed file data crosses SSH; unchanged native
libraries and bundled resources are copied locally into staging. The running app
tree is not modified during transfer. No app archive is transferred or unpacked.
The command prints the staging directory. Stop Pocket and its app-tree owners,
run that directory's `install.py` as root, then restart the same owners and Pocket.
Keep normal reference-data sync separate from app changes.

Omit `--files` when an archive is specifically needed for distribution. That
output includes `nokia.tar.gz` and uses the same installer and verification.
The platform session-entry update is reused when already current.
The installer uses the installed supervisor's existing locks,
validation and rollback catalog. It preserves the previous release, calibration,
keyboard setup, owner configuration, identities, messages and receiver services.
It refuses mismatched supervisor contracts or an occupied console. After registration,
it verifies each installed source hash and prepares timestamp-validated Python
caches. Imports check source modification time and size without rereading every
source file. Release sources and caches are root-owned; install a new release
instead of editing them in place. The cache receipt records each source and
generated cache hash. Unchanged verified Python bytecode is reused even when
staging gives its source a different modification time.

Start normally with `sudo -n /usr/local/sbin/n810-pocket-console run`. Connections
opens first and configured local services attach in the background. Remote device
connections remain explicit. Attaching to a Reticulum management owner does not
activate its radio; Radio Connect remains a separate action in Reticulum. An
already running owner's state is displayed without reconfiguring it.

This adapter requires the existing supervisor and fixed map-pack installation;
it is not a general installer for an unconfigured Nokia. A new computer can run
the portable shell without those components. Roll back with the existing
`n810-pocket-version` selector after closing the desktop.

Product versions and the current package policy are documented in [versioning](versioning.md).
Offline reference snapshots are installed separately at `/usr/share/pocket/data`;
`POCKET_DATA_ROOT` can explicitly select another dataset. User state is separate.
