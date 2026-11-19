"""Read bank names and current memories on the existing UV-PRO connection."""
import datetime
import importlib.util
import json
from pathlib import Path


def read_bank(selected, address):
    files=Path(__file__).resolve().parent
    if not (files/'radio-read-layouts.json').is_file():files=files.parent/'vendor/packet-console'
    layouts = json.loads((files/'radio-read-layouts.json').read_bytes())
    spec = importlib.util.spec_from_file_location('bank_wire', files/'n810-radio-backup.py')
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
    bank = dict(index=active, name=names[active], channels=channels, complete=True)
    return dict(version=1, complete=True, address=address, finished=stamp.isoformat(),
                banks=[bank], bank_names=names, status=final, device=device)


def download(selected, address, root, atomic):
    capture = yield from read_bank(selected, address)
    stamp = datetime.datetime.fromisoformat(capture['finished'])
    folder = root / stamp.strftime('%Y%m%dT%H%M%S.%fZ')
    folder.mkdir(parents=True, mode=0o700, exist_ok=False)
    atomic(folder/'backup.json', capture)
    bank = capture['banks'][0]
    return dict(bank=bank['index'], channels=len(bank['channels']), banks=capture['bank_names'])


def bank_channel(original, row):
    """Encode one field-pack channel, preserving hardware-owned fields."""
    import struct
    if len(original) not in (25, 27) or not isinstance(row, list) or len(row) not in (6,7):
        raise ValueError('Unsupported bank channel layout')
    label, rx, tx, tone, wide, air = row[:6]
    inhibit = row[6] if len(row)==7 else air
    if not isinstance(label, str) or not label.isascii() or not label.isprintable() or not 1 <= len(label) <= 10:
        raise ValueError('Invalid channel label')
    if any(type(value) is not int for value in row[1:]) or wide not in (0, 1) or air not in (0, 1) or inhibit not in (0,1) or (air and not inhibit):
        raise ValueError('Invalid channel fields')
    if air:
        if not 118000000 <= rx < 137000000 or rx != tx or tone:
            raise ValueError('Invalid receive-only air channel')
    elif inhibit:
        gmrs = rx in range(462550000,462725001,25000)
        weather = rx in range(162400000,162550001,25000)
        if not (gmrs or weather) or rx!=tx or tone:raise ValueError('Invalid FM monitor channel')
    elif not any(lo <= rx <= hi and lo <= tx <= hi for lo, hi in ((144000000,148000000),(420000000,450000000))):
        raise ValueError('Unsupported FM frequency')
    if tone and not 6000 <= tone <= 26000:
        raise ValueError('Unsupported input tone')
    flags = 0x80 | wide << 4 | inhibit  # scan, bandwidth, TX inhibit
    return (original[:1] + struct.pack('>IIHHB', tx, (air << 30) | rx, tone, 0, flags)
            + original[14:15] + label.encode('ascii').ljust(10,b'\0') + original[25:])


def upload(plan, address, root, atomic):
    from uvpro_secondary import bits, field
    if not isinstance(plan,dict) or set(plan) != {'bank','channels'}:
        raise ValueError('Invalid field bank request')
    target, rows = plan['bank'], plan['channels']
    if type(target) is not int or not 0 <= target < 64 or not isinstance(rows,list) or not 1 <= len(rows) <= 30:
        raise ValueError('Invalid destination or bank size')
    for row in rows:
        bank_channel(bytes(25),row)
    def current():
        status = yield 20,b''
        if len(status)!=4 or bits(status,20,6)!=target or not bits(status,0,1) or bits(status,1,1):
            raise ValueError('Select destination bank %d on the idle radio first' % target)
        return (bits(status,26,4) << 4) | bits(status,8,4)
    selected = yield from current()
    settings = yield 10, b''
    beacon = yield 33, b'\x02'
    if len(settings) != 22 or len(beacon) not in (50, 52):
        raise ValueError('Unsupported automatic location reporting layout')
    layouts_path = Path(__file__).with_name('radio-read-layouts.json')
    if not layouts_path.is_file():
        layouts_path = layouts_path.parent.parent / 'vendor/packet-console/radio-read-layouts.json'
    layouts = json.loads(layouts_path.read_bytes())
    settings_layout = layouts.get('Settings')
    beacon_layout = layouts.get('BSSSettings' if len(beacon) == 50 else 'BSSSettingsV2')
    if not settings_layout or not beacon_layout:
        raise ValueError('Unsupported automatic location reporting layout')
    encoded = (bits(settings, *field(settings_layout, 'auto_share_loc_ch_upper')) << 5) | bits(
        settings, *field(settings_layout, 'auto_share_loc_ch'))
    reporting = (bool(bits(beacon, *field(beacon_layout, 'should_share_location'))
                       and (bits(beacon, *field(beacon_layout, 'location_share_interval'))
                            or bits(beacon, *field(beacon_layout, 'smart_beacon_en')))))
    # Read and back up every destination slot before making any edits.
    backup = yield from download(target,address,root,atomic)
    if backup['channels'] < len(rows):
        raise ValueError('Bank has too few slots')
    if encoded > backup['channels']:
        raise ValueError('Automatic location reporting maps outside the destination bank')
    def read(index):
        raw=yield 13,bytes([index])
        if len(raw) not in (25,27) or raw[0]!=index:
            raise ValueError('Wrong channel readback')
        return raw
    pending=[]
    for index,row in enumerate(rows):
        original=yield from read(index)
        desired=bank_channel(original,row)
        if desired==original:continue
        if bits(original,42,30) or bits(original,10,30) or original[14]&0xf0:
            raise ValueError('Destination slot %d is occupied or fixed; select an empty bank' % (index+1))
        if reporting and (encoded == index + 1 or encoded == 0 and selected == index):
            raise ValueError('Automatic location reporting uses this channel; disable reporting before upload')
        pending.append((index,row,original,desired))
    for index,row,original,desired in pending:
        if (yield from current()) != selected:
            raise ValueError('Selected channel changed during upload')
        if (yield 10,b'') != settings or (yield 33,b'\x02') != beacon:
            raise ValueError('Automatic location reporting settings changed; upload cancelled')
        if (yield from read(index))!=original:
            raise ValueError('Destination channel changed')
        ack=yield 14,desired,original,{'group':'field_channel','row':row}
        if ack!=bytes([index]):
            raise ValueError('Channel acknowledgement mismatch')
        yield from current()
        if (yield from read(index))!=desired:
            raise ValueError('Channel readback mismatch')
    yield from current()
    return dict(bank=target,channels=len(rows),written=len(pending))
