#!/usr/bin/env python3
"""Run platform regression suites with synthetic inputs in isolated directories."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--work',type=Path,required=True);a=p.parse_args()
a.work=a.work.resolve();a.work.mkdir(parents=True,exist_ok=False)
results=[]
for test in sorted((root/'platform/scripts').glob('test-*.py')):
    home=a.work/(test.stem+'-home');home.mkdir()
    env=dict(os.environ,HOME=str(home),XDG_CONFIG_HOME=str(home/'config'),XDG_CACHE_HOME=str(home/'cache'),XDG_STATE_HOME=str(home/'state'),PYTHONDONTWRITEBYTECODE='1')
    start=time.monotonic()
    try:
        run=subprocess.run([sys.executable,str(test)],cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        code,log=run.returncode,run.stdout
    except subprocess.TimeoutExpired as error:code,log=124,error.stdout or b''
    (a.work/(test.stem+'.log')).write_bytes(log)
    results.append(dict(path=str(test.relative_to(root)),exit_code=code,seconds=round(time.monotonic()-start,2)))
    print(test.name,code,flush=True)
(a.work/'results.json').write_text(json.dumps(results,indent=2)+'\n')
sys.exit(any(r['exit_code'] for r in results))
