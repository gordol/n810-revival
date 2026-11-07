#!/bin/sh
# Run in Lima. Compile the real converter and libfdt, then execute under qemu-arm.
set -eu
ulimit -c 0
project=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
source=${1:?Supply the reconstructed maintained kernel source directory}
converter=${2:-$source/arch/arm/boot/compressed/atags_to_fdt.c}
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT HUP INT TERM
mkdir -p "$work/include/linux" "$work/include/asm"
cat > "$work/include/linux/libfdt_env.h" <<'EOF'
#include <libfdt_env.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t __be32;
#define cpu_to_be32 cpu_to_fdt32
#define cpu_to_be64 cpu_to_fdt64
EOF
printf '#include "%s/arch/arm/include/uapi/asm/setup.h"\n' "$source" > "$work/include/asm/setup.h"
arm-linux-gnueabi-gcc -O2 -static -Wall -Wextra \
 -I"$work/include" -I"$source/scripts/dtc/libfdt" \
 "$project/scripts/test-n810-boot-tags.c" \
 "$converter" \
 "$source/scripts/dtc/libfdt/fdt.c" "$source/scripts/dtc/libfdt/fdt_ro.c" \
 "$source/scripts/dtc/libfdt/fdt_rw.c" "$source/scripts/dtc/libfdt/fdt_wip.c" \
 "$source/scripts/dtc/libfdt/fdt_sw.c" "$source/scripts/dtc/libfdt/fdt_empty_tree.c" -o "$work/test-boot-tags"
qemu-arm -cpu arm1136 "$work/test-boot-tags"
