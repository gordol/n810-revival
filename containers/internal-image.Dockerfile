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
    arch-test e2fsprogs liblzo2-2 \
    && apt-get download libpython3.11-dev:armel libusb-dev:armel libusb-0.1-4:armel \
    && mkdir -p /opt/arm-sysroot \
    && for package in ./*_armel.deb; do dpkg-deb -x "$package" /opt/arm-sysroot; done \
    && rm -f ./*_armel.deb \
    && rm -rf /var/lib/apt/lists/*
RUN python3 -m venv /opt/mesa-tools && /opt/mesa-tools/bin/pip install \
    meson==1.5.2 Mako==1.3.5 packaging==24.1 PyYAML==6.0.2 setuptools==75.1.0
WORKDIR /src
COPY platform/kernel/ platform/kernel/
ARG DISK_ID
RUN test "${#DISK_ID}" = 8 \
    && python3 platform/kernel/build.py --work /build/kernel \
       --root-device "PARTUUID=${DISK_ID}-01" --jobs 4
COPY graphics/mbx/ graphics/mbx/
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
RUN git init -q pocket && git -C pocket add shell graphics \
    && python3 pocket/tools/stage_runtime.py --profile release \
       --frontend /build/frontend/frontend.json --source-commit "$SOURCE_COMMIT" \
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
CMD ["python3", "platform/bootstrap/build_internal_sources.py", "--help"]
