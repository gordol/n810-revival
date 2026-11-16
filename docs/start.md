# Set up an N810

Pocket's N810 system uses Debian armel, a device-specific Linux kernel and a
managed desktop launcher. Keep the tablet's charger connected during installation.

## A tablet running its original Maemo system

Start by preserving the original system and device-specific calibration.
[N810 Setup](pocket/bootstrap.md) builds complete Debian/Pocket kits for internal
storage or SD, including the matching kernel and modules. Read its host support
matrix and prerequisites before building. The guarded storage writers currently
require macOS; Windows, Linux and BSD do not yet have equivalent complete install
workflows. Physical acceptance of the new complete SD route remains outstanding.

The [minimal SD image guide](how-to/prepare-fresh-n810.md) is a separate developer
route and does not include the complete Pocket desktop.

## A tablet already running our Debian system

1. Connect over [SSH](how-to/ssh.md).
2. Follow [Update Pocket](pocket/nokia.md) to build and install the application
   package using the existing supervisor.
3. Follow [Start the GPU desktop](how-to/run-n810-gpu.md).

The update package requires the existing platform installation and its native
libraries. The package guide lists those inputs.

## Try Pocket on a laptop

With Python 3.11 or newer, Make and Git installed:

```sh
git clone https://github.com/gordol/n810-revival.git
cd n810-revival/pocket
make
```

Follow [Your first Pocket session](tutorials/first-session.md) for the controls,
or [Build the graphical desktop](pocket/graphics.md) to open a graphical window.
