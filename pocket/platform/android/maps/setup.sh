#!/bin/sh
# Install a local GIS runtime in Termux. The Pocket UI stays in Termux.
set -eu
if ! command -v pkg >/dev/null; then
    echo 'Run make mobile-map-deps in Termux.' >&2
    exit 1
fi
command -v proot-distro >/dev/null || pkg install -y proot-distro
if ! proot-distro login pocket-maps -- /bin/true >/dev/null 2>&1; then
    proot-distro install debian:trixie --name pocket-maps
fi
proot-distro login pocket-maps -- /usr/bin/apt-get update
proot-distro login pocket-maps -- /usr/bin/apt-get install -y --no-install-recommends ca-certificates python3-pyosmium python3-shapely python3-pil python3-numpy
proot-distro login pocket-maps -- /usr/bin/python3 -c 'import osmium, numpy; from PIL import Image; from shapely import make_valid, from_wkb'
echo 'Map builder ready. Open Offline Data in Pocket.'
