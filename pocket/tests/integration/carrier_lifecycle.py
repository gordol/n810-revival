"""Real idle/activate/borrow/stop lifecycle using the shell's carrier provider."""
from pathlib import Path
import socket
import sys
import tempfile
import time

sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell'))
from app_registry import Registry


def main():
    def wait(predicate):
        deadline=time.monotonic()+120
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.02)
        raise AssertionError('Carrier lifecycle timed out')
    with tempfile.TemporaryDirectory(prefix='carrier-test-',dir='/tmp') as root:
        probe=socket.socket();probe.bind(('127.0.0.1',0));port=probe.getsockname()[1];probe.close()
        options=dict(station='test',interpreter=sys.executable,carriers=[dict(type='tcp-server',host='127.0.0.1',port=port)])
        registry=Registry();owner=registry.configure_reticulum(local_state=root,local_options=options,register=False)
        try:
            wait(lambda:owner.snapshot().get('owner_online'))
            assert owner.snapshot()['radio_state']=='idle'
            with socket.socket() as client:assert client.connect_ex(('127.0.0.1',port))!=0,'Selecting carrier opened its interface'
            borrowed=registry.configure_reticulum(local_state=root,local_options=options,register=False)
            borrowed.close();assert owner.transport.process.poll() is None,'Borrower stopped shared owner'
            owner.request('connect',dict(station='test',radio='carriers'))
            wait(lambda:owner.snapshot().get('radio_state') in ('online','listening'))
            with socket.socket() as client:assert client.connect_ex(('127.0.0.1',port))==0
            assert owner.snapshot()['service_security']=='authenticated-encrypted'
        finally:
            owner.close()
            process=owner.transport.process
            if process and process.poll() is None:process.terminate();process.wait(15)
        assert owner.transport.process.returncode==0
        assert not Path(owner.path).exists()
        with socket.socket() as client:assert client.connect_ex(('127.0.0.1',port))!=0,'Closed owner retained listener'
        print('PASS: selection idle; explicit Connect; borrowing preserves shared owner; explicit service stop removes socket and listener')

if __name__=='__main__':main()
