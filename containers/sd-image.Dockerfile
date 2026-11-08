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
COPY platform/bootstrap/ platform/bootstrap/
RUN python3 platform/bootstrap/test_build_sd.py -q
CMD ["python3", "platform/bootstrap/build_sd.py", "--help"]
