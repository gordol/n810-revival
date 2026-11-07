#!/bin/sh
# Attended GUI blank/wake check; does not change idle or boot configuration.
set -eu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
test "$(id -u)" = 0 || { echo 'Run as root.' >&2; exit 1; }
test "$(cat /sys/class/tty/tty0/active)" = tty8 && test -f /run/n810-gui/auth || {
    echo 'The manual GUI session must be active on tty8.' >&2; exit 1;
}
test "$(n810-mode status)" = normal && test ! -e /run/n810-screen/locked || {
    echo 'Return to normal mode and unlock first.' >&2; exit 1;
}
restore() { timeout 10 n810-screen on; }
trap restore EXIT
trap 'exit 1' HUP INT TERM
timeout 10 n810-screen off
sleep 5
restore
trap - EXIT HUP INT TERM
echo 'Blank/wake commands completed; confirm the GUI returned on the tablet.'
