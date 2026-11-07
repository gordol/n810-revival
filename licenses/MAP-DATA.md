# Map data attribution and reuse

Map data © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright).
OSM extracts and derived databases retain the [Open Database License 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
The original software grant adds no additional restriction to these databases. Preserve attribution and the ODbL
notice when sharing the data. Preparation tools are included in the repository. Users download extracts and
build local data; the generated metadata retains provider attribution.

Natural Earth raster and vector data are in the public domain under the
[provider's terms](https://www.naturalearthdata.com/about/terms-of-use/).

Elevation data comes from USGS 3DEP and NOAA ETOPO1. See the
[USGS product documentation](https://www.usgs.gov/3d-elevation-program/about-3dep-products-services)
and [NOAA's ETOPO1 reuse guidance](https://www.ngdc.noaa.gov/mgg/global/dem_faq.html).
NOAA permits reuse of its public-domain products and identifies ETOPO1 as
unsuitable for navigation. Retain the dataset identities, geographic extents,
acquisition requests and hashes supplied with the data.

The Forest Service road extract comes from the National Forest System Roads layer. Its [published metadata](https://data.fs.usda.gov/geodata/edw/edw_resources/meta/S_USA.RoadCore_FS.xml) states no access constraints and supplies accuracy, liability and legal-boundary disclaimers. Preserve those disclaimers and identify the U.S. Forest Service Enterprise Map Services Program.

The state-road extract corresponds to WSDOT's [State Route Lines (1:24K) Current](https://www.arcgis.com/home/item.html?id=38da3876aac643bdab274a0770e648a2), layer 4 in the Shared/LRSData service. The official catalog supplies planning-use, warranty and indemnification terms. These are retained in [the layer terms receipt](evidence/government-map-terms.json). They are WSDOT's own terms; the layer is not labeled ODbL or public domain. The receipt identifies the MapServer catalog endpoint corresponding to the retained FeatureServer query.

Provider guidance checked 7 November 2026. `data-review.json` covers the remaining authored non-map data assets. Privacy review and provider licensing
are separate checks. Each accompanying metadata file identifies the source used
for its particular prepared data.
