#!/bin/sh
# Keep the receive owner alive so Pocket can observe Bluetooth even when RX is stopped.
set -eu

if [ "$(/usr/local/sbin/n810-mode status)" != normal ]; then
    exit 0
fi

exec /usr/bin/flock -n /run/lock/n810-aprs-feed-supervisor.lock /bin/sh -c '
    while :; do
        /sbin/runuser -u nokia -- /usr/bin/python3 -u /home/nokia/n810-aprs-feed.py >/dev/null 2>&1
        /usr/bin/logger -t n810-aprs-feed "receive owner exited; restarting"
        sleep 3
    done
'
