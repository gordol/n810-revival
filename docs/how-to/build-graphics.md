# Build the imported MBX and Mesa checkpoint

These commands build the earlier 4 November MBX/Mesa source checkpoint, including its packet encoders, kernel module, and Mesa integration. For the later command-reuse and FIFO changes that produced the repeated 30 FPS result, use the [30 FPS driver guide](build-gpu-30fps.md).

Use a Debian Linux builder with at least 3 GiB of free space. Install the kernel prerequisites from the [kernel guide](build-kernel.md), plus:

The container build supplies the pinned Meson and Python environment:

```sh
make container-check DOCKER_STAGE=graphics
```

For a manually prepared Linux build environment:

```sh
sudo apt-get install gcc-arm-linux-gnueabi g++-arm-linux-gnueabi     binutils-arm-linux-gnueabi meson ninja-build pkg-config python3-mako     python3-packaging python3-yaml dpkg-dev
```

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
