#!/bin/sh
# Session-start terminal; key ownership remains with the N810 input services.
set -eu
xmodmap -e 'keycode 191 = F13' -e 'keycode 192 = F14' -e 'keycode 193 = F15' -e 'keycode 194 = F16' -e 'keycode 195 = F17'
xset -r 192
xset -r 193
n810-pocket start
tmux -L "${N810_TMUX_SOCKET:-n810}" set-option -t "${N810_POCKET_SESSION:-pocket}" mouse on
exec xterm -name n810-terminal -title Terminal -fa monospace -fs 10 -b 0 -bg '#131b20' -fg '#dae5ec' -e n810-pocket launch
