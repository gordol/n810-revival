#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Installed only in SD A/B slots. /data is already mounted and expanded.
set -eu
PATH=/usr/sbin:/usr/bin:/sbin:/bin
file=/data/.swapfile
active() { awk -v f="$file" '$1==f { found=1 } END { exit !found }' /proc/swaps; }
case "${1:-}" in
 start)
    test "$(findmnt -n -o FSTYPE --mountpoint /data)" = ext4
    test -f /data/SCHEMA.json
    exec 9>/run/lock/n810-sd-swap.lock
    flock 9
    active && exit 0
    if [ ! -e "$file" ] && [ ! -L "$file" ]; then
        umask 077
        tmp=$(mktemp /data/.swap-new.XXXXXX)
        trap 'rm -f "$tmp"' EXIT
        fallocate -l 536870912 "$tmp"
        mkswap "$tmp" >/dev/null
        ln "$tmp" "$file"
        rm "$tmp"
        trap - EXIT
    fi
    test ! -L "$file" && test -f "$file" || exit 1
    test "$(stat -c '%u:%a:%s' "$file")" = 0:600:536870912
    swapon -p 10 "$file"
    ;;
 stop) if active; then swapoff "$file"; fi ;;
 status) active ;;
 *) exit 2 ;;
esac
