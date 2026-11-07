# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Cross-build the non-X framebuffer presenter; never contacts a Nokia."""
import argparse,hashlib,json,os,shlex,shutil,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cross-compile',default=os.environ.get('CROSS_COMPILE','arm-linux-gnueabi-'))
    parser.add_argument('--output',type=Path,default=HERE.parent/'build/graphics-nokia')
    args=parser.parse_args();cc=shlex.split(args.cross_compile+'gcc')
    if not shutil.which(cc[0]):parser.error('Install the ARM soft-float cross compiler or set CROSS_COMPILE.')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    native=HERE/'native';flags=['-O2','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared','-mcpu=arm1136jf-s','-marm','-mfloat-abi=soft']
    for target,sources in (('cells.so',['cells.c']),('window.so',['nokia.c','present.c'])):
        subprocess.run([*cc,*flags,*[str(native/n) for n in sources],'-o',str(out/target)],check=True)
    inputs=['present.c','present.h','cells.c','cells.h','nokia.c']
    (out/'BUILD.json').write_text(json.dumps({'status':'CROSS_BUILT_NOT_DEVICE_TESTED','sources':{n:hashlib.sha256((native/n).read_bytes()).hexdigest() for n in inputs},'artifacts':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in ('cells.so','window.so')}},indent=2)+'\n')
    print('Cross-built framebuffer frontend libraries; no device access.')
if __name__=='__main__':main()
