# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
# Build all five inputs for the internal MMC kit from one tracked source tree.
FROM python:3.13-bookworm@sha256:cc55e4ded9c95f6ce2133b3d096db43f214d280c2a8af65d83e246c8fa7d168c
COPY platform/bootstrap/debian.sources.list /etc/apt/sources.list
RUN rm -f /etc/apt/sources.list.d/*

RUN dpkg --add-architecture armel && apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libbz2-dev git flex bison bc libssl-dev libelf-dev kmod curl ca-certificates \
    xz-utils patch gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    gcc-arm-linux-gnueabi g++-arm-linux-gnueabi binutils-arm-linux-gnueabi \
    ninja-build pkg-config dpkg-dev mmdebstrap qemu-user-static binfmt-support \
    arch-test e2fsprogs liblzo2-2 \
    && apt-get download libpython3.11-dev:armel libusb-dev:armel libusb-0.1-4:armel libbz2-dev:armel libbz2-1.0:armel \
    && mkdir -p /opt/arm-sysroot \
    && for package in ./*_armel.deb; do dpkg-deb -x "$package" /opt/arm-sysroot; done \
    && rm -f ./*_armel.deb \
    && rm -rf /var/lib/apt/lists/*
COPY platform/bootstrap/builder-requirements.lock /build/builder-requirements.lock
RUN python3 -m venv /opt/mesa-tools && /opt/mesa-tools/bin/pip install --only-binary=:all: --require-hashes --no-deps -r /build/builder-requirements.lock
RUN dpkg-query -W > /build/BUILDER-PACKAGES.tsv
WORKDIR /src
COPY platform/config/n810-mesh*-requirements.txt /build/requirements/
RUN /opt/mesa-tools/bin/pip download --only-binary=:all: --no-deps --require-hashes \
    -r /build/requirements/n810-mesh-requirements.txt \
    -r /build/requirements/n810-meshcore-requirements.txt -d /build/service-wheels
COPY platform/kernel/ platform/kernel/
ARG DISK_ID
ARG AB_BOOT=0
RUN test "${#DISK_ID}" = 8 \
    && python3 platform/kernel/build.py --work /build/kernel \
       --root-device "PARTUUID=${DISK_ID}-01" --jobs 4 $(if test "$AB_BOOT" = 1; then printf %s --ab-boot; fi)
COPY graphics/mbx/ graphics/mbx/
COPY pocket/graphics/driver/mbx/ pocket/graphics/driver/mbx/
RUN python3 graphics/mbx/build.py module --work /build/module \
    --kernel-source /build/kernel/linux-5.15.224 --kernel-build /build/kernel/build
RUN --mount=type=cache,id=n810-internal-mesa-inputs,target=/cache/mesa-inputs,sharing=locked \
    PATH=/opt/mesa-tools/bin:$PATH python3 graphics/mbx/build.py mesa \
    --work /build/mesa --jobs 4 --osmesa --download-cache /cache/mesa-inputs
COPY pocket/ pocket/
COPY platform/bootstrap/ platform/bootstrap/
COPY platform/scripts/ platform/scripts/
COPY platform/device/ platform/device/
COPY platform/flasher/ platform/flasher/
ARG SOURCE_COMMIT
RUN test "${#SOURCE_COMMIT}" = 40
RUN python3 platform/bootstrap/build_internal_frontend.py \
    --mesa-package /build/mesa/package --arm-headers /opt/arm-sysroot/usr/include \
    --output /build/frontend
RUN python3 pocket/shell/native/reticulum/build.py /build/reticulum --arm \
    --bzip2-library /opt/arm-sysroot/usr/lib/arm-linux-gnueabi/libbz2.a
RUN git init -q pocket && git -C pocket add shell graphics \
    && python3 pocket/tools/stage_runtime.py --profile release \
       --frontend /build/frontend/frontend.json --native-reticulum /build/reticulum/build --source-commit "$SOURCE_COMMIT" \
       --output /build/runtime
RUN test -f /opt/arm-sysroot/lib/arm-linux-gnueabi/libusb-0.1.so.4.4.4 \
    && rm -f /opt/arm-sysroot/usr/lib/arm-linux-gnueabi/libusb.so \
    && cp /opt/arm-sysroot/lib/arm-linux-gnueabi/libusb-0.1.so.4.4.4 \
          /opt/arm-sysroot/usr/lib/arm-linux-gnueabi/libusb.so \
    && python3 platform/flasher/build.py --output /build/flasher \
    --target armel --cc arm-linux-gnueabi-gcc \
    --usb-flags '-I/opt/arm-sysroot/usr/include -L/opt/arm-sysroot/usr/lib/arm-linux-gnueabi -lusb'
RUN install -d /opt/n810-touch/touch-runtime \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-touch-calibrate.c -lm -o /opt/n810-touch/n810-touch-calibrate \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-fn-remap.c -o /opt/n810-touch/n810-fn-remap \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-backlightd.c -o /opt/n810-touch/n810-backlightd \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-wake.c -o /opt/n810-touch/n810-wake \
    && cp platform/scripts/n810-touch-fit.py /opt/n810-touch/ \
    && cp pocket/shell/touch.py pocket/shell/touch_evdev.py pocket/shell/touch_diagnostics.py \
          pocket/shell/pointer_events.py /opt/n810-touch/touch-runtime/
RUN if test "$AB_BOOT" = 1; then apt-get update && apt-get install -y --no-install-recommends cpio && mkdir -p /build/ram-tools && cd /build/ram-tools && apt-get download busybox-static:armel; fi
RUN if test "$AB_BOOT" = 1; then cp -a /build/kernel /build/recovery-kernel && python3 platform/kernel/build.py --work /build/recovery-kernel --resume --archive /build/kernel/linux.tar.xz --root-device "PARTUUID=${DISK_ID}-01" --jobs 4 && cp -a /build/kernel /build/ram-kernel && python3 platform/kernel/build.py --work /build/ram-kernel --resume --archive /build/kernel/linux.tar.xz --ram-installer --jobs 4; fi
CMD ["python3", "platform/bootstrap/build_internal_sources.py", "--help"]
