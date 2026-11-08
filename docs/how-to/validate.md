# Run the Pocket tests

With Docker, Python 3 and Make available, clone the repository and run the
complete container build:

```sh
git clone https://github.com/gordol/n810-revival.git
cd n810-revival
```

From that repository root:

```sh
make container-check
```

This builds the kernel, frozen graphics checkpoint, HTIT firmware and graphical
frontend. It runs the full Pocket and bundled radio suites as a normal user with
network access disabled, then runs the HTIT host checks and software-OpenGL GUI
checks. Dependency installation happens in separate cached build stages. The first build
needs network access to download those dependencies. Docker reuses matching
layers on later runs.

The [7 November hosted verification](../reference/component-build-verification.md#github-container-build-7-november)
passed 205 source test files and the HTIT host suites at revision `b331ac7`.
To reproduce that source revision, run `git checkout b331ac7` before the build.
A successful command exits with status zero.

To build and export the separate source and documentation archives, run:

```sh
make release-archives
```

The archives and their checksums appear in `dist/`. This target includes the
container checks and reuses matching build layers. Use
`make container-check-clean` when you explicitly want to rebuild every stage.

With Python 3.11 or newer and Make installed, run the focused host tests from the repository root:

```sh
make pocket-smoke
```

`pocket-smoke` checks the codec, navigation, touch worker, launcher, lazy startup, and panel tray.

For the full Pocket and bundled radio suites, use a normal user account and install the test dependencies into the Python environment you will use:

```sh
python3 -m pip install -r requirements-maps.txt
python3 tools/check-source.py --work /tmp/n810-source-check --jobs 2
```

The runner gives each test process a private temporary home and records its result and log. Use Python 3.11 or newer with NumPy and Pillow; `requirements-maps.txt` supplies a tested conversion environment. The work directory must be new. Nokia session checks enforce normal-user execution.

Regional map data is downloaded and built separately. The [map build guide](build-map-data.md) describes regional acquisition and the independent fixture checks.

On Linux, the proxy test also needs D-Bus and GLib bindings available to the selected Python interpreter. Debian’s `python3-dbus` and `python3-gi` packages supply them for Debian’s `/usr/bin/python3`; a virtual environment made from that interpreter with `--system-site-packages` can use them. A separately installed Python needs its own matching bindings. On other hosts the runner identifies that Linux-only suite explicitly.

The map and terrain suites generate fictional raster, vector and elevation packs
in temporary directories. The fixtures cover renderer loading, source selection,
profiles, line-of-sight workers, cancellation and package dependency checks.
They require no regional download. A separate FCC integration test identifies
its prepared real-data snapshot requirement and skips when that snapshot is absent.
The [build verification](../reference/component-build-verification.md#fresh-checkout-walkthrough-7-november)
records the original failures and their corrections.

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

On a Linux builder without a display, install Xvfb, `xauth`, and Mesa software
OpenGL along with the graphical build dependencies, then run from `pocket/`:

```sh
xvfb-run -a make graphics-check EXTRA=--allow-software
```

The explicit software option permits this container test to use llvmpipe.
The result reports its renderer and checks input, resizing, and Room output.
