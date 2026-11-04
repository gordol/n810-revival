"""Small material recipes, in scene units; scene art remains producer-owned."""
from surface_renderer import Material

LANDSCAPE = {
    'fir': Material(5, "yv/\\';", .85, .12, .5, 'fiber', 3000, 8500),
    'cedar': Material(6, "v/\\y;'", .85, .14, .5, 'fiber', 3000, 8500),
    'fern': Material(2, 'v,;y', .8, .12, .45, 'fiber', 1800, 6500),
    'metal': Material(3, "_:/-'.", .65, .15, .4, 'stone', 1500, 7500),
}
ROOM = {
    'metal': Material(110, '#:/-_.', .8, .2, .5, 'masonry', 1500, 7000),
    'wood': Material(75, '|/\\:', .7, .15, .45, 'grain', 1500, 7000),
    'terrain': Material(130, '.,:_', .45, .09, .3, 'stone', 1800, 6500),
    'fern': Material(80, 'yv/\\;', .85, .15, .5, 'fiber', 1200, 6500),
}
