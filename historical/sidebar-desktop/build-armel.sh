#!/bin/sh
# Run in n810-builder. Use Bookworm X11 libraries, never host/armhf binaries.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
out=${1:?Usage: build-armel.sh NEW_OUTPUT_DIRECTORY}
test ! -e "$out" || { echo 'Output already exists.' >&2; exit 1; }
mkdir -p "$out/sysroot"
cat > "$out/packages.tsv" <<'PACKAGES'
ba22e4b4b6e8417c2435fd506604ac1ae5c48947d252ae34b0b927f77c648c07 pool/main/libx/libx11/libx11-dev_1.8.4-2+deb12u2_armel.deb
a09925794f0dc4f8b4cac87352e7926eb81c988e7ef6022dab12bff65e91ef87 pool/main/libx/libx11/libx11-6_1.8.4-2+deb12u2_armel.deb
7c7105e8ca084c84fa21ef7f0c22fd9e558513aeb1f6eac16e0300036b47d1a3 pool/main/libx/libxcb/libxcb1_1.15-1_armel.deb
21881ba5e6babe6b2d06f61a10e858816734a6f85b02ab7de9eaeb32245fccfb pool/main/libx/libxau/libxau6_1.0.9-1_armel.deb
c7fe718e9a513e4de93e729efc51cd92638a7fbbc3ef167161c2bb523ef15a07 pool/main/libx/libxdmcp/libxdmcp6_1.1.2-3_armel.deb
f048b2e3fa3377782bd8b1dc5f9bc4779f5eb1795fd99b52e66a6c981d8ea322 pool/main/libb/libbsd/libbsd0_0.11.7-2_armel.deb
d4ceb08997a44d75366618b8bca013e20dfbeb7d1c4d01984b6dc4cdedd33495 pool/main/libm/libmd/libmd0_1.0.4-2_armel.deb
PACKAGES
while read -r hash path; do
 file=$out/$(basename "$path")
 curl -fLsS "https://deb.debian.org/debian/$path" -o "$file"
 printf '%s  %s\n' "$hash" "$file" | sha256sum -c - >/dev/null
 dpkg-deb -x "$file" "$out/sysroot"
done < "$out/packages.tsv"
libs=$out/sysroot/usr/lib/arm-linux-gnueabi
arm-linux-gnueabi-gcc -std=c11 -Os -march=armv6 -mfloat-abi=soft -Wall -Wextra -Werror \
 -I"$out/sysroot/usr/include" -I/usr/include \
 "$base/n810-rail.c" -L"$libs" -Wl,-rpath-link,"$libs" -lX11 -o "$out/n810-rail"
arm-linux-gnueabi-strip "$out/n810-rail"
for name in n810-wake n810-fn-remap; do
 arm-linux-gnueabi-gcc -Os -static -march=armv6 -mfloat-abi=soft -Wall -Wextra -Werror \
  "$base/../../platform/scripts/$name.c" -o "$out/$name"
 arm-linux-gnueabi-strip "$out/$name"
done
cp "$base/../../platform/scripts/n810-screen" "$out/"
for name in xfce-session.sh xfce-terminal.sh xfwm-lite.sh test-xfwm.sh install-xfce.sh session.sh client.sh server.sh test-session.sh test-display.sh Xresources kbdconfig xorg.conf xorg-config.py n810-gui n810-gui-launch n810-gui.sudoers install.sh; do
 cp "$base/$name" "$out/"
done
cp -R "$base/xfce" "$out/"
(cd "$out" && sha256sum n810-rail n810-wake n810-fn-remap n810-screen xfce-session.sh xfce-terminal.sh xfwm-lite.sh test-xfwm.sh install-xfce.sh session.sh client.sh server.sh test-session.sh test-display.sh Xresources kbdconfig xorg.conf xorg-config.py n810-gui n810-gui-launch n810-gui.sudoers install.sh packages.tsv xfce/xfce4/xfconf/xfce-perchannel-xml/*.xml > SHA256SUMS)
