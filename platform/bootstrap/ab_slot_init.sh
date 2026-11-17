#!/bin/sh
export PATH=/usr/sbin:/usr/bin:/sbin:/bin
fail() { echo "A/B startup failed: $*"; [ "$MODE" = --prepare ] && exit 1; while :; do /bin/sh; done; }
MODE=${1:-}
if [ "$MODE" = --enter ]; then
 umount -R /old-root || fail 'release internal root'
 exec /sbin/init
fi
mountpoint -q /proc || mount -t proc proc /proc || fail proc
mountpoint -q /sys || mount -t sysfs sysfs /sys || fail sys
mountpoint -q /dev || mount -t devtmpfs devtmpfs /dev || fail dev
mountpoint -q /run || mount -t tmpfs -o mode=755,size=16m tmpfs /run || fail run
mount -t tmpfs -o mode=1777,size=16m tmpfs /tmp || fail tmp
exec </dev/console >/dev/console 2>&1
DATA=
[ "$MODE" != --prepare ] || DATA=${2:-}
case "$DATA" in ""|PARTUUID=????????-04) :;; *) fail "invalid data identity";; esac
if [ "$MODE" != --prepare ]; then
 for arg in $(cat /proc/cmdline); do case "$arg" in n810.data=PARTUUID=????????-04) DATA=${arg#n810.data=};; esac; done
fi
[ -n "$DATA" ] || fail 'missing data identity'
for n in 1 2 3 4 5 6 7 8 9 10; do
 DEV=$(blkid -t "$DATA" -o device)
 [ -b "$DEV" ] && break
 sleep 1
done
[ -b "$DEV" ] || fail 'data partition absent or ambiguous'
/usr/lib/n810-ab/prepare-data "$DEV" || fail 'data filesystem recovery or expansion'
mount -t ext4 -o rw,noatime "$DEV" /data || fail 'data mount'
test -s /data/etc/ssh/ssh_host_ed25519_key || ssh-keygen -q -t ed25519 -N '' -f /data/etc/ssh/ssh_host_ed25519_key || fail 'SSH identity'
test "$(python3 -c 'import json; print(json.load(open("/data/SCHEMA.json"))["version"])')" = 1 || fail 'data schema'
mkdir -p /data/etc-overlay/upper /data/etc-overlay/work || fail 'configuration storage'
mount -t overlay overlay -o lowerdir=/usr/lib/n810-ab/etc,upperdir=/data/etc-overlay/upper,workdir=/data/etc-overlay/work /etc || fail 'persistent configuration overlay'
mount -t tmpfs -o mode=755,size=32m tmpfs /var || fail var
cp -a /usr/lib/n810-ab/var/. /var/ || fail 'var defaults'
while IFS= read -r path; do
 case "$path" in etc/*) :;;
 home|root) mount --bind "/data/$path" "/$path" || fail "$path";;
 *) rm -rf "/$path"; ln -s "/data/$path" "/$path" || fail "$path";; esac
done < /etc/n810-ab/persistent-paths
[ "$MODE" != --prepare ] || exit 0
exec /sbin/init
