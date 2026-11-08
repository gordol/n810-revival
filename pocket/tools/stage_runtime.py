"""Stage a release or developer runtime without tests or build dependencies.

Native libraries remain target-specific: optionally supply the frontend.json
from the already built target. This command does not compile or access devices.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from package_nokia import runtime_files
from runtime_profile import profile_files

ROOT = Path(__file__).resolve().parents[1]
GRAPHICS_BUILD_TOOLS = {'build.py', 'build_nokia.py', 'check.py', 'check_full.py', 'gui.py', 'generate_room.py', 'extend_font.py'}


def stage(destination, profile='release', frontend=None):
    if destination.exists():
        raise ValueError('output must be a new directory')
    paths = subprocess.check_output(['git', 'ls-files', 'shell', 'graphics'], cwd=ROOT, text=True).splitlines()
    shell = {p[6:]: (ROOT / p).read_bytes() for p in paths if p.startswith('shell/')}
    files = {'shell/' + n: raw for n, raw in runtime_files(shell, profile).items()}
    graphics = {p: (ROOT / p).read_bytes() for p in paths if p.startswith('graphics/')
                and Path(p).suffix == '.py' and 'native' not in Path(p).parts
                and not Path(p).name.startswith(('test', 'check', 'bench'))
                and Path(p).name not in GRAPHICS_BUILD_TOOLS}
    if profile == 'release':
        for name in ('graphics/launch.py', 'graphics/desktop.py'):graphics.pop(name, None)
    files.update(profile_files(graphics, profile))
    for name in ('graphics/LICENSE-MIT', 'graphics/SOURCES.json'):
        files[name] = (ROOT / name).read_bytes()
    aliases = {}
    if frontend:
        config = json.loads(frontend.read_text())
        for key, value in list(config.items()):
            if profile == 'release' and key == 'renderer_library':
                del config[key]  # Used only by the isolated fixture frontend.
                continue
            if key == 'graphics_path':
                config[key] = 'graphics'
            elif key.endswith('_library') or key == 'font':
                source = Path(value)
                if not source.is_absolute():source = frontend.parent / source
                if key == 'effect_library' and not source.is_file():
                    del config[key]  # Optional macOS effects are not built on Linux.
                    continue
                name = 'build/graphics/' + source.name
                files[name] = source.read_bytes()
                if key == 'native_library' and (source.parent/'provenance.json').is_file():
                    files['build/graphics/provenance.json'] = (source.parent/'provenance.json').read_bytes()
                if key == 'font':
                    for suffix in ('.glyphs', '.smooth'):
                        sidecar=source.with_suffix(suffix)
                        if sidecar.is_file():files['build/graphics/'+sidecar.name]=sidecar.read_bytes()
                config[key] = name
        # Pixel views load these siblings of the selected renderer.
        for leaf in ('room-pixels.so', 'libOSMesa.so.8'):
            source=frontend.parent/leaf
            if not source.is_file():continue
            name='build/graphics/'+leaf
            target='build/graphics/'+source.resolve().name
            if source.is_symlink() and target in files:aliases[name]=Path(target).name
            else:files[name]=source.read_bytes()
        files['build/graphics/frontend.json'] = (json.dumps(config, indent=2) + '\n').encode()
    revision=subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True)
    commit=revision.stdout.strip() if revision.returncode==0 else None
    content_hash=hashlib.sha256(b''.join(name.encode()+hashlib.sha256(raw).digest() for name,raw in sorted(files.items()))).hexdigest()
    files['shell/build-info.json']=(json.dumps(dict(schema_version=1,release_id=commit[:12] if commit else 'UNKNOWN',
        framework_commit=commit,domain_commit=commit,build_profile=profile,platform='native-gui',backend='native pixels',
        artifact_sha256=content_hash,touch_acquisition_default='process',product_version=(ROOT/'VERSION').read_text().strip()),indent=2)+'\n').encode()
    destination.mkdir(parents=True)
    for name, raw in files.items():
        path = destination / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    for name, target in aliases.items():(destination/name).symlink_to(target)
    manifest={'profile':profile,'source_commit':commit,
              'files':{name:hashlib.sha256(raw).hexdigest() for name,raw in sorted(files.items())},'aliases':aliases}
    (destination / 'runtime-profile.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--profile', choices=('release', 'dev'), default='release')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--frontend', type=Path, help='optional built target frontend.json')
    args = parser.parse_args()
    files = stage(args.output, args.profile, args.frontend)
    print(json.dumps({'profile': args.profile, 'files': len(files), 'bytes': sum(map(len, files.values()))}))


if __name__ == '__main__':main()
