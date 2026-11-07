# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the checked-in graphical frontend and its generated inputs."""
from pathlib import Path
import hashlib,json,os,platform,shlex,shutil,subprocess,sys,sysconfig

HERE=Path(__file__).resolve().parent
POCKET=HERE.parent
OUT=POCKET/'build/graphics'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    cc=shlex.split(os.environ.get('CC','cc'))
    if not shutil.which(cc[0]):raise SystemExit('A C compiler is required (set CC if necessary).')
    if not shutil.which('sdl2-config'):raise SystemExit('SDL2 development files are required: install SDL2, then retry (see graphics/README.md).')
    sdl=shlex.split(subprocess.check_output(['sdl2-config','--cflags','--libs'],text=True))
    mac=sys.platform=='darwin'
    gl=['-framework','OpenGL'] if mac else ['-lGL']
    flags=['-O2','-std=c99','-Wall','-Wextra','-Werror','-shared','-fPIC']+(['-Wno-deprecated-declarations'] if mac else [])
    sys.path.insert(0,str(POCKET/'shell'))
    os.environ.setdefault('XDG_CACHE_HOME',str(OUT/'cache'))
    from native_runtime import select
    native=select(build=True)
    if not native['library']:raise SystemExit(native['reason'])
    sources=[p for p in HERE.rglob('*') if p.suffix in ('.c','.h','.m','.py')]
    sources.extend([POCKET/'shell/font_preview.py',POCKET/'shell/apps/surface-renderer/room.py',POCKET/'shell/vendor/fonts/choices/console-8x16.psf'])
    identity={'version':1,'platform':platform.system(),'machine':platform.machine(),'python':sys.implementation.cache_tag,'compiler':cc,'compiler_version':subprocess.check_output([*cc,'--version'],text=True).splitlines()[0],'sdl':sdl,'sdl_version':subprocess.check_output(['sdl2-config','--version'],text=True).strip(),'native':native['identity'],'inputs':{str(p.relative_to(POCKET)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    stamp=OUT/'BUILD.json';config_path=OUT/'frontend.json'
    outputs=['reference.so','renderer.so','window.so','room-pixels.so','console-font.psf','frontend.json','room_mesh.h','test-desktop-input','test-desktop-borders']+(['_gpueffects.abi3.so','console-font.glyphs'] if mac else [])
    if stamp.exists() and json.loads(stamp.read_text())==identity and all((OUT/n).is_file() for n in outputs):
        print('Graphical frontend is up to date.');return
    subprocess.run([sys.executable,str(HERE/'generate_room.py'),str(OUT)],check=True)
    from extend_font import extend,Font
    font_path=OUT/'console-font.psf';extend(POCKET/'shell/vendor/fonts/choices/console-8x16.psf',font_path)
    subprocess.run([*cc,*flags,str(HERE/'native/cells.c'),'-o',str(OUT/'reference.so')],check=True)
    # One GL owner/context is shared by cells, direct Room pixels and overlays.
    combined='\n'.join((HERE/'native'/name).read_text() for name in ('mbx_cells.c','terminal.c','game.c','room_pixels.c'))
    combined=combined.replace('  glFinish();','  game_draw(age,width,height,tx,ty,tw,th);glFinish();')
    (OUT/'renderer.c').write_text(combined)
    subprocess.run([*cc,*flags,'-DPOCKET_DESKTOP_GL','-I'+str(HERE/'native'),'-I'+str(OUT),str(OUT/'renderer.c'),*sdl,*gl,'-lm','-o',str(OUT/'renderer.so')],check=True)
    subprocess.run([*cc,*flags,'-I'+str(HERE/'native'),str(HERE/'native/desktop_input.c'),*sdl,'-o',str(OUT/'window.so')],check=True)
    for name in ('input','borders'):
        subprocess.run([*cc,'-O2','-std=c99','-Wall','-Wextra','-Werror',str(HERE/f'native/test_desktop_{name}.c'),str(OUT/'window.so'),*sdl,'-o',str(OUT/f'test-desktop-{name}')],check=True)
    room=OUT/'room-pixels.so'
    if room.is_symlink():room.unlink()
    elif room.exists():room.unlink()
    room.symlink_to('renderer.so')
    if mac:
        subprocess.run([*cc,*flags,'-ffp-contract=off','-fno-fast-math','-I'+sysconfig.get_path('include'),'-I'+str(POCKET/'shell/native'),str(HERE/'effects/gpu_effects.c'),*gl,'-undefined','dynamic_lookup','-o',str(OUT/'_gpueffects.abi3.so')],check=True)
        tool=OUT/'font-glyphs'
        subprocess.run([*cc,'-O2',str(HERE/'native/font_glyphs.m'),'-framework','CoreText','-framework','CoreGraphics','-framework','CoreFoundation','-o',str(tool)],check=True)
        import re
        required={8679,9475};font=Font(font_path)
        for path in (POCKET/'shell').rglob('*.py'):
            if 'vendor' in path.relative_to(POCKET/'shell').parts:continue
            text=path.read_text();required.update(ord(ch) for ch in text if ord(ch)>=128)
            required.update(int(code,16) for code in re.findall(r'\\u([0-9a-fA-F]{4})',text))
        missing=sorted(code for code in required if chr(code) not in font.mapping)
        with font_path.with_suffix('.glyphs').open('wb') as output:
            subprocess.run([str(tool)],input=''.join(f'{code:x}\n' for code in missing).encode(),stdout=output,check=True)
    config={'font':str(font_path),'renderer_library':str(OUT/'reference.so'),'gpu_library':str(OUT/'renderer.so'),'display_library':str(OUT/'window.so'),'native_library':native['library'],'effect_library':str(OUT/'_gpueffects.abi3.so'),'graphics_path':str(HERE)}
    config_path.write_text(json.dumps(config,indent=2)+'\n');stamp.write_text(json.dumps(identity,sort_keys=True,indent=2)+'\n')
    print('Built graphical frontend from repository source; no device access.')

if __name__=='__main__':main()
