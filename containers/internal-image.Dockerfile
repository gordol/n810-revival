# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
# Build all five inputs for the internal MMC kit from one tracked source tree.
FROM python:3.13-bookworm@sha256:cc55e4ded9c95f6ce2133b3d096db43f214d280c2a8af65d83e246c8fa7d168c
RUN dpkg --add-architecture armel && apt-get update && apt-get install -y --no-install-recommends \
    build-essential git flex bison bc libssl-dev libelf-dev kmod curl ca-certificates \
    xz-utils patch gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    gcc-arm-linux-gnueabi g++-arm-linux-gnueabi binutils-arm-linux-gnueabi \
    ninja-build pkg-config dpkg-dev mmdebstrap qemu-user-static binfmt-support \
    arch-test e2fsprogs liblzo2-2 libusb-1.0-0-dev:armel \
    && apt-get download libpython3.11-dev:armel \
    && mkdir -p /opt/arm-headers \
    && dpkg-deb -x libpython3.11-dev_*_armel.deb /opt/arm-headers \
    && rm -f libpython3.11-dev_*_armel.deb \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/mesa-tools && /opt/mesa-tools/bin/pip install \
    meson==1.5.2 Mako==1.3.5 packaging==24.1 PyYAML==6.0.2 setuptools==75.1.0
WORKDIR /src
COPY . .
ARG DISK_ID
ARG SOURCE_COMMIT
RUN test "${#DISK_ID}" = 8 && test "${#SOURCE_COMMIT}" = 40 \
    && python3 platform/kernel/build.py --work /build/kernel \
       --root-device "PARTUUID=${DISK_ID}-01" --jobs 4
RUN python3 graphics/mbx/build.py module --work /build/module \
    --kernel-source /build/kernel/linux-5.15.224 --kernel-build /build/kernel/build
RUN --mount=type=cache,id=n810-internal-mesa-inputs,target=/cache/mesa-inputs,sharing=locked \
    PATH=/opt/mesa-tools/bin:$PATH python3 graphics/mbx/build.py mesa \
    --work /build/mesa --jobs 4 --osmesa --download-cache /cache/mesa-inputs
RUN python3 platform/bootstrap/build_internal_frontend.py \
    --mesa-package /build/mesa/package --arm-headers /opt/arm-headers/usr/include \
    --output /build/frontend
RUN git init -q pocket && git -C pocket add shell graphics \
    && python3 pocket/tools/stage_runtime.py --profile release \
       --frontend /build/frontend/frontend.json --source-commit "$SOURCE_COMMIT" \
       --output /build/runtime
RUN python3 platform/flasher/build.py --output /build/flasher \
    --target armel --cc arm-linux-gnueabi-gcc \
    --usb-flags '-I/usr/include/libusb-1.0 -lusb-1.0'
RUN install -d /opt/n810-touch/touch-runtime \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-touch-calibrate.c -lm -o /opt/n810-touch/n810-touch-calibrate \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-fn-remap.c -o /opt/n810-touch/n810-fn-remap \
    && arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror \
       platform/scripts/n810-backlightd.c -o /opt/n810-touch/n810-backlightd \
    && cp platform/scripts/n810-touch-fit.py /opt/n810-touch/ \
    && cp pocket/shell/touch.py pocket/shell/touch_evdev.py pocket/shell/touch_diagnostics.py \
          pocket/shell/pointer_events.py /opt/n810-touch/touch-runtime/
CMD ["python3", "platform/bootstrap/build_internal_sources.py", "--help"]
