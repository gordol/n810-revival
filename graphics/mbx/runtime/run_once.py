"""One guarded identity/render pair. No reboot, retry or force removal."""
from pathlib import Path
import sys,subprocess,json,os
root=Path(sys.argv[1]).resolve();sys.path.insert(0,str(root))
from judge_probe import CLEAN
assert os.geteuid()==0
assert not Path('/sys/module/n810_mbx_gpu_probe').exists()
identity=root/'identity-result';render=root/'render-result'
assert not identity.exists() and not render.exists()
base=[sys.executable,str(root/'run_probe.py'),'--permit-global-clock-commit','--run']
subprocess.run(base+['--mode','identity','--output',str(identity)],check=True)
assert json.loads((identity/'verdict.json').read_text())['status']=='CLEAN_IDENTITY_RECEIPT'
subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
r=subprocess.run(base+['--mode','fill','--identity-receipt',str(identity/'receipt.json'),'--output',str(render)])
receipt=json.loads((render/'receipt.json').read_text());p=receipt['parameters']
failed=bool(r.returncode)
# A pixel mismatch alone does not prevent normal removal after ALL ownership
# and reset checks have passed. Any retained fault stops here with no removal.
for name,want in CLEAN.items():assert p.get(name)==want,(name,p.get(name),want)
assert p.get('gpu_quiesced')==1 and p.get('gpu_dma_stage')==0
if p.get('gpu_capture_valid')==1:
 with open('/dev/n810-mbx-capture','rb',buffering=0) as f:blob=f.read(184385)
 (render/'capture.bin').write_bytes(blob)
 from check_capture import validate
 try:verdict=validate(blob)
 except ValueError as error:
  verdict={'status':'PIXEL_OR_BOUNDS_CHECK_FAILED','error':str(error)}
  failed=True
 (render/'pixel-verdict.json').write_text(json.dumps(verdict,indent=2)+'\n')
 print(json.dumps(verdict,indent=2),flush=True)
subprocess.run(['/sbin/rmmod','n810_mbx_gpu_probe'],check=True)
print('Normal unload complete; no GPU diagnostic resident.',flush=True)
raise SystemExit(2 if failed else 0)
