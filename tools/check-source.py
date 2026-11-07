from pathlib import Path
import argparse,subprocess,os,json,time,concurrent.futures,sys
r=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description='Run Pocket and bundled radio tests with isolated local state.')
parser.add_argument('--work',type=Path,required=True)
parser.add_argument('--jobs',type=int,default=2)
args=parser.parse_args();out=args.work.resolve();out.mkdir(parents=True,exist_ok=False)

files=sorted((r/'pocket/tests').glob('test_*.py'))+sorted((r/'pocket/shell/vendor/packet-console').glob('test-*.py'))+sorted((r/'pocket/shell/vendor/apps/cw-reference').glob('test_*.py'))
linux_only=[p for p in files if p.name=='test-radio-proxy.py' and sys.platform!='linux']
files=[p for p in files if p not in linux_only]
if linux_only:print('Linux-only suite: test-radio-proxy.py (requires python3-dbus and python3-gi)')
# Each test runs in its own process and private home; fixtures never read operator state.
def run(p):
 name=str(p.relative_to(r));home=out/(p.stem+'-home');home.mkdir(exist_ok=True)
 env=os.environ.copy();env.update(HOME=str(home),PYTHONDONTWRITEBYTECODE='1',POCKET_DATA_ROOT=str(r/'pocket/data'),XDG_STATE_HOME=str(home/'state'),XDG_CACHE_HOME=str(home/'cache'),XDG_CONFIG_HOME=str(home/'config'))
 cmd=[sys.executable,'-B','-m','unittest','discover','-s',str(p.parent),'-p',p.name,'-q'] if p.parent.name in ('tests','cw-reference') else [sys.executable,'-B',str(p)]
 start=time.monotonic()
 try:
  result=subprocess.run(cmd,cwd=p.parent,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=240);code=result.returncode;log=result.stdout
 except subprocess.TimeoutExpired as e:code=124;log=e.stdout or b''
 (out/(p.stem+'.log')).write_bytes(log)
 return dict(path=name,code=code,seconds=round(time.monotonic()-start,2))
results=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=args.jobs) as pool:
 for result in pool.map(run,files):
  results.append(result);print(result,flush=True);(out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print('Passed',sum(x['code']==0 for x in results),'/',len(results))

raise SystemExit(any(row['code'] for row in results))
