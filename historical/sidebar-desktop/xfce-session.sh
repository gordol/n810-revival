#!/bin/sh
# Stock XFCE session with the shared N810 input policy and compositing off.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export XDG_CONFIG_DIRS=/usr/local/share/n810/xfce:/etc/xdg
export XDG_CURRENT_DESKTOP=XFCE DESKTOP_SESSION=n810-xfce
"$base/xfwm-lite.sh"
# Preserve the internal remapper and use native XFWM actions for hardware keys.
xfconf-query -c keyboard-layout -p /Default/XkbDisable --create --type bool --set true
for key in F11 F15; do
 xfconf-query -c xfce4-keyboard-shortcuts -p "/xfwm4/custom/$key" --create --type string --set fullscreen_key
done
for key in F14 F16; do
 xfconf-query -c xfce4-keyboard-shortcuts -p "/xfwm4/custom/$key" --create --type string --set cycle_windows_key
done
xfconf-query -c xfce4-keyboard-shortcuts -p /xfwm4/custom/F17 --create --type string --set cycle_reverse_windows_key
xfconf-query -c xfce4-keyboard-shortcuts -p /commands/custom/F13 --create --type string --set xfce4-popup-applicationsmenu
exec xfce4-session
