"""Bounded Nokia monitor capture, filtered to this probe's source and BSSID.

Run as root over a separate USB management connection. Adds/removes a monitor
interface on the current channel; does not change wlan0 type, channel or config.
Captures encrypted test frames only. No keys or unrelated frames are printed.
"""
import argparse
import hashlib
import json
import os
import socket
import signal
import struct
import subprocess
import time
import threading
from pathlib import Path


def tx_metadata(packet):
    """Bounded radiotap fields 0–17; TX failure is bit 0, no-ACK is bit 3.

    Only real TX-status headers have field 15; our injection headers do not.
    Reference: radiotap.org TX flags / data retries field definitions.
    """
    if len(packet)<8 or packet[0]:return None
    size=struct.unpack_from('<H',packet,2)[0]
    if size<8 or size>len(packet):return None
    present=struct.unpack_from('<I',packet,4)[0];word=present;offset=8
    for _ in range(8):
        if not word&(1<<31):break
        if offset+4>size:return None
        word=struct.unpack_from('<I',packet,offset)[0];offset+=4
    else:return None
    if not present&(1<<15):return None
    layout=((8,8),(1,1),(1,1),(2,4),(2,2),(1,1),(1,1),(2,2),(2,2),
            (2,2),(1,1),(1,1),(1,1),(1,1),(2,2),(2,2),(1,1),(1,1))
    flags=retries=None
    for bit,(alignment,length) in enumerate(layout):
        if not present&(1<<bit):continue
        offset=(offset+alignment-1)&~(alignment-1)
        if offset+length>size:return None
        if bit==15:flags=struct.unpack_from('<H',packet,offset)[0]
        if bit==17:retries=packet[offset]
        offset+=length
    return dict(flags=flags,data_retries=retries)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=30)
    parser.add_argument('--source',required=True,help='Probe source MAC as 12 hexadecimal digits')
    parser.add_argument('--reply-file',type=Path,help='Pre-encrypted standard reply MPDUs; contains no temporal key')
    parser.add_argument('--negative-each',action='store_true',help='Inject a bad authentication tag before every valid reply')
    args=parser.parse_args()
    if os.geteuid()!=0:raise SystemExit('Root is required for a monitor interface')
    if not 5<=args.seconds<=60:raise SystemExit('Capture must be bounded to 5–60 seconds')
    monitor='htitmon'
    if os.path.exists('/sys/class/net/'+monitor):raise SystemExit('Monitor name already exists; refusing to reuse it')
    env={**os.environ,'PATH':'/usr/local/sbin:/usr/sbin:/sbin:/usr/bin:/bin'}
    def run(*command):return subprocess.run(command,env=env,check=True,capture_output=True,text=True).stdout
    source=bytes.fromhex(args.source)
    if len(source)!=6:raise SystemExit('Source must be a six-byte MAC address')
    bssid=bytes.fromhex('024e38313002')
    replies=[]
    if args.reply_file:
        replies=[bytes.fromhex(line) for line in args.reply_file.read_text().splitlines()]
        alias=bytes([source[0]^2])+source[1:]
        if len(replies)!=16 or any(len(f)!=104 or f[:2]!=b'\x08\x40' or f[4:10] not in (source,alias) or f[10:22]!=bytes.fromhex('0002eec0ffee')+bssid for f in replies):
            raise SystemExit('Reply file does not match the bounded probe')
    created=False;frames=[];sender=None;send_errors=[]
    output_lock=threading.Lock()
    def emit(message):
        with output_lock:print(message,flush=True)
    def send_replies(raw):
        try:
            # Do not block capture while waiting past the 3.2-second TX burst.
            time.sleep(3.5)
            plain=bytearray(replies[0][:24]);plain[1]=0
            raw.send(b'\0\0\x08\0\0\0\0\0'+plain+b'PUBLIC CCMP RX PATH CHECK')
            for index,reply in enumerate(replies):
                if args.negative_each:
                    bad_tag=bytearray(reply);bad_tag[-1]^=1
                    raw.send(b'\0\0\x08\0\0\0\0\0'+bad_tag);time.sleep(0.02)
                if index==8:
                    forged=bytearray(reply);forged[31]^=0x40
                    raw.send(b'\0\0\x08\0\0\0\0\0'+forged)
                    time.sleep(0.05)
                raw.send(b'\0\0\x08\0\0\0\0\0'+reply)
                time.sleep(0.05)
            raw.send(b'\0\0\x08\0\0\0\0\0'+replies[0])
            emit('REPLIES_SENT 16; forged high-PN frame and old-frame replay injected; bad_tags='+str(16 if args.negative_each else 0))
            emit('INJECTION_STATS '+json.dumps({name:Path('/sys/class/net/'+monitor+'/statistics/'+name).read_text().strip() for name in ('tx_packets','tx_errors','tx_dropped')}))
        except Exception as error:
            send_errors.append(str(error));emit('INJECTION_ERROR '+str(error))
    def interrupted(signum,frame):raise KeyboardInterrupt()
    for signum in (signal.SIGINT,signal.SIGTERM,signal.SIGHUP):signal.signal(signum,interrupted)
    try:
        run('iw','dev','wlan0','interface','add',monitor,'type','monitor','flags','otherbss');created=True
        run('ip','link','set',monitor,'up')
        with socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3)) as raw:
            raw.bind((monitor,0));raw.settimeout(0.5)
            emit('CAPTURE_READY')
            end=time.monotonic()+args.seconds
            while time.monotonic()<end:
                try:packet=raw.recv(4096)
                except socket.timeout:continue
                if len(packet)<8 or packet[0]!=0:continue
                size=struct.unpack_from('<H',packet,2)[0]
                frame=packet[size:]
                if size<8 or len(frame)<40:continue
                if frame[0]==8 and len(frame)>=104 and frame[10:16]==bytes.fromhex('0002eec0ffee') and frame[16:22]==bssid and frame[4:10] in (source,bytes([source[0]^2])+source[1:]):
                    status=tx_metadata(packet)
                    if status is not None and frame[1]&0x40:
                        pn=int.from_bytes(frame[24:26]+frame[28:32],'little')
                        emit('TX_STATUS '+json.dumps(dict(pn=pn,hash=hashlib.sha256(frame[24:104]).hexdigest(),**status)))
                    continue
                if frame[0]!=8 or frame[10:16]!=source or frame[16:22]!=bssid:continue
                # Keep raw MPDU including possible FCS. Host checks either variant.
                if frame[1]&0x40:
                    frames.append(frame.hex());emit('FRAME '+frame.hex())
                elif frame[24:60]==bytes.fromhex('aaaa0300000088b5')+b'Pocket CCMP radio-path probe':
                    emit('PUBLIC_TRIGGER received')
                else:continue
                if replies and sender is None:
                    sender=threading.Thread(target=send_replies,args=(raw,),daemon=True);sender.start()
            if sender:sender.join(timeout=5)
            if sender and sender.is_alive():raise RuntimeError('Injection thread did not stop')
            if send_errors:raise RuntimeError('Injection failed')
    finally:
        if created:run('iw','dev',monitor,'del')
        emit('CAPTURE_DONE '+json.dumps(dict(frames=len(frames),monitor_removed=not os.path.exists('/sys/class/net/'+monitor))))


if __name__=='__main__':main()
