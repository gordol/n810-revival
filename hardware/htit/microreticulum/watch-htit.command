#!/bin/zsh
set -e
HTIT_PROJECT_DIR=${0:A:h}
exec "${HTIT_PYTHON:-python3}" "$HTIT_PROJECT_DIR/rnodelogs.py" "${HTIT_PORT:-/dev/cu.usbserial-0001}"
