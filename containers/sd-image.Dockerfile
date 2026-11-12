# syntax=docker/dockerfile:1
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
FROM python:3.13-bookworm@sha256:cc55e4ded9c95f6ce2133b3d096db43f214d280c2a8af65d83e246c8fa7d168c
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential flex bison bc libssl-dev libelf-dev kmod curl ca-certificates \
    xz-utils patch gcc-arm-linux-gnueabihf binutils-arm-linux-gnueabihf \
    mmdebstrap qemu-user-static binfmt-support arch-test e2fsprogs \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY platform/kernel/ platform/kernel/
ARG JOBS=4
RUN python3 platform/kernel/build.py --work /build/kernel --root-device /dev/mmcblk0p1 --jobs "$JOBS"
RUN apt-get update && apt-get install -y --no-install-recommends gcc-arm-linux-gnueabi libc6-dev-armel-cross liblzo2-2 && rm -rf /var/lib/apt/lists/*
COPY platform/scripts/n810-touch-calibrate.c platform/scripts/n810-touch-confirm.h platform/scripts/n810-touch-fit.py platform/scripts/n810-fn-remap.c platform/scripts/n810-backlightd.c /opt/n810-touch/
RUN arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror /opt/n810-touch/n810-touch-calibrate.c -lm -o /opt/n810-touch/n810-touch-calibrate
RUN arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror /opt/n810-touch/n810-fn-remap.c -o /opt/n810-touch/n810-fn-remap
RUN arm-linux-gnueabi-gcc -Os -static -march=armv6 -marm -mfloat-abi=soft -Wall -Wextra -Werror /opt/n810-touch/n810-backlightd.c -o /opt/n810-touch/n810-backlightd
COPY pocket/shell/touch.py pocket/shell/touch_evdev.py pocket/shell/touch_diagnostics.py pocket/shell/pointer_events.py /opt/n810-touch/touch-runtime/
COPY platform/scripts/n810-jffs2-extract.py platform/scripts/n810-bluetooth-address platform/scripts/n810-wifi-service platform/scripts/n810-keyboard platform/scripts/n810-powerd platform/scripts/n810-ledd platform/scripts/n810-powerctl platform/scripts/n810-ledctl platform/scripts/n810-display-keys.py platform/scripts/n810-power-overlay platform/scripts/n810-power platform/scripts/n810-screen /src/platform/scripts/
COPY platform/device/n810-bluetooth-address.service platform/device/10-n810-address.conf platform/device/n810-wifi.service platform/device/n810-zram.init platform/device/n810-zram.defaults platform/device/n810-zram.service platform/device/n810-buttons.map platform/device/n810-fn-remap.service platform/device/n810-keyboard.service platform/device/n810-backlight.conf platform/device/n810-led.conf platform/device/n810-backlightd.service platform/device/n810-powerd.service platform/device/n810-ledd.service platform/device/n810-display-keys.service platform/device/n810-display.conf /src/platform/device/
COPY platform/bootstrap/ platform/bootstrap/
RUN PYTHONPATH=/opt/n810-touch/touch-runtime python3 -m unittest discover -s platform/bootstrap -p "test_*.py" -v
CMD ["python3", "platform/bootstrap/build_sd.py", "--help"]
