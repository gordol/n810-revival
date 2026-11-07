# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native serial carrier through the actual session provider and owner process."""
import os
from pathlib import Path
import pty
import sys
import tempfile
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell'))
from app_registry import Registry


def wait(provider,predicate):
    until=time.monotonic()+20
    while time.monotonic()<until:
        state=provider.snapshot()
        if predicate(state):return state
        time.sleep(.02)
    raise AssertionError(state)


def main():
    master,slave=pty.openpty()
    try:
        with tempfile.TemporaryDirectory(prefix='native-serial-owner-',dir='/tmp') as root:
            options=dict(station='fixture',interpreter=sys.executable,
                         carriers=[dict(type='kiss' if '--kiss' in sys.argv else 'serial',port=os.ttyname(slave),speed=9600)])
            registry=Registry()
            owner=registry.configure_reticulum(local_state=root,local_options=options,register=False)
            try:
                state=wait(owner,lambda s:s.get('owner_online'))
                assert state['radio_state']=='idle',state
                owner.request('connect',dict(station='fixture',radio='carriers'))
                state=wait(owner,lambda s:s.get('radio_state')=='online')
                assert state['backend']=='native-microreticulum',state
            finally:
                owner.close()
                process=owner.transport.process
                if process and process.poll() is None:process.terminate();process.wait(15)
            assert process.returncode==0,process.returncode
            assert not Path(owner.path).exists()
            print('PASS: session provider starts serial owner idle; explicit connect uses native backend; close releases owner')
    finally:
        os.close(master);os.close(slave)

if __name__=='__main__':main()
