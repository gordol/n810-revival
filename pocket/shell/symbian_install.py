"""Copy an explicitly selected installer to the private inbox and request install."""
import argparse
from pathlib import Path
import os
import shutil
import tempfile
from symbian_catalog import packages
from symbian_launch import launch

def install(source):
    source=Path(source).expanduser().resolve(strict=True)
    inbox=Path.home()/'.local/share/symbian-private/runtime/inbox';inbox.mkdir(parents=True,exist_ok=True,mode=0o700)
    target=inbox/source.name
    if source!=target:
        fd,name=tempfile.mkstemp(prefix='.install-',dir=inbox)
        try:
            with source.open('rb') as src,os.fdopen(fd,'wb') as dst:shutil.copyfileobj(src,dst,65536)
            os.link(name,target)
        finally:Path(name).unlink(missing_ok=True)
    entry=next((p for p in packages() if Path(p['path'])==target),None)
    if entry is None:raise ValueError('Use a .sis or .sisx installer with a simple filename')
    launch(entry['id'])

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('package',type=Path);a=p.parse_args()
    try:install(a.package)
    except (OSError,ValueError,RuntimeError) as error:p.exit(1,str(error)+'\n')
if __name__=='__main__':main()
