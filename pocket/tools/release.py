"""Create a deterministic, source-only release from the committed active tree."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
def git(*args): return subprocess.check_output(['git', '-C', str(ROOT), *args])

def main():
    if git('status', '--porcelain').strip():
        raise SystemExit('Commit the active tree before creating a release.')
    commit = git('rev-parse', 'HEAD').decode().strip()
    files = {}
    for name in git('ls-files', '-z').decode().strip('\0').split('\0'):
        if not name: continue
        path = ROOT/name
        if path.is_symlink(): raise SystemExit('Release requires explicit regular source files: '+name)
        files[name] = path.read_bytes()
    files['shell/build-info.json'] = (json.dumps(dict(schema_version=1,product_version=(ROOT/'VERSION').read_text().strip(),release_id=commit[:12],
        framework_commit=commit,domain_commit=commit,platform='portable-source',backend='python/native-optional',
        artifact_sha256='See RELEASE.json',touch_acquisition_default='python'),sort_keys=True)+'\n').encode()
    files['RELEASE.json'] = (json.dumps(dict(commit=commit,files={name:hashlib.sha256(data).hexdigest()
                for name,data in sorted(files.items())}),sort_keys=True,indent=2)+'\n').encode()
    destination=ROOT/'dist'/('pocket-'+commit[:12]+'.tar.gz');destination.parent.mkdir(exist_ok=True)
    buffer=io.BytesIO()
    with gzip.GzipFile(fileobj=buffer, mode='wb', filename='', mtime=0) as zipped:
        with tarfile.open(fileobj=zipped, mode='w') as archive:
            for name,data in sorted(files.items()):
                info=tarfile.TarInfo('pocket/'+name);info.size=len(data);info.mode=0o644;info.mtime=0
                archive.addfile(info,io.BytesIO(data))
    destination.write_bytes(buffer.getvalue())
    print(destination)
    print('SHA256 '+hashlib.sha256(buffer.getvalue()).hexdigest())

if __name__ == '__main__': main()
