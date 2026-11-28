Places extracted from OpenStreetMap on 2026-11-27. © OpenStreetMap contributors, licensed under the [Open Database License](https://www.openstreetmap.org/copyright). Coordinates are WGS84. Nodes are POI markers. Way points are footprint bounding-box centers. Resolve each source at https://www.openstreetmap.org/{osm_type}/{osm_id}. A POI identifies a business or landmark, not the corners of its counter or its interior layout.

The same attribution and ODbL license apply to delivery.csv and buildings.json. Delivery coordinates follow OSM ways 8071901, 1382688147 and 13526138 in their mapped direction. The building extract covers Seattle Center, downtown and a small part of Ballard. Each record contains its source way ID as key, original height or floor-count tag and value, exterior coordinates, and triangulated roof indices. The extractor skips multipolygons and incomplete ways. Regenerate with pocket/tools/seattle_buildings.py against OSM API 0.6 map exports for bounding boxes (-122.354,47.6158,-122.3420,47.6240), (-122.343,47.600,-122.329,47.614) and (-122.395,47.6665,-122.3900,47.6698).

The seasonal flower table represents the Main Arcade farm tables described
in the Market's [flower farmer history](https://www.pikeplacemarket.org/history-behind-our-hmong-flower-farmers/).
The honey display represents [Sunny Honey Company](https://www.pikeplacemarket.org/vendor/sunny-honey-company/)
inside the main entrance. Their in-game bearings lead to reconstructed displays.

The three public DownUnder shopping levels have separate, walkable scene reconstructions.
The Market identifies [Golden Age Collectables on level 4](https://www.pikeplacemarket.org/vendor/golden-age-collectables/),
[Ruby’s opposite Sound View Café on level 5](https://www.pikeplacemarket.org/vendor/rubys-seattle-gift-gallery/),
and [Gradient Art Gallery on level 3](https://www.pikeplacemarket.org/12-gifts-for-kids-and-teens-at-pike-place-market/).
The numbered levels follow the Market directory. Room dimensions, shop fixtures,
corridor positions, stair connections, and the district map are authored for gameplay.
The [Gum Wall](https://www.pikeplacemarket.org/vendor/the-gum-wall/) scene uses brick and gum on both alley walls.
The waterfront scene uses the steps, benches, and railings visible in the
[Overlook Walk photo reference](https://waterfrontparkseattle.org/overlook-walk/).
Lumen Field and T-Mobile Park are exterior skyline models.
The bakery and coffee counters reference [Piroshky Piroshky](https://www.pikeplacemarket.org/vendor/piroshky-piroshky/)
and the [1912 Pike Place Starbucks storefront](https://www.seattle.gov/documents/departments/neighborhoods/historicpreservation/historicdistricts/pikeplacemarket/meetingdocuments/2024/mhc082824starbuckspp.pdf).

The Belltown and waterfront infill uses OSM API map extracts for
(-122.354,47.6135,-122.34,47.617) and (-122.350,47.600,-122.339,47.614).
The same ODbL attribution applies to streets.json. The keys are OSM way IDs.
The street extractor accepts the Seattle Center, downtown, infill and waterfront
exports with `pocket/tools/seattle_buildings.py --streets`. It retains named
surface streets in the walking district and flags mapped crossing nodes.
Widths, paint, terminal approaches and sign placement are game scenery.
The accelerated ferry rides OSM way 332476322 in both directions. Runway
thresholds and widths come from the [OurAirports public-domain runway dataset](https://ourairports.com/data/).

The same ODbL credit applies to tacoma-streets.json. It contains named drivable ways from the OSM API 0.6 map export for (-122.447,47.249,-122.436,47.257), including the complete returned ways. The same map export supplied 99 height- or floor-tagged Tacoma building footprints in buildings.json using the existing building extractor. Dock Street way 687454686 supplies the illustrated Tacoma delivery route.

The southbound Seattle–Tacoma driving corridor uses OpenStreetMap geometry
routed by the FOSSGIS OSRM car service on 2026-11-28. The extract keeps the
street names and full WGS84 centerline from First Avenue to Dock Street via
I-5. Widths, painted lane lines, rental stand and patrol encounter are game
reconstructions. Bridge and interchange deck heights are not surveyed.
[Route source](https://routing.openstreetmap.de/routed-car/route/v1/driving/-122.3400015,47.6088449;-122.4347,47.2459?geometries=geojson&overview=full&steps=true)

The SoDo and Beacon Hill freeway scenery uses two additional OSM API extracts
(-122.336,47.584,-122.314,47.604 and -122.327,47.563,-122.312,47.585).
They add 320 height- or level-tagged buildings, 1,280 mapped trees, and nine
woodland outlines. The same extracts supply 19 tagged bridge ways crossing
the southbound route, including Yesler Way, South Holgate Street and the
West Seattle Bridge. Deck heights, parapets and supports are reconstructed. Tree heights, crowns and tree positions inside woods are generated.

The green siren on the modeled takeaway cups uses the Starbucks mark from
[Simple Icons 13.0.0](https://cdn.jsdelivr.net/npm/simple-icons@13.0.0/icons/starbucks.svg).
Starbucks owns the mark. Counter layouts and baked goods are visual reconstructions.
[Piroshky Piroshky at Pike Place Market](https://www.pikeplacemarket.org/vendor/piroshky-piroshky/)

The Main Arcade includes reconstructed displays for
[Sosio’s Produce](https://www.pikeplacemarket.org/vendor/sosios-produce/),
[Pure Food Fish](https://www.pikeplacemarket.org/vendor/pure-food-fish/) and
[MarketSpice](https://www.pikeplacemarket.org/vendor/market-spice/).
Sosio’s directory entry places it north of Lowell’s and next to Chukar Cherries.
The game compresses the walk between bays. The display stock, counter dimensions
and sign positions are visual estimates based on market photographs.

The arcade surface texture packs four grayscale channels from Poly Haven's
CC0 photographs, resized to 512 pixels per side and contrast-normalized.
In RGBA order the sources are [Oak Wood Planks](https://polyhaven.com/a/oak_wood_planks),
[Terracotta Floor Tiles](https://polyhaven.com/a/terracotta_floor_tiles),
[Red Brick Pavers](https://polyhaven.com/a/red_brick_pavers) and
[Plastered Wall](https://polyhaven.com/a/plastered_wall). The GPU repeats
each channel independently and tints it with the scene material color.

The freeway.json extract contains OpenStreetMap motorway and ramp geometry,
lane counts, posted speed limits and numbered junctions along the Seattle–Tacoma
drive. The northbound route follows OSRM routing over OpenStreetMap. Road data
© OpenStreetMap contributors, distributed under the Open Database License 1.0.

The sports coupe is an exterior-only, simplified adaptation of Eric Chadwick’s
[Car Concept](https://github.com/KhronosGroup/glTF-Sample-Assets/tree/main/Models/CarConcept),
© 2024 Darmstadt Graphics Group GmbH, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). The original model was
created by Unity Fan. The adaptation omits the original logo textures, clusters
vertices, and replaces glTF materials with runtime paint, glass and lamp colors.
Run pocket/tools/bake_coupe.py with the upstream CarConcept.glb and an output
path. Source SHA-256 is c272098089d78c5cd9fd9f24ff50ee8acf8d932c55f2d55fc10adb6c8998966b.

Passenger railway alignments and stop sequences in rail.json are extracts from
the [Sound Transit GTFS feed](https://www.soundtransit.org/GTFS-rail/40_gtfs.zip)
and the [Amtrak GTFS feed](https://content.amtrak.com/content/gtfs/GTFS.zip).
Rides use simulated running and dwell times. Platform designs, terminal cranes,
ships and landmark architecture are reconstructions. Sea-Tac runway thresholds
and widths come from the public-domain [OurAirports runway data](https://ourairports.com/data/).

park-trees.json contains 469 Seattle Parks and Recreation inventory positions
in the downtown/Seattle Center area. Source is the City of Seattle's
[SPR Tree View](https://data.seattle.gov/dataset/SPR-Tree-View/c7dn-wzzd),
queried in WGS84 within (-122.36, 47.59, -122.326, 47.625).
Tree crowns and ground cover are procedurally reconstructed.
