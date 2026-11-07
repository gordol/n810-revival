#!/bin/sh
# Install the manual GUI only. No display manager or boot service.
set -eu
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
test "$(id -u)" = 0 || { echo 'Run as root.' >&2; exit 1; }
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
(cd "$base" && sha256sum -c SHA256SUMS)
for cmd in xinit xterm xset xrdb xmodmap xauth mcookie python3 flock openvt setsid chvt runuser matchbox-window-manager; do
    command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }
done
if pgrep -x Xorg >/dev/null; then echo 'Stop the GUI before installing.' >&2; exit 1; fi
test -x /usr/lib/xorg/Xorg
test -x /etc/init.d/n810-console-ux && test -x /etc/init.d/n810-wake
"$base/n810-fn-remap" --self-test
"$base/n810-wake" --version | grep -Fx 'n810-wake 3' >/dev/null
test -f /etc/n810-touch-calibration.json
for command in n810-profile n810-desktop n810-dialog; do
 command -v "$command" >/dev/null || { echo 'Update pocket userland before installing this GUI bundle.' >&2; exit 1; }
done
n810-profile get desktop >/dev/null
getent passwd nokia >/dev/null
getent group n810-power >/dev/null
visudo -cf "$base/n810-gui.sudoers"
backup=$(mktemp -d /root/n810-gui-before-XXXXXXXX)
if test -d /usr/local/lib/n810-gui; then cp -a /usr/local/lib/n810-gui "$backup/"; fi
for file in /usr/local/bin/n810-gui /usr/local/sbin/n810-gui-launch /etc/sudoers.d/n810-gui /usr/local/sbin/n810-wake /usr/local/sbin/n810-fn-remap /usr/local/sbin/n810-screen; do
    if test -f "$file"; then
        mkdir -p "$backup$(dirname "$file")"
        cp -p "$file" "$backup$file"
    fi
done
restart_services() {
    /etc/init.d/n810-console-ux start
    /etc/init.d/n810-wake start
}
trap restart_services EXIT
/etc/init.d/n810-wake stop
/etc/init.d/n810-console-ux stop
for name in n810-wake n810-fn-remap n810-screen; do
    install -o root -g root -m 0755 "$base/$name" "/usr/local/sbin/$name"
done
restart_services
trap - EXIT
install -d -o root -g root -m 0755 /usr/local/lib/n810-gui
for name in n810-rail xfce-session.sh xfce-terminal.sh xfwm-lite.sh test-xfwm.sh install-xfce.sh session.sh client.sh server.sh; do
    install -o root -g root -m 0755 "$base/$name" "/usr/local/lib/n810-gui/$name"
done
for name in Xresources kbdconfig xorg.conf xorg-config.py; do
    install -o root -g root -m 0644 "$base/$name" "/usr/local/lib/n810-gui/$name"
done
install -d /usr/local/share/n810/xfce
# Remove only our withdrawn first-trial session template; preserve other files.
old=/usr/local/share/n810/xfce/xfce4/xfconf/xfce-perchannel-xml/xfce4-session.xml
if test -f "$old" && test "$(sha256sum "$old" | cut -d ' ' -f 1)" = d6e996b1999710e27e7d72e98355de65a8c0fa472b8722ddd125c1895e005800; then
 cp -p "$old" "$backup/xfce4-session-first-trial.xml"
 rm "$old"
fi
cp -R "$base/xfce/." /usr/local/share/n810/xfce/
install -o root -g root -m 0755 "$base/n810-gui" /usr/local/bin/n810-gui
install -o root -g root -m 0755 "$base/n810-gui-launch" /usr/local/sbin/n810-gui-launch
install -o root -g root -m 0440 "$base/n810-gui.sudoers" /etc/sudoers.d/n810-gui
visudo -c
printf 'Manual GUI installed. Previous files: %s\n' "$backup"
