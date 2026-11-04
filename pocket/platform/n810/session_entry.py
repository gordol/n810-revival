#!/usr/bin/python3 -I
"""Fixed normal-user desktop entry with optional detailed diagnostics."""
import datetime
import json
import os
from pathlib import Path
import runpy
import stat
import sys
import tempfile
import time

ASSETS = Path('/usr/local/share/n810-pocket')

def command():
    result = ['/usr/bin/python3', '-I', str(ASSETS / 'demo.py'),
            '--native', str(ASSETS / 'native/build-host/Linux-armv6l-cpython-311/_cellengine.abi3.so'),
            '--device-radio', '--native-stations', '--station-db',
            '/home/nokia/.local/state/n810-aprs/directory.sqlite3',
            '--touch-device', '/dev/input/n810-touch', '--touch-calibration',
            '/home/nokia/.local/state/current-world/touch-calibration.json',
            '--touch-display', '800x480', '--touch-rotation', '0']
    inherited = os.environ.get('N810_KEYBOARD_FD')
    if inherited is not None:
        if not inherited.isascii() or not inherited.isdecimal() or not 3<=int(inherited)<=65535:
            raise ValueError('Invalid inherited keyboard descriptor')
        info=os.fstat(int(inherited))
        if not stat.S_ISCHR(info.st_mode) or os.major(info.st_rdev)!=13 or not 64<=os.minor(info.st_rdev)<=255:
            raise ValueError('Inherited descriptor is not a Linux input device')
        result+=['--keyboard-fd',inherited]
    return result

def main():
    if os.geteuid()==0:raise SystemExit('Pocket must run as the normal user')
    if len(sys.argv)!=1:raise SystemExit('This session entry accepts no arguments')
    os.umask(0o077)
    state=Path('/home/nokia/.local/state/current-world')
    state.mkdir(mode=0o700,parents=True,exist_ok=True)
    diagnostics=state/'diagnostics.json'
    requested_metrics=None
    try:
        fd=os.open(diagnostics,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK|os.O_CLOEXEC)
    except FileNotFoundError:
        detailed_metrics=False
    except OSError as error:
        raise SystemExit('Cannot read diagnostics.json: '+str(error))
    else:
        try:
            with os.fdopen(fd,'rb') as stream:
                info=os.fstat(stream.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or info.st_mode&0o022:
                    raise ValueError('configuration must be a user-owned regular file without group or other write access')
                configuration=stream.read(1025)
            if len(configuration)>1024:raise ValueError('configuration exceeds 1024 bytes')
            configuration=json.loads(configuration)
            if not isinstance(configuration,dict) or set(configuration)!={'metrics'} or type(configuration['metrics']) is not bool:
                raise ValueError('expected {"metrics": true} or {"metrics": false}')
            requested_metrics=detailed_metrics=configuration['metrics']
        except (OSError,ValueError,UnicodeError) as error:
            raise SystemExit('Invalid diagnostics.json: '+str(error))
    runs=state/'console-runs';runs.mkdir(mode=0o700,exist_ok=True)
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ-')
    evidence=Path(tempfile.mkdtemp(prefix=stamp,dir=runs))
    engine=json.loads(Path('/usr/local/share/n810-pocket/build-info.json').read_text())['artifact_sha256']
    argv=command()[2:]+['--session',str(state/'session.json')]
    if detailed_metrics:argv+=['--metrics',str(evidence/'metrics.json')]
    (evidence/'launch.json').write_text(json.dumps(dict(engine_sha256=engine,session=str(state/'session.json'),evidence_directory=str(evidence),diagnostics=dict(requested_metrics=requested_metrics,effective_metrics=detailed_metrics)),indent=2)+'\n')
    sys.argv=argv;sys.path.insert(0,'/usr/local/share/n810-pocket');started=time.monotonic()
    try:
        runpy.run_path(sys.argv[0],run_name='__main__')
    except BaseException as error:
        code=error.code if isinstance(error,SystemExit) and type(error.code) is int else 1
        (evidence/'exit.json').write_text(json.dumps(dict(exit_code=code,error=type(error).__name__,elapsed_seconds=time.monotonic()-started))+'\n')
        raise
    else:
        (evidence/'exit.json').write_text(json.dumps(dict(exit_code=0,elapsed_seconds=time.monotonic()-started))+'\n')

if __name__=='__main__':main()
