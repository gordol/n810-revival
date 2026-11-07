#!/usr/bin/env python3
"""Export the reviewed Git index as a deterministic source-and-notice archive."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def tracked_entries(root):
    algorithm = subprocess.check_output(['git', 'rev-parse', '--show-object-format'], cwd=root).decode().strip()
    records = subprocess.check_output(['git', 'ls-files', '--stage', '-z'], cwd=root)
    for record in records.split(b'\0'):
        if not record:
            continue
        metadata, raw_name = record.split(b'\t', 1)
        mode, oid, stage = metadata.decode().split()
        name = raw_name.decode('utf-8')
        path = PurePosixPath(name)
        if stage != '0' or mode not in ('100644', '100755'):
            raise ValueError(f'Unmerged or unsupported entry: {name}')
        if path.is_absolute() or '..' in path.parts:
            raise ValueError(f'Unsafe archive path: {name}')
        source = root / name
        if source.is_symlink():
            raise ValueError(f'Symlink in working tree: {name}')
        raw = source.read_bytes()
        actual = hashlib.new(algorithm, b'blob ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()
        if actual != oid:
            raise ValueError(f'Stage reviewed changes before exporting: {name}')
        yield name, int(mode, 8) & 0o777, raw


def is_documentation(name):
    return (name.startswith('docs/') or name.startswith('tools/docs/')
            or name in ('mkdocs.yml', 'requirements-docs.lock', 'tools/docs_hooks.py',
                        'tools/journal-sources.json', 'tools/check-journal.py'))

def release_bytes(name, raw):
    if (name.startswith(('maintainers/', 'licenses/evidence/'))
            or name in ('LICENSE-PROVENANCE.json', 'LICENSE-REVIEW.json',
                        'data-review.json', 'tools/journal-verification.json',
                        'SOURCE-SNAPSHOT.json', 'DOCS-SNAPSHOT.json',
                        'docs/assets/screenshots/review.json')):
        return None
    if name == 'LICENSE-SCOPE.json':
        scope = json.loads(raw)
        keep = ('path', 'sha256', 'license', 'scope', 'limits', 'grant')
        scope = {'version': scope['version'], 'files': [
            {key: entry[key] for key in keep if key in entry}
            for entry in scope['files']]}
        return (json.dumps(scope, separators=(',', ':')) + '\n').encode()
    return raw


def export(root, output, docs_only=False):
    if output.exists():
        raise ValueError('Choose a new output path; existing archives are preserved')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {'format': 1, 'kind': 'documentation-snapshot' if docs_only else 'repository-source-snapshot', 'files': {}}
    temporary = output.with_name(output.name + '.partial')
    if temporary.exists():
        raise ValueError('An unfinished export exists at the temporary path')
    try:
        with temporary.open('xb') as target, gzip.GzipFile(filename='', mode='wb', fileobj=target, mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w|') as archive:
            def add(name, raw, mode=0o644):
                info = tarfile.TarInfo('n810-revival/' + name)
                info.size, info.mode, info.mtime = len(raw), mode, 0
                archive.addfile(info, io.BytesIO(raw))
            for name, mode, raw in tracked_entries(root):
                if is_documentation(name) != docs_only:
                    continue
                raw = release_bytes(name, raw)
                if raw is None:
                    continue
                manifest['files'][name] = {'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw), 'mode': oct(mode)}
                add(name, raw, mode)
            add('DOCS-SNAPSHOT.json' if docs_only else 'SOURCE-SNAPSHOT.json', (json.dumps(manifest, sort_keys=True, indent=2) + '\n').encode())
        temporary.rename(output)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    with output.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    output.with_name(output.name + '.sha256').write_text(f'{digest}  {output.name}\n')
    return len(manifest['files']), digest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--list-context', action='store_true', help='List release or tracked source paths for Docker, separated by NUL')
    parser.add_argument('--docs-only', action='store_true', help='Export the complete documentation and media separately from source')
    args = parser.parse_args()
    if args.list_context:
        import sys
        snapshots = [ROOT / n for n in ('SOURCE-SNAPSHOT.json', 'DOCS-SNAPSHOT.json')]
        if snapshots[0].exists():
            names = set()
            for snapshot in snapshots:
                if snapshot.exists():
                    names.update(json.loads(snapshot.read_text())['files'])
                    names.add(snapshot.name)
            sys.stdout.buffer.write(b'\0'.join(n.encode() for n in sorted(names)) + b'\0')
        else:
            sys.stdout.buffer.write(subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT))
        raise SystemExit(0)
    if args.output is None:
        parser.error('--output is required for archive export')
    count, digest = export(ROOT, args.output.resolve(), args.docs_only)
    print(f'Exported {count} reviewed source/asset/notice files; SHA256 {digest}')
