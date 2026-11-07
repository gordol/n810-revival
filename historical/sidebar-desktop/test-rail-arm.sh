#!/bin/sh
# Exercise a built ARM rail on the isolated Xvfb display.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
bundle=${1:?Usage: test-rail-arm.sh BUILT_BUNDLE}
bundle=$(CDPATH= cd -- "$bundle" && pwd)
test -x "$bundle/n810-rail"
(cd "$bundle" && sha256sum -c SHA256SUMS >/dev/null)
command -v qemu-arm >/dev/null
runtime=${N810_ARM_RUNTIME:-/usr/arm-linux-gnueabi}
test -f "$runtime/lib/ld-linux.so.3"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
# Keep paths in environment variables so spaces cannot become shell syntax.
export N810_ARM_BUNDLE="$bundle" N810_ARM_RUNTIME="$runtime"
cat > "$work/rail" <<'WRAPPER'
#!/bin/sh
exec qemu-arm -L "$N810_ARM_RUNTIME" \
 -E "LD_LIBRARY_PATH=$N810_ARM_BUNDLE/sysroot/usr/lib/arm-linux-gnueabi" \
 "$N810_ARM_BUNDLE/n810-rail"
WRAPPER
chmod 755 "$work/rail"
N810_RAIL_TEST_BINARY="$work/rail" sh "$base/test-rail.sh"
