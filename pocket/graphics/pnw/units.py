"""US customary display units for Pacific Northwest outings."""
def mph(speed):
    return f'{abs(speed) / .44704:.0f} mph'

def feet(metres):
    return f'{metres / .3048:.0f} ft'

def road_distance(metres):
    return feet(metres) if metres < 160.9344 else f'{metres / 1609.344:.1f} mi'
