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
    parser.add_argument('--mesa-include',type=Path,help='verified ARM Mesa include directory, containing GL/osmesa.h')
    parser.add_argument('--mesa-library',type=Path,help='verified ARM libOSMesa.so.8 used by the device GPU service')
    args=parser.parse_args();cc=shlex.split(args.cross_compile+'gcc')
    if not shutil.which(cc[0]):parser.error('Install the ARM soft-float cross compiler or set CROSS_COMPILE.')
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    native=HERE/'native';flags=['-O2','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared','-mcpu=arm1136jf-s','-marm','-mfloat-abi=soft']
    for target,sources in (('cells.so',['cells.c']),('window.so',['nokia.c','present.c'])):
        subprocess.run([*cc,*flags,*[str(native/n) for n in sources],'-o',str(out/target)],check=True)
    if bool(args.mesa_include)!=bool(args.mesa_library):parser.error('Supply both --mesa-include and --mesa-library for the GPU renderer.')
    if args.mesa_include:
        include=args.mesa_include.resolve();library=args.mesa_library.resolve()
        if not (include/'GL/osmesa.h').is_file() or not library.is_file():parser.error('Mesa headers/library missing.')
        subprocess.run([os.environ.get('PYTHON','python3'),str(HERE/'generate_room.py'),str(out)],check=True)
        combined='\n'.join((native/name).read_text() for name in ('mbx_cells.c','terminal.c','game.c','room_pixels.c','map_pixels.c'))
        combined=combined.replace('  glFinish();','  game_draw(age,width,height,tx,ty,tw,th);glFinish();')
        (out/'renderer.c').write_text(combined)
        subprocess.run([*cc,*flags,'-ffp-contract=off','-fno-fast-math','-I'+str(native),'-I'+str(out),'-I'+str(include),str(out/'renderer.c'),str(library),'-lm','-Wl,-rpath,$ORIGIN','-o',str(out/'renderer.so')],check=True)
        room=out/'room-pixels.so'
        if room.exists() or room.is_symlink():room.unlink()
        room.symlink_to('renderer.so')
        import sys
        sys.path.insert(0,str(HERE.parent/'shell'));sys.path.insert(0,str(HERE))
        from extend_font import extend
        extend(HERE.parent/'shell/vendor/fonts/choices/console-8x16.psf',out/'console-font.psf')
    inputs=['present.c' ,'present.h','cells.c','cells.h','nokia.c']+(['mbx_cells.c','terminal.c','game.c','room_pixels.c','map_pixels.c'] if args.mesa_include else [])
    (out/'BUILD.json').write_text(json.dumps({'mesa_sha256':hashlib.sha256(args.mesa_library.read_bytes()).hexdigest() if args.mesa_library else None,'gpu_renderer':bool(args.mesa_include),'status':'CROSS_BUILT_NOT_DEVICE_TESTED','sources':{n:hashlib.sha256((native/n).read_bytes()).hexdigest() for n in inputs},'artifacts':{n:hashlib.sha256((out/n).read_bytes()).hexdigest() for n in (('cells.so','window.so','renderer.so') if args.mesa_include else ('cells.so','window.so'))}},indent=2)+'\n')
    print('Cross-built framebuffer frontend libraries; no device access.')
if __name__=='__main__':main()
