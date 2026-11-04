"""Exercise the official client against a binary companion emulator; no radio TX."""
import asyncio
import importlib.util
from pathlib import Path
import socket
import struct
import sys
import tempfile
import threading
import time

ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('mesh_owner',ROOT/'shell/vendor/apps/domains/meshcore/owner.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from meshcore import MeshCore


def main():
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();port=listener.getsockname()[1]
    peer=b'a'*32;local=b'b'*32;commands=[];stopped=threading.Event();errors=[]
    def emulator():
        try:
            with listener.accept()[0] as client:
                def send(raw):
                    frame=b'>'+len(raw).to_bytes(2,'little')+raw
                    # Fragment headers and bodies deliberately.
                    for i in range(0,len(frame),7):client.sendall(frame[i:i+7])
                stream=client.makefile('rb');received=False
                while not stopped.is_set():
                    header=stream.read(3)
                    if not header:break
                    assert header[0]==60
                    raw=stream.read(int.from_bytes(header[1:],'little'));commands.append(raw)
                    op=raw[0]
                    if op==1:send(b'\x05\x01\x0a\x14'+local+b'\0'*12+struct.pack('<II',915000,125000)+b'\x07\x05Fixture')
                    elif op==4:
                        send(b'\x02'+struct.pack('<I',1))
                        send(b'\x03'+peer+b'\x01\x00\xff'+b'\0'*64+b'Alice'.ljust(32,b'\0')+b'\0'*16)
                        send(b'\x04'+b'\0'*4)
                    elif op==22:send(b'\x0d\x03\x01\x01'+b'\0'*(4+12+40+20))
                    elif op==31:send(b'\x12\x00'+b'Public'.ljust(32,b'\0')+bytes.fromhex('8b3387e9c5cdea6ac9e5edbaa115cd72'))
                    elif op==10:
                        if not received:
                            send(b'\x10\x00\x00\x00'+peer[:6]+b'\xff\x00'+struct.pack('<I',1234)+b'hello from Alice');received=True
                        else:send(b'\x0a')
                    elif op in (2,3):
                        send(b'\x06\x00abcd'+struct.pack('<I',1000)) if op==2 else send(b'\x00')
                        if op==2:send(b'\x82abcd'+struct.pack('<I',10))
                    else:raise AssertionError('Unexpected command '+str(op))
        except Exception as error:errors.append(repr(error))
    worker=threading.Thread(target=emulator,daemon=True);worker.start()
    async def factory(*args,**kwargs):return await MeshCore.create_tcp('127.0.0.1',port,auto_reconnect=False,default_timeout=2)
    with tempfile.TemporaryDirectory(prefix='mesh-chat-',dir='/tmp') as root:
        owner=module.MeshOwner(root,'test','/dev/test',trusted_peripheral=True,client_factory=factory)
        def wait(predicate):
            deadline=time.monotonic()+20
            while time.monotonic()<deadline:
                owner.drain()
                if predicate():return
                time.sleep(.01)
            raise AssertionError(str(owner.snapshot())+' emulator='+str(errors))
        def request(action,**payload):return owner.dispatch(dict(version=1,action=action,request_id=action+'-id',payload=payload))
        try:
            assert not commands,'Owner startup touched radio'
            request('connect');wait(lambda:owner.online and len(owner.messages)==1)
            assert owner.channels[0]['privacy']=='public'
            assert 'secret' not in repr(owner.snapshot())
            try:request('send',peer=peer.hex(),text='denied')
            except ValueError:pass
            else:raise AssertionError('Unverified send accepted')
            request('verify_peer',peer=peer.hex(),fingerprint=peer.hex())
            request('send',peer=peer.hex(),text='private reply')
            wait(lambda:any(r['id']=='send-id' and r['state']=='acknowledged' for r in owner.messages))
            request('send_channel',channel=0,text='public reply')
            wait(lambda:any(r['id']=='send_channel-id' and r['state']=='sent; no group receipt' for r in owner.messages))
            assert len([r for r in commands if r[0]==2])==1
            assert len([r for r in commands if r[0]==3])==1
            assert not any(r[0] in (6,7,9,11,12,23,24,32) for r in commands),'Unexpected radio mutation/advertisement'
            request('disconnect');wait(lambda:owner.phase=='idle')
        finally:owner.close();stopped.set();listener.close();worker.join(3)
        assert not errors,errors
        assert Path(root,'chat.msgpack').read_bytes().startswith(b'PS\x02')
        restored=module.MeshOwner(root,'test','/dev/test')
        try:assert len(restored.messages)==3 and peer.hex() in restored.pins
        finally:restored.close()
    print('PASS: official MeshCore binary client; RX; verified DM/ACK; channel send; no automatic TX/settings writes; private binary persistence; clean disconnect')

if __name__=='__main__':main()
