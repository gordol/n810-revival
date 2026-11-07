# Installation

## Portable desktop

The portable desktop runs on macOS or Linux with Python 3.11 or newer and Make. Obtain
an N810 Revival source checkout or extract its source archive, then enter the
`pocket` directory inside it:

```sh
cd pocket
make
```

If you are already inside `pocket`, run just the Make command. The commands
throughout this manual use that directory as their starting point. The
[getting-started walkthrough](../../docs/tutorials/first-session.md) provides
ZIP and Git download options and first-session controls.

Instance state defaults to `$XDG_STATE_HOME/pocket/INSTANCE`, or
`~/.local/state/pocket/INSTANCE`. Choose an explicit location with
`make n810 EXTRA='--state /path/to/private/state'`.

The shell includes the existing Python sources and small bundled resources.
Large regional map packs, radio identities, credentials, captured traffic, and
user databases are not installation prerequisites and are not created as fake
live data. Missing services remain unavailable until explicitly attached.

## Optional native compositor

Install a C compiler and the development headers matching Python, then run
`make native`. Builds go to `$XDG_CACHE_HOME/pocket/native`, or
`~/.cache/pocket/native`. Source hashes and interpreter/platform identity select
a matching build. Compilation failure leaves the Python renderer usable.

## Native service codec

For small devices, install the optional MessagePack C extension in the shell's
Python environment and each service owner's environment:

```
python3 -m pip install -r requirements-performance.txt
```

On Debian, `python3-msgpack` supplies the native extension for system Python and
virtual environments using system site packages. Isolated virtual environments
need their own installation. Binary wheels avoid an on-device compiler; source
builds require a C/C++ compiler and Python development headers.

The service frame format stays the same. Without the extension the bundled
portable codec remains available. `wire.NATIVE_CODEC` reports which implementation
an owner uses; installing the dependency does not connect or share services.

## Hardware and optional applications

The N810 framebuffer/VT, touch, fonts, privileged supervisor, and radio service
installation remain device-specific. This source release does not replace the
installed Nokia image or its supervisor. The preserved native sources and
adapters require a separate target build and device acceptance.

Reticulum/LXMF owners require their recorded upstream dependencies and an
explicit radio/owner configuration. No dependency download or radio activation
occurs merely by launching the shell. Optional demonstration apps may require
assets or acceleration providers; the shell remains usable without them.

Existing configured Nokias receive the fixed Bluetooth mapping helper through
the release installer. It upgrades only a reviewed predecessor and retains the
previous helper for rollback. An unchanged mapping is checked without opening
the serial device; creating mappings and preparing a new bond remain platform
setup tasks.
