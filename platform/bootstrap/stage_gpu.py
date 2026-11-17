#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Stage the matching MBX module, Mesa and Pocket GPU owner into a Debian root."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parents[2]
RUNTIME = REPO / 'graphics/mbx/runtime'
SOURCE = Path(__file__).with_name('gpu_runtime')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def inputs(runtime, module_package, mesa_package, kernel_package):
    profile = json.loads((runtime / 'runtime-profile.json').read_text())
    if profile.get('profile') != 'release':
        raise ValueError('GPU image requires a release Pocket runtime')
    for name, want in profile['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or digest(runtime / path) != want:
            raise ValueError('Pocket runtime checksum differs: ' + name)
    frontend = json.loads((runtime / 'build/graphics/BUILD.json').read_text())
    module = json.loads((module_package / 'BUILD.json').read_text())
    mesa = json.loads((mesa_package / 'BUILD.json').read_text())
    kernel = json.loads((kernel_package / 'BUILD.json').read_text())
    release = kernel['release']
    if frontend.get('scene_gl') is not True or frontend.get('gpu_renderer') is not True:
        raise ValueError('Pocket frontend was not built with the GPU scene')
    if module.get('target') != 'module' or module.get('kernel_release') != release or module.get('crc_checks', 0) < 80:
        raise ValueError('MBX module does not match the image kernel')
    if module['source_sha256']['build-inputs/Module.symvers'] != digest(kernel_package / 'Module.symvers'):
        raise ValueError('MBX module was built against different kernel symbols')
    if mesa.get('target') != 'mesa':
        raise ValueError('Missing ARM Mesa build record')
    osmesa = mesa_package / 'libOSMesa.so.8'
    if frontend.get('mesa_sha256') != digest(osmesa) or \
            profile['files'].get('build/graphics/libOSMesa.so.8') != digest(osmesa):
        raise ValueError('Frontend and Mesa libraries differ')
    for name in ('window.so', '_cellengine.abi3.so', 'renderer.so'):
        if 'build/graphics/' + name not in profile['files']:
            raise ValueError('Missing GPU frontend library: ' + name)
    for name, want in frontend.get('artifacts', {}).items():
        if name in ('window.so', 'renderer.so') and profile['files'].get('build/graphics/' + name) != want:
            raise ValueError('GPU frontend build record differs: ' + name)
    binary = module_package / 'n810_mbx_gpu_probe.ko'
    if not binary.is_file():
        raise ValueError('Missing ARM MBX module')
    header = binary.read_bytes()[:20]
    if header[:5] != b'\x7fELF\x01' or header[18:20] != b'\x28\x00':
        raise ValueError('Missing ARM MBX module')
    return profile, release, binary, osmesa


def stage(root, runtime, module_package, mesa_package, kernel_package):
    root, runtime = Path(root), Path(runtime)
    profile, release, binary, osmesa = inputs(runtime, Path(module_package),
                                               Path(mesa_package), Path(kernel_package))
    staged = root / 'usr/local/share/pocket'
    if not staged.is_dir() or json.loads((staged / 'runtime-profile.json').read_text()) != profile:
        raise ValueError('Stage this exact Pocket runtime before its GPU owner')
    for name, want in profile['files'].items():
        if digest(staged / name) != want:
            raise ValueError('Staged Pocket runtime checksum differs: ' + name)
    module_hash = digest(binary)
    release_name = 'bootstrap-' + module_hash[:12]
    graphics = root / 'usr/local/lib/n810-graphics'
    target = graphics / 'releases' / release_name
    if target.exists():
        raise ValueError('GPU release already staged; use a clean build root')
    target.mkdir(parents=True)
    files = {
        'n810_mbx_gpu_probe.ko': binary,
        'libOSMesa.so.8': osmesa,
        'window.so': staged / 'build/graphics/window.so',
        'renderer.so': staged / 'build/graphics/renderer.so',
        '_cellengine.abi3.so': staged / 'build/graphics/_cellengine.abi3.so',
    }
    hashes = {}
    for name, source in files.items():
        shutil.copyfile(source, target / name)
        hashes[name] = digest(target / name)
    # Pixel apps resolve this public entry point beside the selected renderer.
    (target / 'room-pixels.so').symlink_to('renderer.so')
    hashes['room-pixels.so'] = hashes['renderer.so']
    (target / 'defaults.json').write_text((SOURCE / 'defaults.json').read_text())
    hashes['defaults.json'] = digest(target / 'defaults.json')
    (target / 'MANIFEST.json').write_text(json.dumps({
        'kernel_release': release, 'files': hashes, 'source_commit': profile['source_commit']}, indent=2) + '\n')
    current = graphics / 'current'
    if current.exists() or current.is_symlink():
        current.unlink()
    current.symlink_to('releases/' + release_name)
    template = root / 'usr/local/lib/n810-pocket/native-template'
    template.mkdir(parents=True, exist_ok=True)
    for source in RUNTIME.glob('*.py'):
        shutil.copyfile(source, template / source.name)
    for name in ('owner_session.py', 'run_service_frame.py', 'PARAMETERS.json', 'PROBE-SETTINGS.json'):
        shutil.copyfile(SOURCE / name, template / name)
    payload = template / 'payload'
    payload.mkdir(exist_ok=True)
    shutil.copyfile(binary, payload / binary.name)
    (template / 'BUILD.json').write_text(json.dumps({'module_sha256': module_hash}, indent=2) + '\n')
    (template / 'MANIFEST.json').write_text(json.dumps({'files': {
        'payload/n810_mbx_gpu_probe.ko': {'sha256': module_hash}}}, indent=2) + '\n')
    owner = template.parent
    for name in ('native_owner.py', 'symbian_session.py', 'symbian_windows.py'):
        shutil.copyfile(REPO / 'pocket/platform/n810' / name, owner / name)
    shutil.copyfile(REPO / 'pocket/shell/symbian_catalog.py', owner / 'symbian_catalog.py')
    managed = root / 'usr/local/share/pocket-gui/managed-native'
    managed.mkdir(parents=True, exist_ok=True)
    for name, destination in (('source', '/usr/local/share/pocket'),
                              ('assets', '/usr/local/share/pocket/build/graphics')):
        link = managed / name
        if link.exists() or link.is_symlink():
            link.unlink()
        link.symlink_to(destination)
    unit = root / 'etc/systemd/system/pocket-desktop.service'
    text = unit.read_text().replace('/usr/local/lib/pocket/bootstrap_desktop.py --user nokia',
                                    '/usr/local/lib/n810-pocket/native_owner.py')
    text = text.replace('Restart=on-failure', 'Restart=no')
    if text == unit.read_text() or 'native_owner.py' not in text:
        raise ValueError('Unexpected Pocket desktop service; GPU owner not installed')
    unit.write_text(text)
    install = staged / 'INSTALL.json'
    record = json.loads(install.read_text())
    record.update(renderer='native-mbx-gpu', module_sha256=module_hash,
                  mesa_sha256=hashes['libOSMesa.so.8'], gpu_release=release_name)
    install.write_text(json.dumps(record, indent=2) + '\n')
    from stage_desktop import make_readable_tree
    for relative in ('usr/local/lib/n810-graphics', 'usr/local/lib/n810-pocket',
                     'usr/local/share/pocket-gui'):
        make_readable_tree(root, relative)
    return record


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'runtime', 'module-package', 'mesa-package', 'kernel-package'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    if os.geteuid() != 0 or a.root.resolve() == Path('/'):
        p.error('Use a separate Debian build root as root')
    print(json.dumps(stage(a.root, a.runtime, a.module_package, a.mesa_package,
                           a.kernel_package), indent=2))


if __name__ == '__main__':
    main()
