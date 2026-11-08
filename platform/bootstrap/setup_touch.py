#!/usr/bin/env python3
"""Set up Pocket touch on the tablet's text console using existing platform tools."""
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import argparse
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'touch-runtime'))
from touch_evdev import Calibration, EventReader, display


def from_pointercal(text, device):
    values = text.split()
    if len(values) != 7:
        raise ValueError('Expected seven integer tslib coefficients')
    a,b,c,d,e,f,scale = map(int, values)
    if scale == 0:
        raise ValueError('Zero calibration divisor')
    return from_pixels([a/scale,b/scale,c/scale,d/scale,e/scale,f/scale], device)


def from_pixels(coefficients, device):
    a,b,c,d,e,f = coefficients
    xmin,xmax = device['x_range']; ymin,ymax = device['y_range']
    matrix = [a*(xmax-xmin)/800,b*(ymax-ymin)/800,(a*xmin+b*ymin+c)/800,
              d*(xmax-xmin)/480,e*(ymax-ymin)/480,(d*xmin+e*ymin+f)/480]
    profile = dict(version=1,device=device,display=display(800,480),matrix=matrix)
    calibration = Calibration(profile,device,display(800,480))
    u,v = calibration.normalized((xmin+xmax)/2,(ymin+ymax)/2)
    if not all(math.isfinite(x) and -.25 <= x <= 1.25 for x in (u,v)):
        raise ValueError('Calibration center lies outside this display')
    return profile


def save(profile, output):
    output.parent.mkdir(parents=True,exist_ok=True)
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(profile,indent=2)+'\n')
    temporary.chmod(0o644)
    os.replace(temporary,output)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--recalibrate',action='store_true')
    parser.add_argument('--pointercal',type=Path)
    args=parser.parse_args()
    output=Path('/etc/n810/touch-calibration.json')
    reader=None
    for path in sorted(Path('/dev/input').glob('event*')):
        try:
            candidate=EventReader(path)
            if candidate.device['name']=='TSC2005 touchscreen':reader=candidate;break
            candidate.close()
        except (OSError,ValueError):continue
    if reader is None:
        print('Touchscreen unavailable; run sudo n810-setup-touch when it is ready.')
        return
    device=reader.device;reader.close()
    if output.exists() and not args.recalibrate:
        try:Calibration.load(output,device,display(800,480));return
        except (ValueError,OSError):pass
    candidates=[args.pointercal] if args.pointercal else [Path('/etc/pointercal'),Path('/mnt/maemo/etc/pointercal'),Path('/media/maemo/etc/pointercal')]
    if not args.recalibrate:
        for path in candidates:
            try:
                if not path.exists():continue
                if path.stat().st_size>4096:raise ValueError('Calibration file too large')
                profile=from_pointercal(path.read_text(),device)
                with tempfile.NamedTemporaryFile(mode='w') as mapping:
                    # The historical pointer preview takes pixel coefficients.
                    values=list(map(int,path.read_text().split()));scale=values[-1]
                    mapping.write(' '.join(str(v/scale) for v in values[:6]));mapping.flush()
                    print('Move the stylus over the targets to check the saved Maemo mapping.',flush=True)
                    process=subprocess.Popen([str(HERE/'n810-touch-calibrate'),'--pointer',mapping.name])
                    try:
                        input('Press Enter to finish the pointer preview: ')
                        status=process.poll()
                        if status is not None and status!=0:
                            raise ValueError('Pointer preview could not run on this display')
                    finally:
                        if process.poll() is None:process.terminate()
                        process.wait()

                if input('Did the pointer follow the stylus accurately? [y/N] ').strip().lower()=='y':
                    save(profile,output);return
            except (OSError,ValueError,subprocess.CalledProcessError) as error:
                print('Saved touch mapping unavailable: '+str(error))
    print('Touch setup: tap each of the five white crosses. Use the keyboard to continue.',flush=True)
    if input('Press Enter to calibrate, or type skip for a later login: ').strip().lower()=='skip':return
    with tempfile.TemporaryDirectory(prefix='n810-touch-') as tmp:
        targets=Path(tmp)/'targets.csv'
        subprocess.run([str(HERE/'n810-touch-calibrate'),str(targets)],check=True)
        result=subprocess.check_output([sys.executable,str(HERE/'n810-touch-fit.py'),str(targets)],text=True)
        pixel=json.loads(result)
        profile=from_pixels(pixel['x']+pixel['y'],device)
        profile['corner_max_error_px']=pixel['corner_max_error_px'];profile['center_error_px']=pixel['center_error_px']
        save(profile,output)
    print('Saved touchscreen calibration. Run sudo n810-setup-touch --recalibrate to repeat.')


if __name__=='__main__':
    try:main()
    except (EOFError,KeyboardInterrupt):print('\nTouch setup deferred; run sudo n810-setup-touch later.')
