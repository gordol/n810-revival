#!/bin/sh
# Attended two-minute comparison. Existing X clients and rail stay alive.
set -eu
export DISPLAY=:0 XAUTHORITY=/run/n810-gui/auth
base=/usr/local/lib/n810-gui
command -v xfwm4 >/dev/null
command -v dbus-run-session >/dev/null
command -v matchbox-window-manager >/dev/null
test -r "$XAUTHORITY"
test ! -e /run/n810-screen/quiet-charging
test ! -e /run/n810-screen/locked
pgrep -f '(^|/)matchbox-window-manager([[:space:]]|$)' >/dev/null
work=$(mktemp -d /tmp/n810-xfwm-test.XXXXXXXX)
echo "Comparison log: $work/memory.log"
snapshot() {
 date -u
 free -m
 awk '/^pswp(in|out)[[:space:]]/ { print; found=1 } END { if (!found) print "Swap event counters unavailable in this kernel." }' /proc/vmstat
 ps -eo comm,rss --sort=-rss | head -12
}
snapshot > "$work/memory.log"
child=
restore() {
 trap - EXIT HUP INT TERM
 if test -n "$child"; then kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
 # Do not start a WM after the GUI was explicitly ended during the test.
 if pgrep -x Xorg >/dev/null && ! pgrep -f '(^|/)matchbox-window-manager([[:space:]]|$)' >/dev/null; then
  nohup matchbox-window-manager -kbdconfig "$base/kbdconfig" -use_titlebar no -use_cursor yes -use_lowlight no </dev/null >"$work/matchbox.log" 2>&1 &
 fi
 sleep 2
 snapshot >> "$work/memory.log"
 echo "Current desktop restored. Log: $work/memory.log"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
# Matchbox does not relinquish the root redirect through xfwm4 --replace.
# Stop only this user's existing WM, never Xorg or application clients.
old_wm=$(pgrep -u "$(id -u)" -f '(^|/)matchbox-window-manager([[:space:]]|$)')
test "$(printf '%s\n' "$old_wm" | wc -l)" -eq 1
kill -TERM "$old_wm"
for attempt in 1 2 3 4 5; do
 if ! kill -0 "$old_wm" 2>/dev/null; then break; fi
 sleep 1
done
if kill -0 "$old_wm" 2>/dev/null; then echo 'Matchbox did not exit; aborting.' >&2; exit 1; fi
dbus-run-session -- sh -c '
 if test -x /usr/local/lib/n810-gui/xfwm-lite.sh; then /usr/local/lib/n810-gui/xfwm-lite.sh; fi
 xfwm4 --compositor=off --replace &
 wm=$!
 cleanup() { kill -TERM "$wm" 2>/dev/null || true; wait "$wm" 2>/dev/null || true; }
 trap cleanup EXIT
 trap "exit 143" HUP TERM
 sleep 120
' > "$work/xfwm.log" 2>&1 &
child=$!
for attempt in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 20; do
 if pgrep -x xfwm4 >/dev/null; then break; fi
 if ! kill -0 "$child" 2>/dev/null; then break; fi
 sleep 1
done
pgrep -x xfwm4 >/dev/null
snapshot >> "$work/memory.log"
wait "$child"
child=
