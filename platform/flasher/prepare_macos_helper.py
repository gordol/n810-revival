#!/usr/bin/env python3
"""Prepare a self-contained macOS USB flasher helper for one-time admin installation."""
import argparse, hashlib, json, os, platform, re, shutil, subprocess
from pathlib import Path

DEST='/Library/PrivilegedHelperTools/org.n810-revival.flasher'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def prepare(build, output):
    if platform.system()!='Darwin':raise ValueError('Prepare this helper on macOS')
    record=json.loads((build/'BUILD.json').read_text())
    lock=json.loads(Path(__file__).with_name('source.lock.json').read_text())
    identity=record['identity']
    if (not identity.get('usb_only') or not identity.get('nolo_only') or
        identity.get('source_revision')!=lock['revision'] or identity.get('source_sha256')!=lock['sha256'] or
        sha(build/'0xFFFF')!=record['binary_sha256']):raise ValueError('Build the pinned macOS flasher with make flasher first')
    output.mkdir(mode=0o700,parents=True,exist_ok=False)
    copied={}
    def copy(source):
        source=Path(source);target=output/source.name
        if str(source) in copied:return
        if target.exists():raise ValueError('Conflicting library basename: '+source.name)
        shutil.copyfile(source,target);target.chmod(0o755);copied[str(source)]=target
        lines=subprocess.check_output(['otool','-L',str(source)],text=True).splitlines()[1:]
        for line in lines:
            dependency=line.strip().split(' (')[0]
            if dependency==str(source) or dependency.startswith(('/usr/lib/','/System/Library/')):continue
            if not dependency.startswith('/'):raise ValueError('Unresolved library dependency: '+dependency)
            copy(dependency)
            subprocess.run(['install_name_tool','-change',dependency,'@loader_path/'+Path(dependency).name,str(target)],check=True)
        subprocess.run(['codesign','--force','--sign','-',str(target)],check=True)
    copy(build/'0xFFFF')
    (output/'ORIGINAL-SHA256').write_text(record['binary_sha256']+'\n')
    helper='''#!/bin/sh
set -eu
if [ "$#" = 2 ] && [ "$1" = --configure-network ]; then
 case "$2" in en[0-9]|en[0-9][0-9]) ;; *) exit 64;; esac
 exec /sbin/ifconfig "$2" inet 169.254.81.2 netmask 255.255.0.0 up
fi
case "$#" in
  1) test "$1" = -I; limit=25 ;;
  6) if [ "$1" = -P ]; then
       case "$2" in ''|0|*[!0-9]*) exit 64;; esac
       test "$3" = -m; case "$4" in kernel:/*) ;; *) exit 64;; esac
       test "$5" = -f; test "$6" = -r; limit=165
     else
       test "$1" = -m; case "$2" in kernel:/*) ;; *) exit 64;; esac
       test "$3" = -m; case "$4" in initfs:/*) ;; *) exit 64;; esac
       test "$5" = -l; test "$6" = -b; limit=165
     fi ;;
  4) test "$1" = -m; case "$2" in kernel:/*) ;; *) exit 64;; esac
     case "$3:$4" in -f:-r|-l:-b) limit=165 ;; *) exit 64;; esac ;;
  *) exit 64 ;;
esac
/usr/bin/env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin '''+DEST+'''/0xFFFF "$@" &
flasher=$!
(
 /bin/sleep "$limit"
 /bin/kill -TERM "$flasher" 2>/dev/null || :
) </dev/null >/dev/null 2>&1 &
watchdog=$!
set +e
wait "$flasher"
status=$?
set -e
/bin/kill -TERM "$watchdog" 2>/dev/null || :
wait "$watchdog" 2>/dev/null || :
exit "$status"
'''
    (output/'helper').write_text(helper)
    (output/'helper').chmod(0o755)
    names=[p.name for p in output.iterdir()]
    checks='\n'.join(sha(output/n)+'  '+n for n in names)+'\n'
    (output/'SHA256SUMS').write_text(checks)
    installer='''#!/bin/sh
set -eu
[ "$(id -u)" = 0 ] || { echo 'Run this installer with sudo.' >&2; exit 1; }
replace=no
case "$#" in 0) ;; 1) [ "$1" = --replace ] && replace=yes || exit 64;; *) exit 64;; esac
user=${SUDO_USER:-}
case "$user" in ''|root|*[!a-zA-Z0-9_-]*) echo 'Run sudo from your normal local account.' >&2; exit 1;; esac
cd "$(dirname "$0")"
/usr/bin/shasum -a 256 -c SHA256SUMS
base=/Library/PrivilegedHelperTools
[ ! -L "$base" ] || exit 1
/usr/bin/install -d -o root -g wheel -m 755 "$base"
[ "$(/usr/bin/stat -f %u "$base")" = 0 ] || exit 1
[ "$(/usr/bin/stat -f %Lp "$base")" = 755 ] || exit 1
dest='''+DEST+'''
if [ -e "$dest" ] || [ -L "$dest" ]; then
 [ "$replace" = yes ] || { echo 'Helper already exists; rerun with --replace after inspecting it.' >&2; exit 1; }
 [ ! -L "$dest" ] && [ -d "$dest" ] && [ "$(/usr/bin/stat -f %u "$dest")" = 0 ] || exit 1
else
 /usr/bin/install -d -o root -g wheel -m 755 "$dest"
fi
for file in '''+' '.join(names)+'''; do
 [ ! -L "$dest/$file" ] || exit 1
 /usr/bin/install -o root -g wheel -m 755 "$file" "$dest/$file"
done
[ ! -L /etc/sudoers.d ] || exit 1
/usr/bin/install -d -o root -g wheel -m 755 /etc/sudoers.d
rule=/etc/sudoers.d/n810-revival-flasher
if [ -e "$rule" ]; then
 [ "$replace" = yes ] && [ ! -L "$rule" ] && /usr/sbin/visudo -cf "$rule" || exit 1
fi
umask 077
tmp=$(/usr/bin/mktemp /etc/sudoers.d/n810-revival.XXXXXX)
trap '/bin/rm -f "$tmp"' EXIT
printf '%s ALL=(root) NOPASSWD: '''+DEST+'''/helper\\n' "$user" > "$tmp"
/usr/sbin/visudo -cf "$tmp"
/usr/bin/install -o root -g wheel -m 440 "$tmp" "$rule"
echo 'Installed N810 USB helper. No tablet was accessed.'
'''
    (output/'install.sh').write_text(installer)
    (output/'install.sh').chmod(0o700)
    print('Run once in Terminal: sudo /bin/sh '+str(output.resolve()/'install.sh'))
    print('For a verified prior installation: sudo /bin/sh '+str(output.resolve()/'install.sh')+' --replace')
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();prepare(a.build.resolve(),a.output.resolve())
