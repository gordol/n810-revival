"""Exact self-address preferences in the existing saved app preferences."""


def self_calls(preferences):
    if 'station-self' not in preferences:
        return None  # Domain's exact N0CALL default, never its SSID family.
    group = preferences['station-self']
    return tuple(group[key] for key in sorted(group) if key.startswith('self-call-'))


def with_self_calls(preferences, calls):
    # One scalar per address preserves all 32 domain identities without a long
    # text value exceeding the existing preference scalar limit.
    group = {f'self-call-{index:02d}': call for index, call in enumerate(calls)}
    return {**preferences, 'station-self': group}
