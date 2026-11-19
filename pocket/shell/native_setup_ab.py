"""A/B installer adapter for the existing N810 Setup desktop workflow."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
BOOTSTRAP=ROOT/'platform/bootstrap'


def selected(manifest):
    return Path(manifest).name=='AB.json'


def verify(kit,progress=None):
    sys.path.insert(0,str(BOOTSTRAP))
    from ab_media import verify as check
    if progress:progress('Verifying A/B slots, persistent-data seed, and internal recovery…')
    root,m=check(kit)
    from ab_install import ram
    if not (root/'SD-BOOTSTRAP.json').is_file():ram(root)
    return dict(state='files_verified',kind='n810-ab',release='SD A/B + internal recovery',storage_target='sd-ab',
                files=[dict(role=name,path=name,bytes=value['bytes']) for name,value in m['files'].items()],
                total_bytes=sum(v['bytes'] for v in m['files'].values()),destination=str(root))


def run(argv,progress):
    p=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
    lines=[]
    for line in p.stdout:
        lines.append(line)
        if progress:progress(line.strip()[:180])
    if p.wait():raise RuntimeError('A/B install step failed: '+''.join(lines[-8:])[-700:])
    output=''.join(lines)
    # The command's final output is a JSON object; progress may precede it.
    decoder=json.JSONDecoder()
    for offset in reversed([i for i,c in enumerate(output) if c=='{']):
        try:
            result,end=decoder.raw_decode(output[offset:])
            if not output[offset+end:].strip():
                result.setdefault('storage_target','sd-ab');return result
        except ValueError:pass
    raise RuntimeError('A/B installer did not return a result')


def work(action,manifest,disk,key,flasher,progress,cancelled=None):
    kit=Path(manifest).expanduser().resolve().parent
    if action=='check':return verify(kit,progress)
    if action=='prepare':raise ValueError('A/B kits are already prepared. Select Build kit from source for another installation.')
    public=Path(key).expanduser()
    private=public.with_suffix('') if public.suffix=='.pub' else public
    if not private.is_file():private=public
    if action=='install':
        if not (kit/'SD-INSTALL.json').exists():action='mac-write'
        elif not any((kit/n).exists() for n in ('RAM-BOOT.json','SD-BOOT.json')):action='boot'
        elif not (kit/'RECOVERY-INSTALL.json').exists():action='write'
        else:action='flash'
    if action in ('mac-check','mac-write'):
        if not disk:raise ValueError('Select the removable SD whole disk first')
        argv=[sys.executable,str(BOOTSTRAP/'ab_media.py'),'--kit',str(kit),'--disk',disk]
        if action=='mac-write':argv=['sudo','-n',*argv,'--erase']
        return run(argv,progress)
    if action in ('boot','flash') and not Path(flasher).is_file():
        from n810_flasher import build
        build(progress,cancelled)
    argv=[sys.executable,str(BOOTSTRAP/'ab_install.py')]
    if action=='boot':return run([*argv,'boot-sd' if (kit/'SD-BOOTSTRAP.json').is_file() else 'boot-ram','--kit',str(kit),'--flasher',str(flasher)],progress)
    if action=='write':
        result=run([*argv,'inspect','--kit',str(kit),'--key',str(private)],progress)
        return run([*argv,'write-recovery','--kit',str(kit),'--key',str(private),'--expected-cid',result['cid'],'--erase'],progress)
    if action=='flash':return run([*argv,'flash-recovery','--kit',str(kit),'--flasher',str(flasher),'--key',str(private)],progress)
    raise ValueError('This action is not available for an A/B kit')
