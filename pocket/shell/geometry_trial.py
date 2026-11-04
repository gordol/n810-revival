# SPDX-License-Identifier: MIT
"""Opt-in geometry compute trial; forward the existing desktop arguments unchanged."""
import argparse
import json
from pathlib import Path
import runpy
import sys
import time
import geometry_compute

def main(argv=None):
    parser=argparse.ArgumentParser(add_help=False,allow_abbrev=False)
    parser.add_argument('--compute-library',type=Path)
    parser.add_argument('--compute-receipt',type=Path)
    args,remaining=parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    if args.compute_receipt is not None and args.compute_receipt.exists():
        raise FileExistsError('compute receipt already exists')
    state=geometry_compute.configure(args.compute_library)
    if args.compute_library is not None and state['backend'] not in ('native-vfp','native-soft'):
        raise RuntimeError('requested compute backend unavailable: '+str(state))
    receipt=dict(started_at=time.time(),requested_library=str(args.compute_library) if args.compute_library else None,
                 available_backend=state,desktop_arguments=list(remaining),state='running')
    def save():
        if args.compute_receipt is not None:
            args.compute_receipt.write_text(json.dumps(receipt,indent=2)+'\n')
    save()
    original=sys.argv
    desktop=Path(__file__).with_name('demo.py')
    code=0
    try:
        sys.argv=[str(desktop),*remaining]
        runpy.run_path(str(desktop),run_name='__main__')
    except SystemExit as error:
        code=error.code if isinstance(error.code,int) else 0 if error.code is None else 1
        raise
    except BaseException:
        code=1
        raise
    finally:
        sys.argv=original
        used=geometry_compute.status()
        actual=[]
        if used.get('native_points',0):actual.append(used['backend'])
        if used.get('python_points',0):actual.append('python-batch')
        if used.get('reference_fallback_points',0):actual.append('python-reference')
        receipt.update(state='finished',finished_at=time.time(),exit_code=code,
                       used_backend=used,actual_backends=actual)
        save()

if __name__=='__main__':main()
