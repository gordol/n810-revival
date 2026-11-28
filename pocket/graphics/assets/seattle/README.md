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
