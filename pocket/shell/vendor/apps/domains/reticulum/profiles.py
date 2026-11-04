"""Sourced community examples; selecting a profile does not tune a radio."""

PROFILES = (
    dict(id='chicagoland', label='Chicagoland community', frequency=914875000,
         bandwidth=125000, spreadingfactor=8, codingrate=5,
         source='https://chicagolandmesh.org/guides/reticulum/getting-started/configure/'),
    dict(id='ottawa', label='Ottawa community', frequency=914875000,
         bandwidth=125000, spreadingfactor=7, codingrate=7,
         source='https://ottawamesh.ca/reticulum/reticulum-frequency-settings/'),
    dict(id='nepamesh', label='NEPAMesh published example', frequency=912345000,
         bandwidth=500000, spreadingfactor=11, codingrate=8,
         source='https://nepamesh.com/nepamesh-reticulum-primer/'),
)


def occupied_band(profile):
    return (profile['frequency'] - profile['bandwidth'] / 2,
            profile['frequency'] + profile['bandwidth'] / 2)


def summary(profile):
    return '{} · {:.3f} MHz / {} kHz / SF{} / CR4/{}'.format(
        profile['label'], profile['frequency'] / 1e6, profile['bandwidth'] / 1000,
        profile['spreadingfactor'], profile['codingrate'])
