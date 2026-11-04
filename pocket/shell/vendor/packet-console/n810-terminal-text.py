"""Printable terminal text; stored and wire data stay unchanged."""
def printable(value):
    return ''.join(c if c.isprintable() else ('\\x%02x'%ord(c) if ord(c)<256 else '\\u%04x'%ord(c)) for c in str(value))
