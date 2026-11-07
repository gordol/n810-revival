"""Narrow protected-data TX experiment; patches a build-local copy, never the SDK."""
import hashlib
from pathlib import Path
import struct
import subprocess

ARCHIVE_SHA='6db8c03e58385cae462871647c680489ba84b5c29e86abca9c89dca9d8bb7ba1'
OBJECT_SHA='386117a09e188a23429f3597f232b8be145cfb52fd82794218c846b2042c32d5'
RX_ARCHIVE_SHA='a4356534d066da8c1ce08b52e3e614ee4da1a3e9b3b4bfc4285d083f46b75937'
RX_OBJECT_SHA='9d30a29a4b42e7b9cbc6ddee1522e0dd06ea31bfed2b10d9dd2506e62dc2b3f3'


def patch_object(raw,allow_auth=False):
    if hashlib.sha256(raw).hexdigest()!=OBJECT_SHA:
        raise ValueError('Unrecognized ESP32 raw-TX object; refusing to patch')
    result=bytearray(raw)
    offset=struct.unpack_from('<I',raw,32)[0]
    size,count,strings=struct.unpack_from('<HHH',raw,46)
    heads=[struct.unpack_from('<IIIIIIIIII',raw,offset+i*size) for i in range(count)]
    h=heads[strings];names=raw[h[4]:h[4]+h[5]]
    sections={names[h[0]:].split(b'\0',1)[0].decode():h for h in heads}
    text=sections['.text.ieee80211_raw_frame_sanity_check']
    site=text[4]+0xe9
    if raw[site:site+3]!=bytes.fromhex('463b00'):
        raise ValueError('Protected-bit rejection instruction differs')
    # Replace ONLY the protected-bit rejection branch with a 3-byte Xtensa NOP.
    # Length, subtype, address and other stock validation remain in place.
    result[site:site+3]=bytes.fromhex('f02000')
    if allow_auth:
        # In the isolated RSN target, admit authentication instead of action
        # management frames. Preserve the stock size/address/FC validation.
        pos=text[4]+0x117
        if raw[pos:pos+3]!=bytes.fromhex('72a0d0'):raise ValueError('Management subtype instruction differs')
        result[pos:pos+3]=bytes.fromhex('72a0b0')
    reloc=sections['.rela.text.ieee80211_raw_frame_sanity_check']
    found=0
    for entry in range(reloc[4],reloc[4]+reloc[5],reloc[9]):
        address,info,addend=struct.unpack_from('<IIi',raw,entry)
        if address==0xe9:
            if info&255!=20 or addend!=0x1da:raise ValueError('Unexpected branch relocation')
            struct.pack_into('<I',result,entry+4,info&~255) # R_XTENSA_NONE
            found+=1
    if found!=1:raise ValueError('Expected exactly one protected-bit relocation')
    return bytes(result)


def patch_archive(source,destination,ar,allow_auth=False):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Never patch the shared SDK')
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=ARCHIVE_SHA:raise ValueError('Unrecognized SDK archive')
    destination.parent.mkdir(parents=True,exist_ok=True)
    raw=subprocess.check_output([str(ar),'p',str(source),'ieee80211_output.o'])
    patched=patch_object(raw,allow_auth)
    # Rebuild one archive member in a private build directory.
    member=destination.parent/'ieee80211_output.o'
    member.write_bytes(patched);destination.write_bytes(data)
    subprocess.run([str(ar),'r',str(destination),str(member)],check=True)
    subprocess.run([str(ar),'s',str(destination)],check=True)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=ARCHIVE_SHA:
        raise ValueError('Shared SDK changed during patching')
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def patch_rx_object(raw):
    """LAB: include otherwise skipped normal frames in the promiscuous copy.

    Only removes the descriptor-bit-31 gate in wDev_ProcessRxSucData. Existing
    receive-error handling, interface, promiscuous-mode and AMPDU checks remain.
    Exact descriptor bit semantics are not assumed; test before integration.
    """
    if hashlib.sha256(raw).hexdigest()!=RX_OBJECT_SHA:raise ValueError('Unknown RX object')
    result=bytearray(raw)
    offset=struct.unpack_from('<I',raw,32)[0]
    size,count,strings=struct.unpack_from('<HHH',raw,46)
    heads=[struct.unpack_from('<IIIIIIIIII',raw,offset+i*size) for i in range(count)]
    h=heads[strings];names=raw[h[4]:h[4]+h[5]]
    sections={names[h[0]:].split(b'\0',1)[0].decode():h for h in heads}
    text=sections['.wifislprxiram.30'];site=text[4]+0x151
    if raw[site:site+3]!=bytes.fromhex('d64a05'):raise ValueError('RX descriptor gate changed')
    result[site:site+3]=bytes.fromhex('f02000')
    rela=sections['.rela.wifislprxiram.30'];found=0
    for pos in range(rela[4],rela[4]+rela[5],rela[9]):
        address,info,addend=struct.unpack_from('<IIi',raw,pos)
        if address==0x151:
            if info&255!=20 or addend!=0x1a9:raise ValueError('RX descriptor relocation changed')
            struct.pack_into('<I',result,pos+4,info&~255);found+=1
    if found!=1:raise ValueError('Missing RX descriptor relocation')
    return bytes(result)


def patch_rx_archive(source,destination,ar):
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Never patch the shared SDK')
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=RX_ARCHIVE_SHA:raise ValueError('Unknown RX SDK archive')
    destination.parent.mkdir(parents=True,exist_ok=True)
    member=destination.parent/'wdev.o'
    member.write_bytes(patch_rx_object(subprocess.check_output([str(ar),'p',str(source),'wdev.o'])))
    destination.write_bytes(data)
    subprocess.run([str(ar),'r',str(destination),str(member)],check=True)
    subprocess.run([str(ar),'s',str(destination)],check=True)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=RX_ARCHIVE_SHA:raise ValueError('Shared SDK changed')
    return hashlib.sha256(destination.read_bytes()).hexdigest()


def observer_archive(source,destination,ar,objcopy,tx_selector=False):
    """Preserve executable sections; make one RX entry interposable with an alias.

    Our strong lab wrapper observes then calls the original via the alias. No
    SDK instruction, receive filter, DMA ownership or interrupt is replaced.
    """
    source,destination=Path(source),Path(destination)
    if source.resolve()==destination.resolve():raise ValueError('Never change the shared SDK')
    data=source.read_bytes()
    if hashlib.sha256(data).hexdigest()!=RX_ARCHIVE_SHA:raise ValueError('Unknown RX archive')
    raw=subprocess.check_output([str(ar),'p',str(source),'wdev.o'])
    if hashlib.sha256(raw).hexdigest()!=RX_OBJECT_SHA:raise ValueError('Unknown RX object')
    destination.parent.mkdir(parents=True,exist_ok=True)
    original=destination.parent/'wdev-original.o';member=destination.parent/'wdev.o'
    original.write_bytes(raw)
    subprocess.run([str(objcopy),'--weaken-symbol=wDev_ProcessRxSucData',
        '--add-symbol=pocket_vendor_process_rx=.wifislprxiram.30:0x70,global,function',
        str(original),str(member)],check=True)
    def allocated(blob):
        offset=struct.unpack_from('<I',blob,32)[0];size,count,strings=struct.unpack_from('<HHH',blob,46)
        heads=[struct.unpack_from('<IIIIIIIIII',blob,offset+i*size) for i in range(count)]
        h=heads[strings];names=blob[h[4]:h[4]+h[5]]
        return {names[h[0]:].split(b'\0',1)[0]:(h[1],h[5],blob[h[4]:h[4]+h[5]] if h[1]!=8 else b'')
                for h in heads if h[2]&2}
    if allocated(raw)!=allocated(member.read_bytes()):raise ValueError('Observer altered allocated SDK sections')
    members=[member]
    if tx_selector:
        tx_raw=subprocess.check_output([str(ar),'p',str(source),'hal_mac_tx.o'])
        if hashlib.sha256(tx_raw).hexdigest()!='c864aeb68d206ad321857f859d95b480ac00fcd57c15134c2c7113f8f69d24d1':raise ValueError('Unknown TX selector object')
        tx_original=destination.parent/'hal_mac_tx-original.o';tx_member=destination.parent/'hal_mac_tx.o'
        tx_original.write_bytes(tx_raw)
        subprocess.run([str(objcopy),'--weaken-symbol=mac_tx_set_plcp1',
            '--add-symbol=pocket_vendor_tx_plcp1=.text.mac_tx_set_plcp1:0x10,global,function',
            str(tx_original),str(tx_member)],check=True)
        if allocated(tx_raw)!=allocated(tx_member.read_bytes()):raise ValueError('TX selector altered allocated SDK sections')
        members.append(tx_member)
    destination.write_bytes(data)
    subprocess.run([str(ar),'r',str(destination),*map(str,members)],check=True)
    subprocess.run([str(ar),'s',str(destination)],check=True)
    if hashlib.sha256(source.read_bytes()).hexdigest()!=RX_ARCHIVE_SHA:raise ValueError('Shared SDK changed')
    return hashlib.sha256(destination.read_bytes()).hexdigest()
