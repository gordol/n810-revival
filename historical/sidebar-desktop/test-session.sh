#!/bin/sh
# Attended display test; normal launcher has no timeout.
set -eu
base=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
N810_GUI_TEST_SECONDS=${N810_GUI_TEST_SECONDS:-90}
export N810_GUI_TEST_SECONDS
exec "$base/server.sh"
