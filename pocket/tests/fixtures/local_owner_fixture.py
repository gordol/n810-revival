"""Original local lifecycle fixture. No serial, RNS, MeshCore or radio imports."""
import argparse
import os
from pathlib import Path
import signal
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'shell/vendor/apps/domains/reticulum'))
from owner import Owner, serve

parser = argparse.ArgumentParser()
for name in ('socket', 'state', 'station', 'ready-fd'): parser.add_argument('--' + name, required=True)
parser.add_argument('--block')
args = parser.parse_args()
def stop(*_): raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)

class Fixture(Owner):
    def snapshot(self):
        return dict(super().snapshot(), service_type='lifecycle-fixture', pid=os.getpid(),
                    radio_state='idle', capabilities=['connect', 'send'])
    def dispatch(self, request):
        if request.get('action') in ('connect', 'send'):
            with (Path(args.state) / 'actions').open('a') as stream:
                stream.write(request['action'] + '\n')
            return dict(version=1, accepted=True)
        return super().dispatch(request)

def factory(state, station):
    if args.block:
        Path(args.block).touch()
        signal.pause()
    return Fixture(state, station)
serve(args.socket, args.state, args.station, factory, ready_fd=int(args.ready_fd))
