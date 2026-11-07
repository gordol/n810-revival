#!/usr/bin/env python3
"""Run host and ARM-emulated MBX checks against a completed Mesa build."""
import argparse,ast,json,os,shlex,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--mesa-work',type=Path,required=True)
p.add_argument('--work',type=Path,required=True)
a=p.parse_args();out=a.work.resolve();out.mkdir(parents=True,exist_ok=False)
mesa=a.mesa_work.resolve()/'mesa-22.3.6';build=a.mesa_work.resolve()/'build'
common=sorted((ROOT/'common').glob('*.c'));results=[]
def run(name,commands,cwd=None):
    with (out/(name+'.log')).open('wb') as log:
        for command in commands:
            result=subprocess.run(list(map(str,command)),cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
            if result.returncode:break
    results.append({'test':name,'exit_code':result.returncode})
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(name,result.returncode,flush=True)
for test in sorted((ROOT/'tests').glob('*.c')):
    if test.stem=='test_vgp_shader':continue
    exe=out/test.stem
    sources=common
    if test.stem=='test_vgp_wire':sources=[f for f in common if f.name not in ('mbx_vgp_isa.c','mbx_vgp_draw.c','mbx_vgp_topology.c')]
    command=['cc','-O1','-g','-ffp-contract=off','-I'+str(ROOT/'common'),'-I'+str(ROOT/'mesa'),'-I'+str(mesa/'src/gallium/auxiliary/draw'),test,*sources,'-lm','-lpthread','-o',exe]
    if test.stem in ('test_shared_image','test_async_image','test_gears_status'):command+=['-lX11','-lXext']
    launch=['xvfb-run','-a','-s','-screen 0 800x600x16','env','N810_MBX_ASYNC=1','timeout','60s',exe] if test.stem in ('test_shared_image','test_async_image') else [exe]
    run(test.stem,[command,launch])
for test in sorted((ROOT/'tests').glob('test_*.py')):
    args=[sys.executable,test]
    if test.stem=='test_profile_sampler':
        sampler=out/'profile-sampler'
        run('build-profile-sampler',[['cc','-O2',ROOT/'mesa/profile_sampler.c','-o',sampler]])
        args.append(sampler)
    elif test.stem.startswith(('test_arm_vertex','test_vertex_')):args.append(ROOT/'mesa')
    run(test.stem,[args])
# Use the same ARM flags and headers as the actual Mesa compilation for the TGSI oracle.
row=next(x for x in json.loads((build/'compile_commands.json').read_text()) if x['file'].endswith('tgsi_parse.c'))
command=shlex.split(row['command']);flags=[];skip=False
for flag in command[1:]:
    if skip:skip=False;continue
    if flag in ('-o','-MF','-MQ'):skip=True;continue
    if flag in ('-c','-MD','-DNDEBUG','-Werror=missing-prototypes') or flag.endswith('tgsi_parse.c'):continue
    flags.append(flag)
link=ast.literal_eval(next(x.split('=',1)[1] for x in (a.mesa_work/'armel.cross').read_text().splitlines() if x.startswith('c_link_args=')))
fixture=out/'gears-vertex-inputs.raw';fixture.write_bytes(bytes.fromhex((ROOT/'tests/fixtures/gears-vertex-inputs.hex').read_text()))
exe=out/'test-vgp-shader-arm'
run('test_vgp_shader',[[command[0],*flags,'-I'+str(ROOT/'common'),'-ffp-contract=off',ROOT/'tests/test_vgp_shader.c',*[ROOT/'common'/n for n in ('mbx_vgp_isa.c','mbx_vgp_draw.c','mbx_vgp_topology.c')],mesa/'src/gallium/auxiliary/tgsi/tgsi_parse.c',*link,'-Wl,--gc-sections','-lm','-o',exe],['qemu-arm','-cpu','arm1136','-L',a.mesa_work/'sysroot',exe,fixture]],cwd=build)
raise SystemExit(any(row['exit_code'] for row in results))
