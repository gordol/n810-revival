# Get started

## Set up an N810

The tablet runs Debian armel, the N810 kernel and modules, and the Pocket console services. The installation route depends on the software already running on your tablet.

| Your starting point | Next step |
| --- | --- |
| An N810 running Maemo or another original system | First-install preparation is still in development. The required inputs are described below. |
| An N810 already running Debian and the Pocket console supervisor | Follow the [Nokia package and installation guide](pocket/nokia.md). It lists the platform archive and native library inputs required to build an update. |
| A configured N810 that you want to use from a laptop | Follow [Use Pocket over SSH](how-to/ssh.md). |
| A laptop where you want to explore the desktop | Follow [Your first Pocket session](tutorials/first-session.md). |

### First-install preparation

A complete first installation needs a Debian armel filesystem, matching kernel and modules, firmware and calibration handling, a storage layout, and a tested boot and recovery procedure. The project is assembling these into a reproducible installation kit. The complete procedure still needs verification on another N810.

The [kernel build guide](how-to/build-kernel.md) reproduces the kernel and modules from the included source inputs. The [platform reference](reference/platform-files.md) describes the runtime scripts and their role in the tablet system. These are individual parts of the installation kit.

## Explore Pocket on your laptop

Python 3.11 or newer, Make, and a UTF-8 terminal are the prerequisites for the portable desktop. With Git installed, download and launch it with:

```sh
git clone https://github.com/gordol/n810-revival.git
cd n810-revival/pocket
make
```

The [first-session tutorial](tutorials/first-session.md) also provides a ZIP download and explains the initial Connections window, Help, opening applications, and quitting. The [installation reference](pocket/install.md) explains optional dependencies for native rendering and service owners.

### Open the native graphical desktop

The [graphical frontend guide](pocket/graphics.md) lists its compiler, SDL2, OpenGL, and optional Mac compute dependencies. After preparing those dependencies, run `make gui` from the same `pocket/` directory. It builds the native frontend as needed and opens the shared Pocket desktop in an application window. `make` continues to launch the terminal frontend.

The [native desktop journal](posts/2026-11-07-native-desktop.md) shows the rendering path and resize behavior, and the [Surface Room entry](posts/2026-11-07-surface-room.md) explains its movement and target-range controls.
