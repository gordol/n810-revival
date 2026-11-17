#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Called before mounting the persistent data filesystem. Replay an interrupted
# boot's journal before resize2fs, which rejects needs_recovery even at full size.
set -eu
[ "$#" = 1 ] || { echo 'Usage: prepare-data DEVICE' >&2; exit 2; }
status=0
e2fsck -p "$1" || status=$?
case "$status" in
 0|1) ;;
 *) echo "Persistent data check requires attention (e2fsck status $status)." >&2; exit "$status";;
esac
resize2fs "$1"
