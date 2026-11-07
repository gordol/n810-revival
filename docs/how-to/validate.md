# Run the Pocket tests

With Python 3.11 or newer and Make installed, run the focused host tests from the repository root:

```sh
make pocket-smoke
```

`pocket-smoke` checks the codec, navigation, touch worker, launcher, lazy startup, and panel tray.

For the full Pocket and bundled radio suites, run:

```sh
python3 tools/check-source.py --work /tmp/n810-source-check --jobs 2
```

The runner gives each test process a private temporary home and records its result and log. Use Python 3.11 or newer with NumPy and Pillow; `requirements-maps.txt` supplies a tested conversion environment. Synthetic fixtures are included in the checkout. Regional map data is downloaded and built separately; it is not distributed in Git. See the map build guide and `pocket/docs/testing.md` for the reference-data integration suite. On Linux, the proxy test also needs `python3-dbus` and `python3-gi`. On other hosts the runner identifies that Linux-only suite explicitly.

The [HTIT guide](build-htit.md) supplies firmware and host-protocol checks. The [map guide](build-map-data.md) supplies real-data rebuilds and format-conversion tests.

For platform changes, select the relevant tests under `platform/scripts/`. Boot-mode, zram cleanup, and dialog cancellation have focused checks that can run on the host. A device test additionally needs the target kernel, installed services, and an attended observation of the behavior being changed.

The [journal checkpoint guide](test-journal-checkpoints.md) gives commands for the platform helpers, console-color regression harness, historical desktop, and other earlier implementations.

## Graphical desktop

From `pocket/`, run `make graphics-check` after installing the dependencies in
[the graphics guide](../pocket/graphics.md). This builds all frontend
sources, checks native text/mouse/focus handling and frame borders across five
window sizes, then runs the actual desktop with menu, app and resize actions in
isolated state. It reports the OpenGL renderer used. The release container also
builds this path and runs it under explicit Mesa software GL; that checks
portability, not Nokia GPU performance. Its ARM framebuffer cross-build likewise
does not establish device installation or physical display acceptance.
