"""Opt-in contact-scoped internet fill; positions are RAM-only and expire."""
import importlib.util
from pathlib import Path
import socket
import threading
import time
from aprs_internet import InternetEvidence,login,CALL


class Fill:
    def __init__(self,wakeup=None):
        self.wakeup=wakeup;self.stop=threading.Event();self.thread=None;self.socket=None
        self.lock=threading.Lock();self.positions={};self.status='Internet fill off';self.calls=();self.revision=0
    def publish(self,status=None):
        if status is not None:self.status=status
        self.revision+=1
        if self.wakeup:self.wakeup()
    def start(self,own,calls):
        self.close()
        calls=tuple(dict.fromkeys(c.upper() for c in calls if c))
        if not CALL.fullmatch(own) or not calls or len(calls)>32 or any(not CALL.fullmatch(c) for c in calls):raise ValueError('Enter own call and 1–32 contact calls, including SSIDs')
        self.calls=calls;self.stop=threading.Event();self.publish('Connecting · contacts only')
        self.thread=threading.Thread(target=self.run,args=(own,calls,self.stop),daemon=True,name='aprs-internet-fill');self.thread.start()
    def run(self,own,calls,stopped):
        spec=importlib.util.spec_from_file_location('fill_decode',Path(__file__).parent/'vendor/packet-console/n810-aprs-decode.py')
        decode=importlib.util.module_from_spec(spec);spec.loader.exec_module(decode)
        path=Path.home()/'.local/state/pocket/aprs-internet.sqlite3';path.parent.mkdir(parents=True,exist_ok=True)
        store=InternetEvidence(path);store.expire()
        try:
            with socket.create_connection(('rotate.aprs2.net',14580),timeout=8) as sock:
                if stopped.is_set():return
                self.socket=sock;sock.settimeout(30)
                names='/'.join(dict.fromkeys((own,)+calls))
                sock.sendall(login(own,'b/'+names+' g/'+names).encode('ascii'));self.publish('Connected · listed calls only · RX only')
                buffer=bytearray();expiry_due=time.monotonic()+60
                while not stopped.is_set():
                    if time.monotonic()>=expiry_due:
                        store.expire();expiry_due=time.monotonic()+60
                    try:block=sock.recv(4096)
                    except socket.timeout:store.expire();continue
                    if not block:raise OSError('Internet feed disconnected')
                    buffer.extend(block)
                    if len(buffer)>16384:raise ValueError('Internet feed buffer exceeded')
                    while b'\n' in buffer:
                        line,_,tail=buffer.partition(b'\n');buffer=bytearray(tail)
                        try:
                            text=line.decode('ascii').rstrip('\r')
                            if not text or text.startswith('#'):continue
                            header,sep,payload=text.partition(':');source,_,route=header.partition('>')
                            recipient=payload[1:10].strip() if payload.startswith(':') and len(payload)>10 and payload[10]==':' else ''
                            if source not in calls+(own,) and recipient not in calls+(own,):continue
                            store.ingest(text)
                            if source in calls:
                                pos=decode.decode(payload,route.split(',')[0]).get('position')
                                if pos:
                                    with self.lock:self.positions[source]=(pos,time.monotonic())
                            self.publish()
                        except (ValueError,UnicodeDecodeError):continue
        except (OSError,ValueError) as error:
            if not stopped.is_set():self.publish('Internet fill: '+str(error)+' · toggle off/on to reconnect')
        finally:self.socket=None;store.close()
    def snapshot(self):
        with self.lock:
            self.positions={c:v for c,v in self.positions.items() if time.monotonic()-v[1]<1800}
            return {c:v[0] for c,v in self.positions.items()}
    def close(self):
        self.stop.set()
        if self.socket:
            try:self.socket.shutdown(socket.SHUT_RDWR)
            except OSError:pass
        if self.thread:self.thread.join(timeout=.2)
        self.thread=None
        with self.lock:self.positions.clear()
        self.publish('Internet fill off')
