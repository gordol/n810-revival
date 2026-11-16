# Build MBX and Mesa

These commands build the portable Mesa integration with the maintained Pocket driver overlay from `pocket/graphics/driver/mbx/`. The module and Mesa use the same assembled common interfaces, and their build records hash the effective inputs. Explicit historical checkpoints retain their frozen sources; for the repeated 30 FPS checkpoint, use the [30 FPS driver guide](build-gpu-30fps.md).

Use a Debian Linux builder with at least 3 GiB of free space. Install the kernel prerequisites from the [kernel guide](build-kernel.md).

The container build supplies the pinned Meson and Python environment:

```sh
make container-check DOCKER_STAGE=graphics
```

For a manually prepared Linux build environment, run these commands from the repository root:

```sh
sudo apt-get install gcc-arm-linux-gnueabi g++-arm-linux-gnueabi \
    binutils-arm-linux-gnueabi ninja-build pkg-config dpkg-dev python3-venv
python3 -m venv .venv-mesa
.venv-mesa/bin/python -m pip install meson==1.5.2 Mako==1.3.5 \
    packaging==24.1 PyYAML==6.0.2 setuptools==75.1.0
export PATH="$PWD/.venv-mesa/bin:$PATH"
```

Keep that shell open for the build commands. The virtual environment supplies Meson and its Python dependencies together, including the compatibility support needed by this Mesa release on newer Python versions.

The kernel module uses the completed kernel build directory, including its generated headers and symbol-version table:

```sh
python3 graphics/mbx/build.py module --work /tmp/mbx-module-build     --kernel-source /tmp/n810-kernel-build/linux-5.15.224     --kernel-build /tmp/n810-kernel-build/build
python3 graphics/mbx/build.py mesa --work /tmp/mbx-mesa-build --jobs 4
```

The Mesa builder downloads the pinned Mesa archive and 34 pinned Debian packages, verifies their checksums, extracts a local sysroot, applies the owned integration, and compiles `libGL.so.1`. The sysroot supplies the Debian armel headers and libraries used for userspace compatibility. The module builder checks each imported symbol's version against the kernel build.

Both commands require a new output directory. Each produces a `package/BUILD.json` record and detailed logs. [Graphics source inputs](../reference/graphics-inputs.md) describes the directory layout. [Build verification](../reference/component-build-verification.md) records the compiler, library compatibility, and module symbol checks for each checkpoint.

The container pins Meson 1.5.2 and its Python dependencies. Debian Bookworm’s
older Meson does not recognize the `pkg-config` cross-file entry used here.
Use the container target for the tested compiler and dependency combination.
