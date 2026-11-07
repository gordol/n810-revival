#!/bin/sh
# User-level XFWM drawing policy; do not replace unrelated preferences.
set -eu
if test -z "${DBUS_SESSION_BUS_ADDRESS:-}"; then
 exec dbus-run-session -- "$0"
fi
config=${XDG_CONFIG_HOME:-$HOME/.config}/xfce4/xfconf/xfce-perchannel-xml/xfwm4.xml
if test -f "$config"; then
 backup=$(mktemp "${config}.before-n810-lightweight.XXXXXXXX")
 cp -p "$config" "$backup"
fi
while read -r property value; do
 xfconf-query -c xfwm4 -p "/general/$property" --create --type bool --set "$value"
done <<'POLICY'
box_move true
box_resize true
use_compositing false
cycle_preview false
tile_on_move false
wrap_windows false
wrap_workspaces false
scroll_workspaces false
POLICY
# Allow the daemon's delayed configuration write before a temporary bus exits.
sleep 6
xfconf-query -c xfwm4 -l -v | grep -E '/general/(box_move|box_resize|use_compositing|cycle_preview|tile_on_move|wrap_windows|wrap_workspaces|scroll_workspaces)[[:space:]]'
