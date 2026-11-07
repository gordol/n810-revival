"""Idle owner for explicit RNS carriers. Connect activates them; process exit closes them."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import tempfile

from carriers import configuration,validate_native
from lxmf_owner import LXMFBackend
from owner import serve


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('socket','state','station','carriers'):parser.add_argument('--'+name,required=True)
    parser.add_argument('--relay',action='store_true')
    parser.add_argument('--ready-fd',type=int)
    args=parser.parse_args()
    specs=json.loads(args.carriers);config=configuration(specs,args.relay)
    digest=hashlib.sha256(config.encode()).hexdigest()
    def stop(signum,frame):
        signal.signal(signal.SIGTERM,signal.SIG_IGN)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM,stop)
    # The provider owns this private runtime directory. A second instance never
    # overwrites an active owner's configuration.
    with tempfile.TemporaryDirectory(prefix='config-',dir=Path(args.socket).parent) as directory:
        path=Path(directory)/'config'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as stream:stream.write(config)
        from native_owner import selected_backend,NativeBackend
        backend=selected_backend('loopback')
        if backend is NativeBackend:validate_native(specs,args.relay)
        class CarrierOwner(backend):
            def snapshot(self):
                state=super().snapshot()
                state.update(service_type='reticulum-carrier',carrier_config_sha256=digest,
                             carriers=specs,service_security='authenticated-encrypted')
                return state
        def factory(state,station):return CarrierOwner(state,station,directory,'carriers','carriers')
        serve(args.socket,args.state,args.station,factory,ready_fd=args.ready_fd)


if __name__=='__main__':main()
