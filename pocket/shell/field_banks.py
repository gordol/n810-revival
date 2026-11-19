"""Browse local BTECH banks and radio frequency references from a field pack."""
import csv
from pathlib import Path


def load(root):
    groups = []
    for path in sorted((root / 'uv-pro').glob('*.csv')):
        rows = []
        for source in _records(path):
            r = {k.split('(')[0]: v for k, v in source.items()}
            air = int(r['rx_modulation'])
            inhibit=int(r['tx_dis'])
            if (air not in (0,1) or inhibit not in (0,1) or (air and not inhibit) or int(r['tx_modulation']) or
                    r['tx_power']!='L' or int(r['bandwidth']) not in (12500,25000) or
                    int(r['rx_sub_audio']) or int(r['scan'])!=1 or any(int(r[k]) for k in
                    ('talk around','pre_de_emph_bypass','sign','mute'))):
                raise ValueError('Unsupported channel fields in '+path.name)
            title=r['title']
            label=title if len(title)<=10 else title[:3]+title[-7:]
            row=[label,int(r['rx_freq']),int(r['tx_freq']),int(r['tx_sub_audio']),int(r['bandwidth'])==25000,air]
            row[4]=int(row[4])
            if inhibit and not air:row.append(inhibit)
            rows.append((title,row[1],'AM · RX only' if air else 'FM · RX only' if inhibit else 'FM',row))
        if rows:groups.append((path.stem,rows))
    sources = [(path.parent.name, path) for path in sorted((root / 'radios').glob('*/frequencies.csv'))]
    legacy = root / 'belka' / 'frequencies.csv'
    if legacy.is_file() and not any(label.casefold() == 'belka' for label, _ in sources):
        sources.append(('Belka', legacy))
    for radio, path in sources:
        banks = {}
        for record in _records(path):
            name = record.get('bank') or 'Frequencies'
            details = [record['mode'], record.get('utc')]
            if record.get('tx_hz'):
                details.append(f"TX {int(record['tx_hz']) / 1e6:g} MHz")
            mode = ' · '.join(filter(None, details))
            banks.setdefault(name, []).append((record['station'], int(record['hz']), mode, None))
        groups.extend((f'{radio} {name}', rows) for name, rows in banks.items())
    return groups


def _records(path):
    with path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream, strict=True)
        try:
            if not reader.fieldnames or any(not name for name in reader.fieldnames) or len(set(reader.fieldnames)) != len(reader.fieldnames):
                raise ValueError(f'Invalid CSV header in {path.name}')
            for record in reader:
                if None in record or any(value is None for value in record.values()):
                    raise ValueError(f'Invalid column count in {path.name} at row {reader.line_num}')
                yield record
        except (csv.Error,UnicodeError) as error:
            raise ValueError(f'Invalid CSV in {path.name} at row {reader.line_num}: {error}') from error
