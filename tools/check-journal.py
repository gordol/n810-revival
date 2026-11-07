#!/usr/bin/env python3
"""Check the journal's explicit source inventory and regenerate its navigation."""
import argparse,json,re,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write',action='store_true');p.add_argument('--tracked',action='store_true');args=p.parse_args()
entries=json.loads((ROOT/'tools/journal-sources.json').read_text())['entries']
errors=[];sources=set();seen=set();index=['# Journal source index\n','This index follows all 23 journal entries from the first recovery work through the frozen 30 FPS result. Each source link opens a local text copy from this checkout; the adjacent GitHub link identifies its repository location. Build guides open inside this site.\n','The [checkpoint test guide](../how-to/test-journal-checkpoints.md) gives the commands and external inputs. Each entry identifies its source version and the scope of its tests.\n']
START='<!-- journal-sources:start -->';END='<!-- journal-sources:end -->'
for row in entries:
    path=ROOT/row['post'];seen.add(row['post']);post=path.read_text();title=post.splitlines()[0].removeprefix('# ')
    section=['## Code, tests and build inputs\n','| Material | Repository files |','|---|---|']
    for key,label in [('implementation','Implementation'),('tests','Checks and fixtures'),('inputs','Build inputs')]:
        links=[]
        for item in row[key]:
            source=item['path'];sources.add(source)
            if not (ROOT/source).is_file():errors.append('Missing source: '+source)
            local='../assets/source/journal/'+source+'.txt'
            url='https://github.com/gordol/n810-revival/blob/main/'+source
            links.append(f"[{item['label']}]({local}) ([GitHub]({url}))")
        section.append('| '+label+' | '+'<br>'.join(links)+' |')
    section+=['',f"[Build and test instructions](../{row['guide']}) · [Chronological source index](../reference/journal-sources.md#{row['id']})"]
    if row['note']:section+=['',row['note']]
    block=START+'\n'+'\n'.join(section)+'\n'+END
    if START in post:updated=re.sub(re.escape(START)+r'.*?'+re.escape(END),lambda _:block,post,flags=re.S)
    else:
        at=post.find('[Journal](')
        updated=post[:at]+block+'\n\n'+post[at:] if at>=0 else post.rstrip()+'\n\n'+block+'\n'
    if args.write:path.write_text(updated)
    elif updated!=post:errors.append('Source navigation needs regeneration: '+row['post'])
    index+=['<a id="'+row['id']+'"></a>\n','## '+title+'\n',f"[Read the journal entry](../posts/{path.name})\n",'\n'.join(section[1:])+'\n']
    for target in re.findall(r'https://github.com/gordol/n810-revival/(?:blob|tree)/main/([^\s)#]+)',updated):
        if not (ROOT/target).exists():errors.append('Broken journal GitHub target: '+target)
actual={str(x.relative_to(ROOT)) for x in (ROOT/'docs/posts').glob('*.md')}
if actual!=seen:errors.append('Journal coverage mismatch: '+str(sorted(actual^seen)))
out=ROOT/'docs/reference/journal-sources.md';content='\n'.join(index)
if args.write:out.write_text(content)
elif not out.exists() or out.read_text()!=content:errors.append('Chronological source index needs regeneration')
if args.tracked:
    tracked=set(subprocess.check_output(['git','ls-files'],cwd=ROOT,text=True).splitlines())
    errors+=['Untracked journal input: '+p for p in sorted(sources-tracked)]
for error in errors:print(error,file=sys.stderr)
print(f'Journal audit: {len(entries)} entries, {len(sources)} unique source/test/input files, {len(errors)} errors.')
sys.exit(bool(errors))
