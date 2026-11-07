"""Create a per-device legacy pairing PIN without printing or overwriting it."""
import json,os,secrets
from pathlib import Path
path=Path(__file__).resolve().parent/'HTITPrivate.h'
fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:
    out.write('#pragma once\n#define HTIT_BT_PIN '+json.dumps(''.join(str(secrets.randbelow(10)) for _ in range(15)))+'\n')
print('Created private HTIT configuration; PIN was not printed.')
