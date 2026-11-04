"""Inventory runtime copies and conservative caller candidates; never delete code.

Run from any directory. Output is JSON. A missing static caller is a review
candidate, not proof of dead code: CLI entry points and computed imports exist.
"""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import subprocess

from package_nokia import ROOT, runtime_files


def audit():
    tracked=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    paths=[ROOT/name for name in tracked if name and (ROOT/name).is_file()]
    source={str(p.relative_to(ROOT/'shell')):p.read_bytes()
            for p in paths if p.is_relative_to(ROOT/'shell')}
    runtime=runtime_files(source)
    python={name:raw for name,raw in runtime.items() if name.endswith('.py')}
    duplicates=defaultdict(list)
    for name,raw in python.items():duplicates[hashlib.sha256(raw).hexdigest()].append(name)
    # Include executable/config callers outside shell, but exclude historical
    # inventories, documentation, tests and excluded runtime copies.
    callers={name:raw.decode(errors='replace') for name,raw in runtime.items()
             if Path(name).suffix in ('.py','.json','.cjs','.sh')
             and Path(name).name!='dependency-inventory.json'}
    for p in paths:
        relative=p.relative_to(ROOT)
        if relative.parts[0] in ('tools','platform') and p.suffix in ('.py','.json','.sh'):
            callers[str(relative)]=p.read_text(errors='replace')
    callers['Makefile']=(ROOT/'Makefile').read_text()
    candidates=[]
    for name in python:
        path=Path(name)
        if path.name=='__init__.py':continue
        if not any(other!=name and (path.name in text or path.stem in text)
                   for other,text in callers.items()):
            candidates.append(name)
    return dict(source_python=sum(n.endswith('.py') for n in source),
                runtime_python=len(python),runtime_bytes=sum(map(len,runtime.values())),
                by_area=dict(sorted(Counter('/'.join(Path(n).parts[:2]) if '/' in n else 'shell core'
                                            for n in python).items())),
                exact_duplicate_groups=[names for names in duplicates.values() if len(names)>1],
                no_static_caller_candidates=sorted(candidates),
                excluded_python=sorted(n for n in source if n.endswith('.py') and n not in runtime))


if __name__=='__main__':print(json.dumps(audit(),indent=2))
