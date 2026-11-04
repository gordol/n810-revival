#!/usr/bin/env python3
"""Bounded receive-only UV-Pro SBC audio trial; no Bluetooth send operations."""
import argparse
import base64
import ctypes as c
import ctypes.util
import json
import os
import resource
from pathlib import Path
import signal
import socket
import sys
import time
import uuid


class SBCState(c.Structure):
    _fields_=[('flags',c.c_ulong),('frequency',c.c_uint8),('blocks',c.c_uint8),('subbands',c.c_uint8),
              ('mode',c.c_uint8),('allocation',c.c_uint8),('bitpool',c.c_uint8),('endian',c.c_uint8),
              ('priv',c.c_void_p),('priv_alloc_base',c.c_void_p)]


class Decoder:
    def __init__(self,path=None):
        name=path or ctypes.util.find_library('sbc')
        if not name:raise RuntimeError('libsbc not installed; no codec or Bluetooth opened')
        self.lib=c.CDLL(name)
        self.lib.sbc_init.argtypes=[c.POINTER(SBCState),c.c_ulong];self.lib.sbc_init.restype=c.c_int
        self.lib.sbc_decode.argtypes=[c.POINTER(SBCState),c.c_void_p,c.c_size_t,c.c_void_p,c.c_size_t,c.POINTER(c.c_size_t)]
        self.lib.sbc_decode.restype=c.c_ssize_t
        self.lib.sbc_reinit.argtypes=[c.POINTER(SBCState),c.c_ulong];self.lib.sbc_reinit.restype=c.c_int
        self.lib.sbc_finish.argtypes=[c.POINTER(SBCState)];self.lib.sbc_finish.restype=None
        self.state=SBCState()
        if self.lib.sbc_init(c.byref(self.state),0)!=0:raise RuntimeError('libsbc init failed')
        self.state.endian=0;self.closed=False
    def decode(self,frame):
        output=c.create_string_buffer(4096);written=c.c_size_t()
        used=self.lib.sbc_decode(c.byref(self.state),frame,len(frame),output,len(output),c.byref(written))
        if used!=len(frame) or not 0<written.value<=len(output):raise ValueError('SBC decode rejected frame')
        return output.raw[:written.value]
    def reset(self):
        if self.lib.sbc_reinit(c.byref(self.state),0)!=0:raise ValueError('SBC reset failed')
        self.state.endian=0
    def close(self):
        if not self.closed:self.lib.sbc_finish(c.byref(self.state));self.closed=True


def sbc_header(raw):
    if len(raw)<4:return None
    if raw[0]!=0x9c:raise ValueError('Only standard SBC supported for this bounded trial')
    value=raw[1];rate=(16000,32000,44100,48000)[value>>6];blocks=(4,8,12,16)[(value>>4)&3]
    mode=(value>>2)&3;channels=1 if mode==0 else 2;subbands=8 if value&1 else 4;pool=raw[2]
    if not 2<=pool<=250:raise ValueError('Invalid SBC bitpool')
    if pool>(16 if mode in (0,1) else 32)*subbands:raise ValueError('SBC bitpool outside frame limits')
    audio_bits=blocks*channels*pool if mode in (0,1) else blocks*pool+(subbands if mode==3 else 0)
    size=4+(4*subbands*channels)//8+(audio_bits+7)//8
    return dict(rate=rate,channels=channels,samples=blocks*subbands,size=size)


class AudioFrames:
    def __init__(self):self.data=bytearray();self.active=False;self.escape=False;self.dropped=0
    def feed(self,chunk):
        out=[]
        for value in chunk:
            if value==0x7e:
                if self.active and self.data and not self.escape:out.append((self.data[0],bytes(self.data[1:])))
                elif self.escape:self.dropped+=1
                self.data.clear();self.active=True;self.escape=False
            elif self.active:
                if self.escape:
                    if value not in (0x5d,0x5e):
                        self.dropped+=1;self.active=False;self.data.clear()
                    else:self.data.append(value^0x20)
                    self.escape=False
                elif value==0x7d:self.escape=True
                else:self.data.append(value)
                if len(self.data)>65536:self.dropped+=1;self.data.clear();self.active=False
        return out


class Pipeline:
    def __init__(self,decoder,emit,receiver_id):
        self.decoder=decoder;self.emit=emit;self.receiver_id=receiver_id;self.format=None;self.source_stream=None
        self.frames=AudioFrames();self.rx_frames=0;self.tx_echo_frames=0;self.decoded_samples=0;self.sbc_frames=0;self.reset('start')
    def reset(self,reason):
        self.stream=uuid.uuid4().hex;self.seq=0;self.first=0;self.sbc=bytearray();self.pcm=bytearray();self.rate=None;self.origin=None;self.format=None
        if self.decoder is not None and hasattr(self.decoder,'reset'):self.decoder.reset()
        self.emit(dict(type='gap',reason=reason,stream_id=self.stream,source_stream_id=self.source_stream,receiver_id=self.receiver_id,audio_retained=False))
    def decode_frame(self,frame,info,now_ns):
        if info['channels']!=1:raise ValueError('Stereo source not silently downmixed')
        if self.rate is None:
            self.rate=info['rate'];self.origin=now_ns
            self.format=dict(type='format' if self.decoder is not None else 'encoded_format',stream_id=self.stream,
                             source_stream_id=self.source_stream,sample_rate=self.rate,encoding='s16le' if self.decoder is not None else 'sbc',channels=1,
                             codec='sbc',receiver_id=self.receiver_id,direction='rx',clock_domain='receiver_owner_monotonic',
                             time_basis='receipt_anchor_estimate_plus_sample_count',capture_time_known=False,clock_uncertainty_ns=None,
                             channel=None,receiver_position=None,audio_retained=False)
            self.emit(self.format)
        elif self.rate!=info['rate']:raise ValueError('Source rate changed')
        self.sbc_frames+=1
        if self.decoder is None:
            self.emit(dict(type='sbc',stream_id=self.stream,sequence=self.seq,first_sample=self.first,
                           sample_count=info['samples'],sample_rate=self.rate,channels=1,receiver_id=self.receiver_id,direction='rx',
                           owner_received_monotonic_ns=now_ns,sbc_b64=base64.b64encode(frame).decode()))
            self.seq+=1;self.first+=info['samples'];return
        pcm=self.decoder.decode(frame)
        if len(pcm)!=info['samples']*2:raise ValueError('Decoded sample count mismatch')
        self.decoded_samples+=info['samples']
        self.pcm.extend(pcm);count=self.rate//50;size=count*2
        while len(self.pcm)>=size:
            block=bytes(self.pcm[:size]);del self.pcm[:size]
            self.emit(dict(type='pcm',stream_id=self.stream,source_stream_id=self.source_stream,sequence=self.seq,first_sample=self.first,
                           sample_count=count,sample_rate=self.rate,encoding='s16le',channels=1,direction='rx',
                           capture_monotonic_ns=None,sample_monotonic_ns_estimate=self.origin+round(self.first*1000000000/self.rate),
                           capture_time_known=False,clock_uncertainty_ns=None,owner_received_monotonic_ns=now_ns,
                           receiver_id=self.receiver_id,pcm_b64=base64.b64encode(block).decode()))
            self.seq+=1;self.first+=count
    def feed(self,data,now_ns=None):
        now_ns=time.monotonic_ns() if now_ns is None else now_ns;dropped=self.frames.dropped
        for kind,payload in self.frames.feed(data):
            if kind==9:self.tx_echo_frames+=1;continue
            if kind==1:self.reset('audio_end');continue
            if kind not in (0,3):continue
            self.rx_frames+=1;self.sbc.extend(payload)
            if len(self.sbc)>65536:self.reset('sbc_accumulator_overflow');continue
            while len(self.sbc)>=4:
                try:
                    info=sbc_header(self.sbc)
                    if len(self.sbc)<info['size']:break
                    frame=bytes(self.sbc[:info['size']]);del self.sbc[:info['size']]
                    self.decode_frame(frame,info,now_ns)
                except ValueError as exc:self.reset(str(exc));break
        if self.frames.dropped!=dropped:self.reset('audio_framing_discontinuity')


class EncodedInput:
    def __init__(self,pipeline):self.pipeline=pipeline;self.pending=bytearray();self.stream=None;self.next_sequence=None;self.next_sample=None
    def feed(self,data):
        self.pending.extend(data)
        if len(self.pending)>65536:self.pending.clear();self.pipeline.reset('input_overflow');return
        while b'\n' in self.pending:
            line,_,rest=self.pending.partition(b'\n');self.pending=bytearray(rest)
            try:
                event=json.loads(line)
                if not isinstance(event,dict):raise ValueError('Audio event must be an object')
                if event.get('type')=='gap':
                    self.pipeline.source_stream=event.get('stream_id');self.pipeline.reset(event.get('reason','source_gap'))
                    self.stream=event.get('stream_id');self.next_sequence=None;self.next_sample=None;continue
                if event.get('type')!='sbc':continue
                if event.get('direction')!='rx':raise ValueError('Non-RX input rejected')
                if event.get('stream_id')!=self.stream or (self.next_sequence is not None and (event['sequence']!=self.next_sequence or event['first_sample']!=self.next_sample)):
                    self.stream=event.get('stream_id');self.pipeline.source_stream=self.stream;self.pipeline.reset('source_reset_or_gap')
                if any(type(event.get(k)) is not int or event[k]<0 for k in ('sequence','first_sample','owner_received_monotonic_ns')):raise ValueError('Invalid sample/sequence/clock metadata')
                frame=base64.b64decode(event['sbc_b64'],validate=True);info=sbc_header(frame)
                if info is None or info['size']!=len(frame) or info['rate']!=event.get('sample_rate') or info['samples']!=event.get('sample_count'):raise ValueError('Encoded metadata/header mismatch')
                self.pipeline.decode_frame(frame,info,event['owner_received_monotonic_ns'])
                self.next_sequence=event['sequence']+1;self.next_sample=event['first_sample']+info['samples']
                self.pipeline.rx_frames+=1
            except (ValueError,KeyError,TypeError) as exc:self.pipeline.reset(str(exc));self.next_sequence=None;self.next_sample=None


def run(args):
    if not 1<=args.duration<=120:raise ValueError('Trial duration must be1..120seconds')
    decoder=None if args.encoded_only else Decoder(args.libsbc)
    path=Path(args.socket)
    if os.path.lexists(path):
        if decoder:decoder.close()
        raise ValueError('Refusing existing audio socket path')
    server=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    radio=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) if args.input_socket else socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM)
    bound=None
    clients={};stopped=False;stats={'type':'status','state':'starting','audio_retained':False,'bt_bytes':0,'source_bytes':0}
    def emit(value):
        encoded=json.dumps(value,separators=(',',':')).encode()+b'\n'
        for client in list(clients):
            if len(clients[client])+len(encoded)>131072:
                client.close();del clients[client] # reconnect = new format/gap, no backlog replay
            else:clients[client].extend(encoded)
    def stop(*_):
        nonlocal stopped
        stopped=True
    for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,stop)
    try:
        server.bind(str(path));bound=path.lstat().st_ino;os.chmod(path,0o600);server.listen(4);server.setblocking(False)
        if args.wait_for_consumer:
            import select
            ready_deadline=time.monotonic()+60
            while not stopped:
                if time.monotonic()>=ready_deadline:raise RuntimeError('No consumer attached within 60 seconds')
                if select.select([server],[],[],.1)[0]:
                    client,_=server.accept();client.setblocking(False);clients[client]=bytearray()
                    break
            if stopped:return
        radio.settimeout(8);radio.connect(args.input_socket if args.input_socket else (args.address,args.channel));radio.setblocking(False)
        stats['state']='connected';pipeline=Pipeline(decoder,emit,args.receiver_id)
        audio_input=EncodedInput(pipeline) if args.input_socket else pipeline
        started=time.monotonic();cpu_started=resource.getrusage(resource.RUSAGE_SELF);end=started+args.duration;last_status=0
        import select
        while not stopped and time.monotonic()<end:
            readable,writable,_=select.select([server,radio,*clients],[c for c,v in clients.items() if v],[],.1)
            for source in readable:
                if source is server:
                    client,_=server.accept();client.setblocking(False);clients[client]=bytearray()
                    if len(clients)>4:client.close();del clients[client];continue
                    clients[client].extend((json.dumps(stats)+'\n').encode())
                    if pipeline.format:clients[client].extend((json.dumps(pipeline.format)+'\n').encode())
                elif source is radio:
                    data=radio.recv(8192)
                    if not data:
                        stats['state']='source_closed' if args.input_socket else 'radio_closed';stopped=True;break
                    stats['source_bytes']+=len(data)
                    if not args.input_socket:stats['bt_bytes']+=len(data)
                    audio_input.feed(data)
                else:
                    # Input is never forwarded; this stream is receive-only.
                    source.close();del clients[source]
            for client in writable:
                if client not in clients:continue
                try:n=client.send(clients[client]);del clients[client][:n]
                except (BlockingIOError,BrokenPipeError,ConnectionResetError):client.close();del clients[client]
            if time.monotonic()-last_status>=1:
                stats.update(rx_audio_frames=pipeline.rx_frames,sbc_frames=pipeline.sbc_frames,decoded_samples=pipeline.decoded_samples,tx_echo_ignored=pipeline.tx_echo_frames,framing_gaps=pipeline.frames.dropped)
                emit(stats);last_status=time.monotonic()
        usage=resource.getrusage(resource.RUSAGE_SELF)
        stats.update(elapsed_seconds=time.monotonic()-started,cpu_seconds=usage.ru_utime+usage.ru_stime-cpu_started.ru_utime-cpu_started.ru_stime,max_rss=usage.ru_maxrss,max_rss_unit='bytes' if sys.platform=='darwin' else 'KiB')
        stats.update(trial_finished=True,rx_audio_frames=pipeline.rx_frames,sbc_frames=pipeline.sbc_frames,decoded_samples=pipeline.decoded_samples,tx_echo_ignored=pipeline.tx_echo_frames)
        print(json.dumps(stats),flush=True)
    finally:
        # Never call send/sendall on Bluetooth, including cleanup. Local close only.
        for client in clients:client.close()
        radio.close();server.close()
        if decoder:decoder.close()
        if bound is not None and path.exists() and path.lstat().st_ino==bound:path.unlink()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--address');p.add_argument('--channel',type=int);p.add_argument('--input-socket');p.add_argument('--encoded-only',action='store_true')
    p.add_argument('--socket',default='/dev/shm/n810-audio-rx.sock');p.add_argument('--duration',type=float,default=30)
    p.add_argument('--receiver-id',required=True);p.add_argument('--libsbc');p.add_argument('--wait-for-consumer',action='store_true',help='Wait up to 60 seconds for a local consumer before connecting upstream and starting the trial')
    args=p.parse_args()
    if not args.input_socket and (not args.address or args.channel is None or not 1<=args.channel<=30):p.error('Verified audio address/channel or forwarded input socket required')
    if args.input_socket and args.encoded_only:p.error('Forwarded input is for one shared decoder, not encoded passthrough')
    try:run(args)
    except (OSError,ValueError,RuntimeError) as exc:print('RX audio unavailable: '+str(exc),file=sys.stderr);raise SystemExit(1)
