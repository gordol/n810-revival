#!/usr/bin/env python3
"""Prepare regional field packs and exchange private observations."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'shell'))
import field_companion as field


def prepare(manifest):
    data = json.loads(field.bounded_bytes(manifest))
    if not isinstance(data, dict) or not isinstance(data.get('cards'), list):
        raise ValueError('Expected a manifest with a cards list')
    total = 0
    for card in data['cards']:
        field.mapping(card, 'id kind title file source terms')
        path = (manifest.parent/field.text(card.pop('file'), 512)).resolve()
        if not path.is_relative_to(manifest.parent.resolve()):
            raise ValueError('Card file must be in the manifest directory')
        with path.open('rb') as stream:
            raw = stream.read(64001)
        total += len(raw)
        if len(raw) > 64000 or total > field.LIMIT:
            raise ValueError('Card sources exceed pack limits')
        card['body'] = raw.decode().replace('\r\n', '\n').strip()
    return field.check_pack(data)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, default=field.state_root())
    actions = parser.add_subparsers(dest='action', required=True)
    build = actions.add_parser('build')
    build.add_argument('manifest', type=Path)
    build.add_argument('output', type=Path)
    for action in ('install', 'import-log'):
        actions.add_parser(action).add_argument('file', type=Path)
    note = actions.add_parser('note')
    note.add_argument('region')
    note.add_argument('text')
    note.add_argument('--source', required=True)
    note.add_argument('--kind', choices=['note','transcript','translation'], default='note')
    export = actions.add_parser('export-log')
    export.add_argument('region')
    export.add_argument('output', type=Path)
    export.add_argument('--after-id', default='', help='Continue after the UUID printed by the previous export')
    args = parser.parse_args()
    if args.action == 'build':
        field.write_file(args.output, prepare(args.manifest))
    elif args.action == 'install':
        print(field.activate(args.file, args.state)['region'])
    else:
        journal = field.Journal(args.state)
        if args.action == 'export-log':
            notes, cursor = journal.export_page(args.region, args.after_id)
            field.write_log(args.output, notes)
            if cursor:
                print(f'More observations available. Export to a new file with --after-id {cursor}')
        else:
            batch = (field.read_log(args.file) if args.action == 'import-log' else
                     dict(format=field.LOG, notes=[field.observation(args.region, args.source, args.kind, args.text)]))
            print(f'{journal.merge(batch)} observations added')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError) as error:
        sys.exit(str(error))
