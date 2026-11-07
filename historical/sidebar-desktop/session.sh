#!/bin/sh
# Manual session only. No display manager or boot-time service.
set -eu
PATH=/usr/local/bin:/usr/bin:/bin
export PATH
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
xrdb -merge "$base/Xresources"
xset s off -dpms
xmodmap -e 'keycode 191 = F13' -e 'keycode 192 = F14' -e 'keycode 193 = F15' -e 'keycode 194 = F16' -e 'keycode 195 = F17'
xset -r 192
xset -r 193
desktop=$(n810-profile get desktop)
case "$desktop" in
 xfce)
  # D-Bus activated xfconfd inherits the bus daemon's environment.
  export XDG_CONFIG_DIRS=/usr/local/share/n810/xfce:/etc/xdg
  export XDG_CURRENT_DESKTOP=XFCE DESKTOP_SESSION=n810-xfce
  exec dbus-run-session -- "$base/xfce-session.sh";;
 n810|'') :;;
 *) echo 'Invalid desktop preference.' >&2; exit 1;;
esac
matchbox-window-manager -kbdconfig "$base/kbdconfig" -use_titlebar no -use_cursor yes -use_lowlight no &
wm=$!
"$base/n810-rail" &
rail=$!
cleanup() { kill "$rail" "$wm" 2>/dev/null || true; }
trap cleanup EXIT HUP INT TERM
n810-pocket start
tmux -L "${N810_TMUX_SOCKET:-n810}" set-option -t "${N810_POCKET_SESSION:-pocket}" mouse on
xterm -name n810-terminal -title Terminal -fa monospace -fs 10 -b 0 -bg '#131b20' -fg '#dae5ec' -e n810-pocket launch &
# The rail owns the session; closing a terminal does not close other apps.
wait "$rail"
