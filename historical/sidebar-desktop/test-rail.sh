#!/bin/sh
# All UI activity stays on an isolated virtual display.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
work=$(mktemp -d)
cleanup() {
 for pid in ${rail:-} ${wm:-} ${server:-}; do kill "$pid" 2>/dev/null || true; done
 rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM
mkdir "$work/screen"
export N810_TEST_SCREEN_DIR="$work/screen"
export N810_SCREEN_RUN_DIR="$work/screen"
cc -std=c11 -O2 -Wall -Wextra -Werror "$base/n810-rail.c" -lX11 -o "$work/rail"
cc -std=c11 -O2 -Wall -Wextra -Werror "$base/test-rail.c" -lX11 -lXtst -o "$work/test"
Xvfb -noreset -displayfd 3 -screen 0 800x480x16 -nolisten tcp 3>"$work/display" >"$work/x.log" 2>&1 &
server=$!
for attempt in 1 2 3 4 5; do test ! -s "$work/display" || break; sleep 1; done
test -s "$work/display"
DISPLAY=:$(cat "$work/display")
export DISPLAY
xmodmap -e 'keycode 192 = F14' -e 'keycode 193 = F15' -e 'keycode 194 = F16' -e 'keycode 195 = F17'
matchbox-window-manager -kbdconfig "$base/kbdconfig" -use_titlebar no >"$work/wm.log" 2>&1 &
wm=$!
sleep 1
"${N810_RAIL_TEST_BINARY:-$work/rail}" >"$work/rail.log" 2>&1 &
rail=$!
if ! "$work/test"; then cat "$work/rail.log" "$work/wm.log"; exit 1; fi
