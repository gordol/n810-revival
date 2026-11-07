# Pocket

Pocket is the N810's terminal desktop: windows, keyboard and touch input,
local apps, and explicit connections to separately owned services. It also
runs on a laptop for development.

## Run it locally

From this directory:

```sh
make
```

Python 3.11 or newer and a UTF-8 terminal are required. The shell starts
locally; it does not contact a Nokia or activate a radio by opening. Use
**Connections** to attach a local service socket or a previously configured
remote host. **Ctrl-]**, then **q**, quits. See [navigation](docs/navigation.md)
and [connections](docs/connections.md).

## Source layout

| Path | Contents |
|---|---|
| `shell/launch.py`, `shell/desktop.py` | Startup and the window host. |
| `shell/apps/` | Registered app modules, including renderer, map library, touch lab, and optional Doom adapter. Registration is not device acceptance. |
| `shell/owner-service/` | Processes that own shared radio and device services. |
| `shell/native/` | Optional C code and its build instructions. |
| [`shell/vendor/`](shell/vendor/README.md) | Imported domain code and dependencies used by Pocket. The older packet console implementation is carried here as source, without its separate Git history. |
| `shell/heard/` | Heard station UI and model. |
| `platform/n810/` | Packaging adapter for the existing Nokia supervisor. It is not the OS platform tree at the repository root. |
| `tools/` | Explicit build, package, data preparation, and profiling commands. |
| `tests/` | Local and integration tests; some need reference data or host facilities absent from this selected tree. |
| `docs/` | Setup, controls, connections, and service behavior. |

The source here omits local Git history, experimental work folders, private
provenance notes, and prepared regional maps. Map and scenery views may need
separately installed reference data. The portable shell is the first thing to
try; Nokia packaging has a distinct build and acceptance path in
[the install guide](docs/nokia.md).

Version 0.1.0 names the integrated source release. It does not certify every
physical radio, input, or long-session path. [Release notes](docs/releases-0.1.0.md).
