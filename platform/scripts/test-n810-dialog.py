"""Exercise the optional GTK dialog adapter without a GUI or real power actions."""
import os,pathlib,subprocess,tempfile
base=pathlib.Path(__file__).resolve().parent
with tempfile.TemporaryDirectory() as t:
 d=pathlib.Path(t)
 (d/'yad').write_text('''#!/bin/sh
cat >/dev/null
printf '%s\n' "$TEST_RESULT"
exit "${TEST_EXIT:-0}"
''');(d/'yad').chmod(0o755)
 env=dict(os.environ,PATH=str(d)+':'+os.environ['PATH'],DISPLAY=':99')
 def run(kind,result,code=0):
  args=['sh',str(base/'n810-dialog'),kind,'Test','Prompt']
  if kind=='menu':args+=['back','Return','topoff','Top off']
  return subprocess.run(args,env=dict(env,TEST_RESULT=result,TEST_EXIT=str(code)),text=True,capture_output=True,input='')
 assert run('confirm','Cancel').returncode!=0
 assert run('confirm','Confirm').returncode==0
 assert run('confirm','Confirm',1).returncode!=0
 assert run('menu','').returncode!=0
 r=run('menu','back');assert r.returncode==0 and r.stdout.strip()=='back'
print('PASS: GTK Cancel, close and empty selection cannot confirm an action.')
