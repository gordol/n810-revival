# Set up an N810

Pocket's N810 system uses Debian armel, a device-specific Linux kernel and a
managed desktop launcher. Keep the tablet's charger connected during installation.

## A tablet running its original Maemo system

Start by preserving the original system and device-specific calibration. Prepare
an SD card for Debian, then install the matching N810 kernel, modules and firmware.
The desktop and its supervisor are installed after Debian boots successfully.

The project still needs a tested, end-to-end first-install kit for this route.
A stock N810 owner should wait for that kit before replacing the installed system.
The [kernel build guide](how-to/build-kernel.md) and
[platform reference](reference/platform-files.md) provide the components available
for developers preparing an installation.

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
