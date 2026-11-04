FROM debian:bookworm-slim
RUN apt-get update -qq && apt-get install -y --no-install-recommends cmake g++ g++-arm-linux-gnueabi git make python3 ca-certificates libbz2-dev
RUN dpkg --add-architecture armel && apt-get update -qq && cd /tmp && apt-get download libbz2-dev:armel libbz2-1.0:armel && for package in libbz2*.deb; do dpkg-deb -x "$package" /opt/n810-target; done && rm -rf /tmp/*.deb /var/lib/apt/lists/*
