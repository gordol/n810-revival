"""Read-only KISS provisioning probe; works on the N810 with stdlib alone."""
import argparse,json,socket,time
p=argparse.ArgumentParser();p.add_argument('--bluetooth');p.add_argument('--serial');p.add_argument('--hold',type=float,default=0);args=p.parse_args()
if args.bluetooth:
    port=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM)
    port.settimeout(15);port.connect((args.bluetooth,1))
    print('RFCOMM connected',file=__import__('sys').stderr,flush=True)
    send=port.sendall;read=port.recv
else:
    import serial
    port=serial.Serial(args.serial,115200,timeout=.2)
    time.sleep(4);port.reset_input_buffer();send=port.write;read=port.read
# MsgPack [GET_INFO,1,nil], [GET_STATE,2,{NamespaceFilter:[1,107,104]}].
queries=['930201c0','930402810193016b68']
responses=[];buf=bytearray();inside=False;escape=False
for seq,query in enumerate(queries,1):
    raw=bytes.fromhex(query);send(b'\xc0\x86'+raw.replace(b'\xdb',b'\xdb\xdd').replace(b'\xc0',b'\xdb\xdc')+b'\xc0')
    deadline=time.monotonic()+20;got=False
    while time.monotonic()<deadline and not got:
        try:data=read(4096)
        except socket.timeout:continue
        for b in data:
            if b==192:
                if inside and buf and buf[0]==135:
                    responses.append(bytes(buf[1:]).hex());got=True
                buf.clear();inside=True;escape=False
            elif inside:
                if b==219:escape=True;continue
                if escape:b={220:192,221:219}.get(b,b);escape=False
                if len(buf)<65536:buf.append(b)
    if not got:raise SystemExit('No provisioning response for query '+str(seq))
time.sleep(args.hold)
port.close();print(json.dumps({'transport':'rfcomm' if args.bluetooth else 'usb','responses':responses}))
