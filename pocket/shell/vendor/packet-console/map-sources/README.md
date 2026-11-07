# Map input downloads

Acquire public map inputs with `make maps-download` from `pocket/`. The current
workflow stores them in `pocket/data/downloads/`, records their source URL and
SHA-256, and uses `make maps` to build the local map catalogues.

Earlier converters remain here as source code in the parent directory and its
`tools/` directory. Their `--help` output describes explicit input paths. Downloaded
GIS exports and generated packs are excluded from the source repository.
