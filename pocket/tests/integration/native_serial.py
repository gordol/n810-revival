# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native serial framing against stock RNS through bridged pseudo terminals."""
import os
from pathlib import Path
import pty
import select
import sys
import threading
import time
import tempfile
import RNS
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from native_radio import SerialPackets,KISSPackets
from RNS.Interfaces.SerialInterface import SerialInterface
from RNS.Interfaces.KISSInterface import KISSInterface


def main():
    kiss='--kiss' in sys.argv
    adapter=KISSPackets if kiss else SerialPackets
    stock_adapter=KISSInterface if kiss else SerialInterface
    config=tempfile.TemporaryDirectory(prefix='native-serial-rns-')
    Path(config.name,'config').write_text('[reticulum]\nshare_instance = No\n[interfaces]\n')
    stack=RNS.Reticulum(configdir=config.name)
    left,left_slave=pty.openpty();right,right_slave=pty.openpty()
    wake,stop_write=os.pipe();native=stock=None
    def bridge():
        while True:
            ready,_,_=select.select([left,right,wake],[],[])
            if wake in ready:return
            for source,target in ((left,right),(right,left)):
                if source in ready:os.write(target,os.read(source,4096))
    worker=threading.Thread(target=bridge,daemon=True);worker.start()
    native_packets=[];stock_packets=[]
    try:
        native=adapter(dict(port=os.ttyname(left_slave),speed=9600),native_packets.append,lambda event:None)
        stock=stock_adapter(SimpleNamespace(inbound=lambda data,interface:stock_packets.append(data)),
                              dict(name='test',port=os.ttyname(right_slave),speed=9600))
        assert stock.online and native.online
        payload=b'wire interoperability '+bytes(range(256))
        native.send(payload);stock.process_outgoing(payload[::-1])
        until=time.monotonic()+5
        while (not native_packets or not stock_packets) and time.monotonic()<until:time.sleep(.01)
        assert stock_packets==[payload],stock_packets
        assert native_packets==[payload[::-1]],native_packets
        print('PASS: native and stock RNS', 'KISS' if kiss else 'serial', 'adapters exchange escaped binary packets in both directions; pseudo terminals only')
    finally:
        if stock:stock.detach()
        if native:native.close()
        os.write(stop_write,b'x');worker.join(2)
        for fd in (left,left_slave,right,right_slave,wake,stop_write):os.close(fd)
        stack.exit_handler();config.cleanup()

if __name__=='__main__':main()
