"""Verify the bounded radio probe's captured standard CCMP frames, off-device."""
import argparse
import json
from pathlib import Path
import zlib
from cryptography.hazmat.primitives.ciphers.aead import AESCCM

MARKER=b'Pocket CCMP radio-path probe'


def verify_frames(lines,key):
    if len(key)!=16:raise ValueError('A private 16-byte trial key is required')
    received={};invalid=duplicates=0
    for line in lines:
        if not line.startswith('FRAME '):continue
        try:
            frame=bytes.fromhex(line.split()[1])
            if len(frame)==108:
                if zlib.crc32(frame[:-4]).to_bytes(4,'little')!=frame[-4:]:raise ValueError('FCS mismatch')
                frame=frame[:-4]
            if len(frame)!=104 or frame[0]!=8 or frame[1]&0x43!=0x40:raise ValueError('Not the probe frame')
            if frame[4:22]!=bytes.fromhex('0002eec0ffee020000000001024e38313002'):raise ValueError('Wrong peer')
            if frame[26:28]!=b'\0\x20':raise ValueError('Wrong CCMP key ID or reserved bits')
            pn=bytes([frame[31],frame[30],frame[29],frame[28],frame[25],frame[24]])
            number=int.from_bytes(pn,'big')
            nonce=b'\0'+frame[10:16]+pn
            aad=bytes([frame[0]&0x8f,(frame[1]&0xc7)|0x40])+frame[4:22]+bytes([frame[22]&15,0])
            plain=AESCCM(key,tag_length=8).decrypt(nonce,frame[32:],aad)
            if plain[:8]!=bytes.fromhex('aaaa0300000088b5') or plain[8:36]!=MARKER:raise ValueError('Wrong payload')
            if not 1<=number<=16 or plain[36]!=number-1:raise ValueError('Wrong packet sequence')
            if number in received:
                if received[number]!=plain:raise ValueError('Nonce reused for a different payload')
                duplicates+=1
            received[number]=plain
        except Exception:
            invalid+=1
    return dict(authenticated_unique_frames=len(received),packet_numbers=sorted(received),
        sequences=sorted(value[36] for value in received.values()),duplicate_frames=duplicates,
        invalid_frames=invalid,**{'pass':len(received)==16 and invalid==0})


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture',type=Path,required=True)
    parser.add_argument('--key',type=Path,required=True)
    args=parser.parse_args()
    result=verify_frames(args.capture.read_text().splitlines(),args.key.read_bytes())
    print(json.dumps(result,indent=2))
    return 0 if result['pass'] else 1


if __name__=='__main__':raise SystemExit(main())
