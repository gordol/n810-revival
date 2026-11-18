"""Read bank names and current memories on the existing UV-PRO connection."""
import datetime
import importlib.util
import json
from pathlib import Path


def download(selected, address, root, atomic):
    layouts = json.loads(Path(__file__).with_name('radio-read-layouts.json').read_bytes())
    spec = importlib.util.spec_from_file_location('bank_wire', Path(__file__).with_name('n810-radio-backup.py'))
    wire = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(wire)

    def decode(raw, layout):
        if len(raw) * 8 != sum(field[1] for field in layouts[layout]):
            raise ValueError('Unknown ' + layout + ' layout')
        return wire.decode(raw, layouts[layout])

    status = decode((yield 20, b''), 'StatusExt')
    active = status['curr_region']
    device = decode((yield 4, b'\x03'), 'DevInfo')
    groups, count = device['region_count'], device['channel_count']
    if not 0 <= active < groups or not count:
        raise ValueError('Invalid radio bank or channel count')
    names = []
    for index in range(groups):
        raw = yield 73, bytes([index])
        if not raw or raw[0] != index:
            raise ValueError('Bank name reply has the wrong index')
        names.append(raw[1:].split(b'\0', 1)[0].decode('gbk', errors='replace'))

    if selected is not None and selected != active:
        raise ValueError('Radio is receiving on bank %d. Its channel read addresses the active bank only.' % active)
    channels = []
    for index in range(count):
        raw = yield 13, bytes([index])
        row = decode(raw, 'RfChDMR' if len(raw) == 27 else 'RfCh')
        if row['channel_id'] != index:
            raise ValueError('Channel reply has the wrong index')
        channels.append(dict(index=index, decoded=row, response=dict(status=0, reply_hex='00'+raw.hex())))
    final = decode((yield 20, b''), 'StatusExt')
    if final['curr_region'] != active:
        raise ValueError('Active bank changed during download')
    stamp = datetime.datetime.now(datetime.timezone.utc)
    folder = root / stamp.strftime('%Y%m%dT%H%M%S.%fZ')
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    bank = dict(index=active, name=names[active], channels=channels, complete=True)
    atomic(folder/'backup.json', dict(version=1, complete=True, address=address, finished=stamp.isoformat(),
                                      banks=[bank], bank_names=names, status=final, device=device))
    return dict(bank=active, channels=count, banks=names)
