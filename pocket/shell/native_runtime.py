"""Build/select the cell compositor for this host, with explicit provenance."""
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import sysconfig
import tempfile


def select(build=True):
    root=Path(__file__).resolve().parent/'native'
    identity={'system':platform.system(),'machine':platform.machine(),'python_tag':sys.implementation.cache_tag,'build_policy':5,'abi':'CPython limited API 3.11','sources':{}}
    result={'mode':'auto','identity':identity,'library':None,'reason':None,'built':False}
    if sys.implementation.name!='cpython' or sys.version_info<(3,11):result['reason']='native requires CPython 3.11+';return result
    try:identity['sources']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (root/'cell_module.c',root/'cell_engine.c',root/'window_host.c',root/'scene_host.c',root/'blend_host.c',root/'input_pump.c')}
    except OSError as error:result['reason']='native source unavailable: '+str(error);return result
    cache=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'pocket/native'
    directory=cache/('-'.join((identity['system'],identity['machine'],identity['python_tag'])))
    library=directory/'_cellengine.abi3.so';receipt=directory/'provenance.json'
    try:
        prior=json.loads(receipt.read_text())
        if prior['identity']==identity and prior['sha256']==hashlib.sha256(library.read_bytes()).hexdigest():
            result.update(library=str(library),sha256=prior['sha256']);return result
    except (OSError,ValueError,KeyError):pass
    if not build:result['reason']='no matching host build';return result
    compiler=shutil.which('cc');include=sysconfig.get_path('include')
    if not compiler or not include or not Path(include,'Python.h').is_file():
        result['reason']='host C compiler or Python headers unavailable';return result
    try:
        directory.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.cell-',suffix='.so',dir=directory);os.close(fd)
    except OSError as error:result['reason']='native build storage unavailable: '+str(error);return result
    command=[compiler,'-O3','-std=c99','-Wall','-Wextra','-Werror','-fPIC','-shared','-pthread','-ffp-contract=off','-fno-fast-math','-fno-builtin-sin','-fno-builtin-cos','-I'+include,str(root/'cell_module.c'),'-o',tmp]
    if identity['system']=='Darwin':command+=['-arch',identity['machine'],'-undefined','dynamic_lookup']
    try:
        done=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,timeout=30)
        if done.returncode:
            result['reason']='host C build failed: '+done.stderr[-1200:];return result
        digest=hashlib.sha256(Path(tmp).read_bytes()).hexdigest();os.replace(tmp,library)
        data={'identity':identity,'sha256':digest,'compiler':compiler,'flags':command[1:],'library':str(library)}
        fd,temp_receipt=tempfile.mkstemp(prefix='.provenance-',dir=directory)
        with os.fdopen(fd,'w') as f:json.dump(data,f,indent=2);f.write('\n')
        os.replace(temp_receipt,receipt)
        result.update(library=str(library),sha256=digest,built=True);return result
    except (OSError,subprocess.SubprocessError) as e:result['reason']=str(e);return result
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
