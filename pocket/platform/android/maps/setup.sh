#!/bin/sh
# Install a local GIS runtime in Termux. The Pocket UI stays in Termux.
set -eu
if ! command -v pkg >/dev/null; then
    echo 'Run make mobile-map-deps in Termux.' >&2
    exit 1
fi
# Flight can decode several imagery tiles at once while boarding paints the cockpit.
# Keep those small image jobs in Termux when its Pillow package is available.
if ! python3 -c 'from PIL import Image, ImageDraw, ImageFont' 2>/dev/null; then
    pkg install -y python-pillow || echo 'Using the Debian image worker for flight graphics.' >&2
fi
command -v proot-distro >/dev/null || pkg install -y proot-distro
check_builder() {
    proot-distro login pocket-maps -- /usr/bin/python3 -c 'import osmium, numpy, ssl; assert ssl.create_default_context().get_ca_certs(); from PIL import Image; from shapely import make_valid, from_wkb'
}
if check_builder >/dev/null 2>&1; then
    exit 0
fi
echo 'Preparing the on-phone map and terrain builder…'
if ! proot-distro login pocket-maps -- /bin/true >/dev/null 2>&1; then
    proot-distro install debian:trixie --name pocket-maps
fi
proot-distro login pocket-maps -- /usr/bin/apt-get update
proot-distro login pocket-maps -- /usr/bin/apt-get install -y --no-install-recommends ca-certificates python3-pyosmium python3-shapely python3-pil python3-numpy
check_builder
echo 'Map builder ready. Open Offline Data in Pocket.'
