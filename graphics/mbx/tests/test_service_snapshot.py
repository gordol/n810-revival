"""Regression: boolean sysfs values must not prevent GPU owner cleanup."""
import ast,tempfile
from pathlib import Path
source=Path(__file__).resolve().parents[1]/'mesa/stop_service.py'
node=next(n for n in ast.parse(source.read_text()).body if isinstance(n,ast.FunctionDef) and n.name=='snapshot')
with tempfile.TemporaryDirectory() as d:
 base=Path(d)
 for name,value in {'enabled':'Y\n','disabled':'N\n','jobs':'1317\n','error':'-5\n','recover':'not-readable-as-a-number'}.items():(base/name).write_text(value)
 scope={'base':base};exec(compile(ast.Module(body=[node],type_ignores=[]),str(source),'exec'),scope)
 assert scope['snapshot']()=={'enabled':1,'disabled':0,'jobs':1317,'error':-5}
 (base/'unexpected').write_text('invalid')
 try:scope['snapshot']()
 except ValueError:pass
 else:raise AssertionError('Unexpected parameter text was silently accepted')
print('PASS: actual cleanup snapshot accepts boolean/integer sysfs values and rejects invalid values')
