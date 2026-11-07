#!/bin/sh
# xinit client wrapper: keep runuser's separator out of xinit's argument parser.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
exec /usr/sbin/runuser -u nokia -- "$base/session.sh"
