"""One-way reader for pre-binary Pocket state; never used to write runtime data."""

def decode(raw):
    import json
    return json.loads(raw)
