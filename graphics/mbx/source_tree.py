"""Assemble the maintained Pocket driver over the portable Mesa integration."""
from pathlib import Path
import shutil


def assemble(base, destination):
    base, destination = Path(base), Path(destination)
    overlay = base.parents[1] / 'pocket/graphics/driver/mbx'
    for component in ('common', 'kernel', 'mesa'):
        shutil.copytree(base / component, destination / component)
        for source in (overlay / component).iterdir():
            if source.is_file() and source.suffix in ('.c', '.h'):
                shutil.copyfile(source, destination / component / source.name)
    # Replace inherited ABI copies, but retain explicit kernel extensions.
    # Mesa overrides likewise take precedence over shared common headers.
    for source in (destination / 'common').iterdir():
        if source.suffix in ('.c', '.h'):
            if (destination / 'kernel' / source.name).exists() and not (overlay / 'kernel' / source.name).exists():
                shutil.copyfile(source, destination / 'kernel' / source.name)
    shutil.copytree(base / 'build-inputs', destination / 'build-inputs')
    for source in (overlay / 'common').iterdir():
        if source.suffix in ('.c', '.h') and not (overlay / 'mesa' / source.name).exists():
            shutil.copyfile(source, destination / 'mesa' / source.name)
    return destination
