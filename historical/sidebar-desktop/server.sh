#!/bin/sh
# Root X server lifecycle; clients run as nokia. No boot-time service.
set -eu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
test "$(id -u)" = 0 || { echo 'Run the test through root openvt.' >&2; exit 1; }
case "$(/usr/local/sbin/n810-mode status)" in normal) ;; *) echo 'Return to normal mode first.' >&2; exit 1;; esac
test ! -e /run/n810-screen/locked || { echo 'Unlock first.' >&2; exit 1; }
policy=${N810_GUI_DISPLAY_POLICY:-1}
case "$policy" in 0|1) ;; *) echo 'Invalid display-policy flag.' >&2; exit 1;; esac
duration=${N810_GUI_TEST_SECONDS:-0}
case "$duration" in ''|*[!0-9]*) echo 'Invalid test duration.' >&2; exit 1;; esac
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
install -d -o root -g root -m 0755 /run/n810-gui
exec >/run/n810-gui/test.log 2>&1
run=$(mktemp -d /run/n810-x11-test.XXXXXX)
chmod 755 "$run"
child=
rm -f /run/n810-gui/stop-requested
cleanup() {
    trap - EXIT HUP INT TERM
    if test -n "$child"; then kill -TERM "$child" 2>/dev/null || true; wait "$child" 2>/dev/null || true; fi
    rm -rf "$run"
    rm -f /run/n810-gui/auth /run/n810-gui/xinit.pid /run/n810-gui/stop-requested /run/n810-gui/console-vt /run/n810-screen/x11-managed
    case "${N810_GUI_RETURN_VT:-}" in
        ''|*[!0-9]*) ;;
        *) if test "$N810_GUI_RETURN_VT" -ge 1 && test "$N810_GUI_RETURN_VT" -le 63; then chvt "$N810_GUI_RETURN_VT"; fi;;
    esac
    if test ! -e /run/n810-screen/locked && test ! -e /run/n810-screen/quiet-charging; then
        timeout 10 /usr/local/sbin/n810-screen on || true
    else
        timeout 10 /usr/local/sbin/n810-screen off || true
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM
python3 "$base/xorg-config.py" "$base/xorg.conf" /etc/n810-touch-calibration.json > "$run/xorg.conf"
cookie=$(mcookie)
auth=/run/n810-gui/auth
rm -f "$auth"
: > "$auth"
xauth -f "$auth" add :0 . "$cookie"
chown nokia:nokia "$auth"
chmod 600 "$auth"
XAUTHORITY=$auth
export XAUTHORITY
/usr/local/sbin/n810-screen on
# Opt in only after the attended GUI blank/wake check passes.
if test "$policy" = 1; then : > /run/n810-screen/x11-managed; fi
# Zero leaves the session active until the client exits.
set --
if test "$duration" != 0; then
 set -- timeout --signal=TERM --kill-after=5 "$duration"
fi
"$@" /usr/bin/xinit "$base/client.sh" -- \
 /usr/lib/xorg/Xorg :0 -config "$run/xorg.conf" -auth "$auth" \
 -nolisten tcp -keeptty vt8 -logfile /run/n810-gui/Xorg.log &
child=$!
printf '%s\n' "$child" > /run/n810-gui/xinit.pid
status=0
wait "$child" || status=$?
child=
if test -e /run/n810-gui/stop-requested; then status=0; fi
exit "$status"
