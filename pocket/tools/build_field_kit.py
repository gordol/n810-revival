#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Assemble public, offline field documentation and ARM tools, without private state."""
import argparse,hashlib,json,shutil,subprocess,html,re,tarfile
from pathlib import Path
import markdown

ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--project',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True)
    def copy(source,destination):
        destination.parent.mkdir(parents=True,exist_ok=True)
        if source.is_dir():shutil.copytree(source,destination,dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
        else:shutil.copy2(source,destination)
    copy(a.project/'site',out/'docs/project')
    web=a.build/'web-libs'
    scripts=out/'docs/project/assets/javascripts'
    for name in ('mermaid.min.js','resize-observer.js'):copy(web/name,scripts/name)
    for bundle in scripts.glob('bundle.*.min.js'):
        text=bundle.read_text()
        for url,name in (('https://unpkg.com/mermaid@11/dist/mermaid.min.js','mermaid.min.js'),('https://unpkg.com/resize-observer-polyfill','resize-observer.js')):
            text=text.replace('"'+url+'"',"new URL("+json.dumps(name)+",document.querySelector('script[src*=\"bundle.\"]').src).href")
        bundle.write_text(text)
    for page in (out/'docs/project').rglob('*.html'):
        page.write_text(page.read_text().replace('data-md-component="source"','data-offline-source="true"').replace('="/assets/','="assets/'))
    web_receipt={}
    for name in ('mermaid-11.4.1','resize-observer-polyfill-1.5.1'):
        archive=web/(name+'.tgz')
        web_receipt[name]=dict(archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),registry='https://registry.npmjs.org/')
        with tarfile.open(archive) as package:
            license=next(n for n in package.getnames() if n.lower() in ('package/license','package/license.md'))
            destination=out/'source/web-libraries'/name/'LICENSE';destination.parent.mkdir(parents=True,exist_ok=True);destination.write_bytes(package.extractfile(license).read())
    (out/'source/web-libraries/BUILD.json').write_text(json.dumps(web_receipt,indent=2)+'\n')
    copy(a.build/'tools',out)
    copy(ROOT/'platform/n810/field_kit',out/'bin')
    copy(a.build/'debs',out/'source/debian-packages')
    copy(a.build/'0xffff-source.tar.gz',out/'source/0xffff-source.tar.gz')
    copy(a.build/'build-tools.sh',out/'source/build-tools.sh')
    copy(a.project/'platform/kernel',out/'source/kernel-build')
    package=a.project/'artifacts/kernel-clean-build-20261104/package'
    for name in ('BUILD.json','KERNELRELEASE','kernel.config','zImage-omap2420-n810'):copy(package/name,out/'kernel'/name)
    copy(package/'root/lib/modules',out/'kernel/modules')
    # Full tracked source, including current changes; no build outputs or private files.
    paths=subprocess.check_output(['git','ls-files','-z'],cwd=ROOT).decode().split('\0')
    paths+=['shell/native_peer_setup.py','shell/peer_profile.py','docs/SELF-CONTAINED-N810.md','tools/build_field_kit.py','tests/integration/native_peer_messages.py']
    paths += [str(p.relative_to(ROOT)) for p in (ROOT/'platform/n810/field_kit').iterdir() if p.is_file()]
    for name in sorted(set(filter(None,paths))):
        source=ROOT/name
        if source.is_file():copy(source,out/'source/pocket'/name)
    manuals=[];links=[]
    style='<style>body{max-width:65em;margin:2em auto;padding:0 1em;font:17px sans-serif;line-height:1.5}pre{overflow:auto;background:#eee;padding:1em}img{max-width:100%}a{color:#075a9c}</style>'
    for source in sorted((ROOT/'docs').rglob('*.md'))+[ROOT/'README.md',ROOT/'TERRAIN-PROFILE.md']:
        if not source.exists():continue
        relative=source.relative_to(ROOT);destination=out/'docs/pocket'/relative.with_suffix('.html');raw=source.read_text();title=next((s.lstrip('# ') for s in raw.splitlines() if s.startswith('# ')),source.stem)
        rendered=markdown.markdown(raw,extensions=['fenced_code','tables','toc'])
        rendered=re.sub(r'(href="[^"#]+)\.md([#"])',r'\1.html\2',rendered)
        destination.parent.mkdir(parents=True,exist_ok=True);destination.write_text('<!doctype html><meta charset="utf-8"><title>'+html.escape(title)+'</title>'+style+rendered)
        links.append('<li><a href="pocket/'+str(relative.with_suffix('.html'))+'">'+html.escape(title)+'</a></li>')
        # Full text in Pocket Help, without the short quick-help normalization cap.
        manuals.append([title,raw.splitlines()])
    # Include text of the full project, grouped separately from current Pocket docs.
    for source in sorted((a.project/'docs').rglob('*.md')):
        raw=source.read_text();title=next((s.lstrip('# ') for s in raw.splitlines() if s.startswith('# ')),source.stem)
        manuals.append(['Project: '+title,raw.splitlines()])
    (out/'manual.json').write_text(json.dumps(manuals,ensure_ascii=False))
    (out/'docs/index.html').write_text('<!doctype html><meta charset="utf-8"><title>Pocket field manual</title>'+style+'<h1>Pocket field manual</h1><p>Stored on this Nokia. No Internet needed.</p><p><a href="project/">Full N810 project documentation</a></p><h2>Current Pocket documentation</h2><ul>'+''.join(links)+'</ul>')
    receipt=dict(pocket_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),ffff_commit='9c608021f8a5135aab9efc97e371737832c0f3de',ffff_source='https://github.com/pali/0xFFFF',busybox_source='https://sources.debian.org/src/busybox/1:1.35.0-4+deb12u1/',libusb_source='https://sources.debian.org/src/libusb/2:0.1.12-32/',date='2026-11-04',kernel_boot_tested=False)
    (out/'source/BUILD.json').write_text(json.dumps(receipt,indent=2)+'\n')
    files={str(p.relative_to(out)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file() and p.name!='manifest.json'}
    (out/'manifest.json').write_text(json.dumps(dict(version=1,files=files,manual_topics=len(manuals),provenance=receipt),indent=2)+'\n')
    print(json.dumps(dict(files=len(files),manual_topics=len(manuals),bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))))
if __name__=='__main__':main()
