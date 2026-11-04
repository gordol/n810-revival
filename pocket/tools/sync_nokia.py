"""Sync a --files Nokia build; unchanged installed resources stay on the device."""
import argparse,json,re,shlex,subprocess
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('build',type=Path)
    parser.add_argument('--target',default='root@192.168.10.1')
    parser.add_argument('--ssh-key',type=Path)
    parser.add_argument('--control-path',type=Path)
    parser.add_argument('--basis',default='/usr/local/share/n810-pocket')
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.@-]+',args.target):parser.error('Expected an SSH host or user@host')
    if not args.basis.startswith('/') or not re.fullmatch(r'[A-Za-z0-9_./-]+',args.basis):parser.error('Expected an absolute basis directory')
    receipt=json.loads((args.build/'INSTALL.json').read_text())
    if receipt.get('transport')!='files':parser.error('Build with package_nokia.py --files first')
    stage=receipt['stage']
    if not re.fullmatch(r'/tmp/pocket-[0-9a-f]{12}-register',stage):parser.error('Unexpected staging directory')
    ssh=['ssh','-o','BatchMode=yes','-o','ConnectTimeout=60']
    if args.ssh_key:ssh+=['-i',str(args.ssh_key)]
    if args.control_path:ssh+=['-S',str(args.control_path)]
    # The running tree supplies unchanged files locally. Never write into it.
    subprocess.run([*ssh,args.target,'mkdir -p '+stage+'/files'],check=True)
    rsync=['rsync','-azc','--partial-dir=.rsync-partial','--delay-updates',
           '--chown=root:root','--chmod=D755,F644','-e',shlex.join(ssh)]
    subprocess.run([*rsync,'--stats','--copy-dest='+args.basis,
                    str(args.build/'files')+'/',args.target+':'+stage+'/files/'],check=True)
    subprocess.run([*rsync,'--exclude=files','--exclude=CONTENTS.json',
                    str(args.build)+'/',args.target+':'+stage+'/'],check=True)
    print('Files ready at '+stage+'; run its install.py through the normal desktop stop/restart.')


if __name__=='__main__':main()
