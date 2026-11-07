"""Resolve captured ARM PC/LR samples using symbols from the exact tested ELF.
Pass result.json, matching unstripped libGL nm output, and matching libc nm output.
This reads saved evidence only; libc identity must be checked separately.
"""
from pathlib import Path
import bisect,collections,json,re,sys
result=Path(sys.argv[1]);log=json.loads(result.read_text())['gears_log']
maps=[]
for line in log.splitlines():
 m=re.match(r'N810_MBX_CPU_MAP ([0-9a-f]+)-([0-9a-f]+) (\S+) ([0-9a-f]+) \S+ \d+\s*(.*)',line)
 if m:maps.append((int(m[1],16),int(m[2],16),int(m[4],16),m[5]))
def symbols(path):
 rows=[]
 for line in Path(path).read_text().splitlines():
  m=re.match(r'([0-9a-f]+) ([0-9a-f]+) [tTwW] (.*)',line)
  if m:rows.append((int(m[1],16),int(m[2],16),m[3]))
 rows.sort();return [r[0] for r in rows],rows
libraries={'libGL.so.1':symbols(sys.argv[2]),'libc.so.6':symbols(sys.argv[3])}
def resolve(address):
 for start,end,offset,name in maps:
  if start<=address<end:
   key=Path(name).name
   if key in libraries:
    starts,rows=libraries[key];a=address-start+offset;i=bisect.bisect_right(starts,a)-1
    if i>=0 and a<rows[i][0]+rows[i][1]:return rows[i][2]
   return name or 'anonymous/JIT'
 return 'unmapped/JIT'
pairs=re.findall(r'N810_MBX_CPU_SAMPLE ([0-9a-f]+) ([0-9a-f]+)',log)
counts=collections.Counter(resolve(int(pc,16)) for pc,lr in pairs)
callers=collections.Counter((resolve(int(pc,16)),resolve(int(lr,16))) for pc,lr in pairs if resolve(int(pc,16)).startswith(('memcpy','memset','write@')))
report={'samples':len(pairs),'functions':[{'function':name,'samples':n,'percent':round(100*n/len(pairs),2)} for name,n in counts.most_common()], 'copy_and_write_callers':[{'function':key[0],'caller':key[1],'samples':n} for key,n in callers.most_common()]}
(result.parent/'cpu-resolved.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(samples=len(pairs),functions=report['functions'][:20],callers=report['copy_and_write_callers'][:12]),indent=2))
