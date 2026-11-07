#!/bin/sh
# Optional Bookworm comparison packages; keep the accepted SysV boot policy.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
test "$(id -u)" = 0
test "$(dpkg-query -W -f='${Status}' sysvinit-core)" = 'install ok installed'
export DEBIAN_FRONTEND=noninteractive
exec apt-get -y --no-install-recommends --no-remove install \
 dbus-x11 xfce4-session xfwm4 xfce4-panel xfdesktop4 thunar sysvinit-core+
