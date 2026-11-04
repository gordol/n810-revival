"""Offline APRS symbol labels and authored terminal approximations.

Factual identifiers follow WB4APR's master symbol list (25 November 2015).
No icon artwork or third-party implementation is included. Glyphs are our
single-cell text approximations, not the standardized APRS pictograms.
"""
SOURCE = 'https://www.aprs.org/symbols/symbolsX.txt'

# Each entry is code, glyph, readable name. Unlisted/reserved codes stay unknown.
PRIMARY = {
    '!': ('P', 'Police'), '#': ('◆', 'Digipeater'), '$': ('T', 'Telephone'),
    '%': ('D', 'DX cluster'), '&': ('G', 'HF gateway'), "'": ('A', 'Small aircraft'),
    '(': ('S', 'Mobile satellite station'), ')': ('W', 'Wheelchair'),
    '*': ('S', 'Snowmobile'), '+': ('+', 'Red Cross'), ',': ('B', 'Boy Scouts'),
    '-': ('⌂', 'Home'), '.': ('×', 'X marker'), '/': ('●', 'Point'),
    ':': ('F', 'Fire'), ';': ('C', 'Campground'), '<': ('M', 'Motorcycle'),
    '=': ('R', 'Train'), '>': ('C', 'Car'), '?': ('S', 'File server'),
    '@': ('H', 'Hurricane forecast'), 'A': ('+', 'Aid station'), 'B': ('B', 'BBS'),
    'C': ('C', 'Canoe'), 'E': ('E', 'Event'), 'F': ('T', 'Tractor'),
    'G': ('■', 'Grid square'), 'H': ('H', 'Hotel'), 'I': ('N', 'On-air TCP/IP station'),
    'K': ('K', 'School'), 'L': ('U', 'Logged-on user'), 'M': ('M', 'MacAPRS'),
    'N': ('N', 'NTS station'), 'O': ('O', 'Balloon'), 'P': ('P', 'Police'),
    'R': ('R', 'Recreational vehicle'), 'S': ('S', 'Space shuttle'), 'T': ('T', 'SSTV'),
    'U': ('B', 'Bus'), 'V': ('T', 'ATV'), 'W': ('W', 'National Weather Service'),
    'X': ('H', 'Helicopter'), 'Y': ('Y', 'Sailboat'), 'Z': ('W', 'WinAPRS'),
    '[': ('P', 'Person'), '\\': ('▲', 'Direction-finding station'),
    ']': ('M', 'Post office'), '^': ('A', 'Large aircraft'), '_': ('W', 'Weather station'),
    '`': ('D', 'Dish antenna'), 'a': ('+', 'Ambulance'), 'b': ('B', 'Bicycle'),
    'c': ('C', 'Incident command'), 'd': ('F', 'Fire department'), 'e': ('H', 'Horse'),
    'f': ('F', 'Fire engine'), 'g': ('G', 'Glider'), 'h': ('H', 'Hospital'),
    'i': ('I', 'Island'), 'j': ('J', 'Jeep'), 'k': ('T', 'Truck'), 'l': ('L', 'Laptop'),
    'm': ('R', 'Mic-E repeater'), 'n': ('N', 'Node'), 'o': ('E', 'Emergency operations'),
    'p': ('D', 'Dog'), 'q': ('■', 'Grid square'), 'r': ('R', 'Repeater'),
    's': ('S', 'Powerboat'), 't': ('T', 'Truck stop'), 'u': ('T', 'Heavy truck'),
    'v': ('V', 'Van'), 'w': ('W', 'Water station'), 'x': ('X', 'xAPRS'),
    'y': ('Y', 'Yagi antenna'), '|': ('T', 'TNC stream switch'), '~': ('T', 'TNC stream switch'),
}
ALTERNATE = {
    '!': ('!', 'Emergency'), '#': ('◆', 'Digipeater'), '$': ('B', 'Bank'),
    '%': ('P', 'Power plant'), '&': ('G', 'Gateway'), "'": ('!', 'Incident site'),
    '(': ('C', 'Cloud'), ')': ('F', 'Firenet observation'), '+': ('+', 'Church'),
    ',': ('G', 'Girl Scouts'), '-': ('⌂', 'Home'), '.': ('?', 'Ambiguous position'),
    '/': ('●', 'Destination waypoint'), '0': ('G', 'IRLP/Echolink/WIRES link'),
    '8': ('N', 'Network node'), '9': ('F', 'Fuel station'), ';': ('P', 'Park'),
    '<': ('!', 'Advisory'), '=': ('■', 'Overlay symbol group'), '>': ('C', 'Vehicle'),
    '?': ('?', 'Information kiosk'), '@': ('H', 'Tropical cyclone'),
    'A': ('■', 'DTMF/RFID identifier'), 'C': ('C', 'Coast Guard'),
    'D': ('D', 'Depot'), 'E': ('S', 'Smoke or visibility'), 'H': ('H', 'Haze or hazard'),
    'I': ('R', 'Rain shower'), 'K': ('H', 'Kenwood handheld'), 'L': ('L', 'Lighthouse'),
    'M': ('M', 'MARS'), 'N': ('B', 'Navigation buoy'), 'O': ('O', 'Balloon or rocket'),
    'P': ('P', 'Parking'), 'Q': ('Q', 'Earthquake'), 'R': ('R', 'Restaurant'),
    'S': ('S', 'Satellite'), 'T': ('T', 'Thunderstorm'), 'U': ('S', 'Sun'),
    'V': ('V', 'VORTAC'), 'W': ('W', 'National Weather Service'), 'X': ('P', 'Pharmacy'),
    'Y': ('R', 'Radio or device'), '[': ('C', 'Wall cloud'), '\\': ('G', 'GPS'),
    '^': ('A', 'Aircraft'), '_': ('W', 'Weather station'), '`': ('R', 'Rain'),
    'a': ('A', 'Radio organization'), 'c': ('▲', 'Civil defense'),
    'd': ('D', 'DX callsign spot'), 'e': ('S', 'Sleet'), 'f': ('F', 'Funnel cloud'),
    'g': ('G', 'Gale'), 'h': ('H', 'Store or hamfest'), 'i': ('■', 'Point of interest'),
    'j': ('W', 'Work zone'), 'k': ('V', 'Special vehicle'), 'l': ('■', 'Area'),
    'm': ('S', 'Value sign'), 'n': ('▲', 'Triangle'), 'o': ('○', 'Circle'),
    'r': ('R', 'Restroom'), 's': ('S', 'Boat'), 't': ('T', 'Tornado'),
    'u': ('T', 'Truck'), 'v': ('V', 'Van'), 'w': ('F', 'Flood or earth movement'),
    'x': ('×', 'Wreck or obstruction'), 'y': ('S', 'Skywarn'), 'z': ('⌂', 'Shelter'),
    '|': ('T', 'TNC stream switch'), '~': ('T', 'TNC stream switch'),
}


def display_symbol(table, code):
    """Return fresh display metadata without inferring role or operational state.

    Overlays retain their raw character and alternate base name. Their specific
    meanings are deliberately not guessed from the overlay letter.
    """
    valid_code = isinstance(code, str) and len(code) == 1 and 33 <= ord(code) <= 126
    overlay = table if isinstance(table, str) and len(table) == 1 and table.isascii() and ('A' <= table <= 'Z' or '0' <= table <= '9') else None
    base = '/' if table == '/' else '\\' if table == '\\' or overlay is not None else None
    entry = (PRIMARY if base == '/' else ALTERNATE).get(code) if valid_code and base else None
    glyph, name = entry or ('?', 'Unknown or unassigned APRS symbol')
    return dict(table=table, code=code, base_table=base, overlay=overlay,
                name=name, glyph=glyph, known=entry is not None,
                glyph_kind='terminal_approximation', source=SOURCE)
