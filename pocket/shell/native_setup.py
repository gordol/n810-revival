# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native host/tablet setup guide with explicit local file preparation."""
from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
import select
import signal
import subprocess
import sys
import threading
import textwrap
from app_widgets import Canvas,TextInput


REPOSITORY=Path(__file__).resolve().parents[2]
BOOTSTRAP=REPOSITORY/'platform/bootstrap'
FLASHER=REPOSITORY/'dist/flasher/0xFFFF'
INTERNAL_BUILDER=BOOTSTRAP/'build_internal_image.py'
MAC_WRITER=BOOTSTRAP/'write_macos_internal.py'


class SecretInput(TextInput):
    def presentation(self,width,focused=True):
        visible=self.text
        try:
            self.text='*'*len(visible)
            return super().presentation(width,focused)
        finally:
            self.text=visible

    def draw(self,width):
        visible=self.text
        try:
            self.text='*'*len(visible)
            return super().draw(width)
        finally:
            self.text=visible


def _verify_built_kit(output,progress):
    if progress:progress('Build finished; verifying every kit file and the expanded root image…')
    sys.path.insert(0,str(BOOTSTRAP))
    from internal_installer import verify_local_kit
    installation,manifest,files=verify_local_kit(output)
    return dict(state='internal_kit_built',kind='n810-internal',release=installation['release'],
                files=[dict(role=role,path=path.name,bytes=path.stat().st_size) for role,path in files.items()],
                total_bytes=sum(path.stat().st_size for path in files.values()),
                kernel_release=manifest['kernel_release'],desktop_user='nokia',autostart=True,
                destination=str(output))


def _build_internal_kit(plan_path,destination,progress,cancelled):
    if sys.platform!='linux':raise RuntimeError('Build internal kits on a Linux host or VM with e2fsprogs installed')
    plan_path=Path(plan_path).expanduser()
    if plan_path.is_symlink() or not plan_path.is_file() or plan_path.stat().st_size>16384:
        raise ValueError('Choose a regular N810 internal build-plan JSON file')
    output=Path(destination).expanduser().absolute()
    argv=[sys.executable,str(INTERNAL_BUILDER),'--plan',str(plan_path.resolve()),'--output',str(output)]
    if os.geteuid()!=0:argv=['sudo','-n',*argv]
    if progress:progress('Building the ext4 root image and internal-install manifests on Linux…')
    try:
        process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,
                                 bufsize=1,start_new_session=True)
        output_lines=[]
        while process.poll() is None:
            if cancelled.is_set():
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise InterruptedError('Internal kit build cancelled; any partial output is private and can be removed')
            ready,_,_=select.select([process.stdout],[],[],.25)
            if ready:
                line=process.stdout.readline()
                if line:
                    output_lines.append(line.rstrip())
                    if progress:progress(line.rstrip()[:180])
        output_lines.extend(line.rstrip() for line in process.stdout)
        code=process.wait()
    except InterruptedError:
        raise
    except OSError as error:
        raise RuntimeError('Could not start the internal kit builder: '+str(error)) from error
    if code:
        tail='\n'.join(output_lines[-8:])
        if 'password is required' in tail:
            raise RuntimeError('Authorize the Linux build step first by running sudo -v in the launching terminal')
        raise RuntimeError('Internal kit build failed; its output folder may be partial. Choose a new folder to retry. '+tail[-400:])
    return _verify_built_kit(output,progress)


def _build_internal_source_kit(destination,ssh_key,password,progress,cancelled):
    output=Path(destination).expanduser().absolute()
    key=Path(ssh_key).expanduser().absolute()
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new kit folder below an existing directory')
    if not key.is_file() or key.is_symlink():
        raise ValueError('Choose a regular Ed25519 public key file')
    if not password or '\n' in password or '\r' in password:
        raise ValueError('Enter a local nokia password without a line break')
    argv=['make','--no-print-directory','n810-build-internal',
          'SSH_PUBLIC_KEY='+str(key),'INTERNAL_KIT='+str(output),'INTERNAL_PASSWORD_STDIN=1']
    if progress:progress('Building kernel, graphics, Debian and Pocket from tracked source…')
    process=subprocess.Popen(argv,cwd=REPOSITORY,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,start_new_session=True)
    try:
        process.stdin.write((password+'\n').encode());process.stdin.close()
        del password
        tail=bytearray()
        while True:
            if cancelled.is_set():
                os.killpg(process.pid,signal.SIGTERM)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL);process.wait()
                raise InterruptedError('Source kit build cancelled; remove any partial private output before retrying')
            ready,_,_=select.select([process.stdout],[],[],.25)
            if ready:
                chunk=os.read(process.stdout.fileno(),4096)
                if chunk:
                    tail.extend(chunk)
                    if len(tail)>4096:del tail[:-4096]
                    message=chunk.decode(errors='replace').replace('\r','\n').strip().split('\n')[-1]
                    if message and progress:progress(message[:180])
                elif process.poll() is not None:break
            elif process.poll() is not None:break
        if process.wait():
            raise RuntimeError('Source kit build failed; choose a new folder after inspecting the build. '+
                               tail.decode(errors='replace')[-400:])
    finally:
        process.stdout.close()
    return _verify_built_kit(output,progress)


def _mac_storage(action,kit,disk,usb_location,progress):
    if sys.platform!='darwin':raise RuntimeError('Maemo USB storage installation requires macOS')
    if not re.fullmatch(r'/dev/disk[0-9]+',disk):
        raise ValueError('Enter the new tablet whole disk as /dev/diskN')
    try:location=int(usb_location,0)
    except ValueError as error:raise ValueError('Enter the new tablet USB location as 0x...') from error
    if not 0<location<=0xffffffff:raise ValueError('Invalid USB location')
    argv=[sys.executable,str(MAC_WRITER),'--kit',str(kit),'--disk',disk,
          '--usb-location',hex(location)]
    if action=='mac-write':argv=['sudo','-n',*argv,'--write']
    if progress:progress('Checking the selected N810 disk and USB port…')
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                             text=True,bufsize=1)
    lines=[]
    for line in process.stdout:
        lines.append(line.rstrip())
        if progress:progress(line.rstrip()[:180])
    if process.wait():
        raise RuntimeError('Mac storage step failed: '+'\n'.join(lines[-6:])[-500:])
    return dict(state='mac_disk_checked' if action=='mac-check' else 'rootfs_written',
                device=disk,usb_location=location,
                rootfs_written=action=='mac-write',rootfs_readback_verified=action=='mac-write')


def _setup_work(action,manifest,destination,progress,cancelled,disk='',usb_location='',ssh_key='',password=''):
    if action=='identify':
        sys.path.insert(0,str(BOOTSTRAP))
        from internal_installer import identify_device
        return identify_device(FLASHER,progress)
    if action in ('check','prepare'):
        from n810_bootstrap import inspect,prepare
        if action=='prepare':return prepare(manifest,destination,progress,cancelled)
        result=inspect(manifest,progress,cancelled)
        if result['kind']!='n810-internal':return result
        sys.path.insert(0,str(BOOTSTRAP))
        from internal_installer import verify_local_kit
        installation,plan,files=verify_local_kit(Path(manifest).expanduser().parent)
        return dict(state='files_verified',kind='n810-internal',release=installation['release'],
                    files=[dict(role=role,path=path.name,bytes=path.stat().st_size) for role,path in files.items()],
                    total_bytes=sum(path.stat().st_size for path in files.values()),
                    kernel_release=plan['kernel_release'],desktop_user='nokia',autostart=True)
    if action=='kit':return _build_internal_kit(manifest,destination,progress,cancelled)
    if action=='source-kit':return _build_internal_source_kit(destination,ssh_key,password,progress,cancelled)
    if not manifest.strip():raise ValueError('Choose an internal INSTALLATION.json manifest first')
    sys.path.insert(0,str(BOOTSTRAP))
    if action in ('mac-check','mac-write'):
        return _mac_storage(action,Path(manifest).expanduser().parent,disk,usb_location,progress)
    from internal_installer import boot_installer,flash_kernel,install_root,install_device,install_macos
    kit=Path(manifest).expanduser().parent
    if action=='install' and sys.platform=='darwin':
        try:location=int(usb_location,0) if usb_location else 0
        except ValueError as error:raise ValueError('Enter the new tablet USB location as 0x...') from error
        from n810_flasher import build
        build(progress,cancelled)
        return install_macos(kit,disk,location,FLASHER,progress,cancelled)
    if action=='boot':return boot_installer(kit,FLASHER,progress)
    if action=='write':return install_root(kit,progress=progress)
    if action=='flash':return flash_kernel(kit,FLASHER,progress)
    if action=='install':return install_device(kit,FLASHER,progress=progress,cancelled=cancelled)
    raise ValueError('Unknown N810 setup action')


class N810Setup:
    def __init__(self):
        self.width=86;self.height=28
        default_manifest=Path(os.environ.get('N810_INSTALLATION_MANIFEST',str(REPOSITORY/'dist/n810-internal/INSTALLATION.json')))
        self.manifest=TextInput(str(default_manifest) if default_manifest.is_file() else '',limit=2048);self.destination=TextInput('',limit=2048)
        self.ssh_key=TextInput(str(Path.home()/'.ssh/id_ed25519.pub'),limit=2048)
        self.password=SecretInput('',limit=128)
        self.disk=TextInput('',limit=64);self.usb_location=TextInput('',limit=32)
        self.field='manifest';self.scroll=0;self._length=0;self._spans=();self._hits=[]
        self.result=None;self.tool_result=None;self.error='';self.status='Start at step 1 below. No disk or tablet is changed by opening Setup.'
        self.pool=None;self.pending=None;self.active_action=None;self.wakeup=None;self.closed=False;self.cancelled=threading.Event();self._session_callback=None
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def navigation_targets(self):
        from native_navigation import Target
        return [Target('manifest','Installation manifest','input'),Target('destination','New local kit folder','input'),
                Target('ssh_key','Ed25519 public key','input'),Target('password','Local nokia password','input'),
                Target('disk','New N810 whole disk','input'),Target('usb_location','New N810 USB location','input'),
                Target('check','Check files','action','v'),Target('install','Install Debian + Pocket','action','i'),Target('prepare','Prepare local kit','action','p'),
                Target('cancel','Cancel preparation','action','c'),Target('flasher','Build host flasher','action','b'),
                Target('source-kit','Build kit from source','action','g'),Target('kit','Build from plan','action','k'),
                Target('identify','Detect target','action','d'),Target('boot','Boot RAM installer','action','r'),
                Target('write','RAM installer: erase and write','action','w'),
                Target('mac-check','Check Mac N810 disk','action','m'),
                Target('mac-write','Write Mac N810 disk','action','x'),
                Target('flash','Flash kernel and reboot','action','f'),Target('steps','Setup steps','details')]
    def navigation_focus(self):return self.field
    def navigation_input(self,key):return {'manifest':self.manifest,'destination':self.destination,
                                            'ssh_key':self.ssh_key,'password':self.password,
                                            'disk':self.disk,'usb_location':self.usb_location}.get(key)
    def navigation_accept_input(self):return self.start('check')
    def changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:self.field=nav.target
        if self._session_callback:self._session_callback()
    def navigation_back(self):
        self.field='manifest'
        nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def poll_interval(self):return .1 if self.pending else None
    def start(self,action):
        if self.pending:self.status='A setup step is already running';return True
        if action=='flasher':return self.start_flasher()
        if action not in ('identify','source-kit') and not self.manifest.text.strip():self.error='Choose an internal INSTALLATION.json manifest first.';return True
        if action in ('prepare','kit','source-kit') and not self.destination.text.strip():self.error='Choose a new local kit folder first';return True
        if action=='source-kit' and (not self.ssh_key.text.strip() or not self.password.text):
            self.error='Enter an Ed25519 public key path and local nokia password first';return True
        if action in ('mac-check','mac-write') and (not self.disk.text.strip() or not self.usb_location.text.strip()):
            self.error='Enter the new N810 whole disk and USB location first';return True
        if action=='install' and sys.platform=='darwin' and not (Path(self.manifest.text).expanduser().parent/'INSTALL-STATE.json').is_file():
            if not self.disk.text.strip() or not self.usb_location.text.strip():
                self.error='Enter the new N810 whole disk and USB location before Install';return True
        self.error='';self.result=None;self.cancelled.clear()
        self.active_action=action
        labels={'check':'Verifying installation files…','prepare':'Preparing a local copy; tablet unchanged…',
                'install':'Starting the permanent internal installation…',
                'kit':'Building a private internal-install kit…',
                'source-kit':'Building a private kit from tracked source…','identify':'Identifying an N810 in update mode…',
                'boot':'Checking kit and booting the RAM installer…',
                'write':'Connecting to the RAM installer and preparing internal storage…',
                'flash':'Checking the write receipt and flashing the matching kernel…',
                'mac-check':'Checking the Mac disk and selected new-tablet USB port…',
                'mac-write':'Writing and reading back the selected new N810 internal disk…'}
        self.status=labels.get(action,'Working…')
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='n810-setup')
        manifest=self.manifest.text;destination=self.destination.text
        password=self.password.text if action=='source-kit' else ''
        self.password.text='';self.password.cursor=0
        def progress(message):
            if self.closed:return
            self.status=message
            if self.wakeup:self.wakeup()
        self.pending=self.pool.submit(_setup_work,action,manifest,destination,progress,self.cancelled,
                                      self.disk.text,self.usb_location.text,self.ssh_key.text,password)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda _:callback() if not self.closed else None)
        return True
    def start_flasher(self):
        from n810_flasher import build
        self.error='';self.tool_result=None;self.cancelled.clear();self.active_action='flasher'
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='n810-setup')
        def progress(message):
            if not self.closed:
                self.status=message
                if self.wakeup:self.wakeup()
        self.pending=self.pool.submit(build,progress,self.cancelled)
        callback=self.wakeup
        if callback:self.pending.add_done_callback(lambda _:callback() if not self.closed else None)
        return True
    def poll(self):
        if not self.pending or not self.pending.done():return False
        pending=self.pending;self.pending=None
        try:
            result=pending.result()
            if result['state']=='flasher_built':
                self.tool_result=result;self.status='Host flasher built. No tablet was accessed.';self.active_action=None;return True
            self.result=result
            state=result['state']
            if state=='internal_kit_built' and result.get('destination'):
                self.manifest.text=str(Path(result['destination'])/'INSTALLATION.json')
            self.status={
                'kit_prepared':'Local kit prepared. The tablet is not installed.',
                'internal_kit_built':'Internal kit built and verified. The tablet is not installed.',
                'files_verified':'Kit verified. Choose the Mac storage or RAM-installer path for the target.',
                'device_identified':'One Nokia N810 RX-44 is in update mode.',
                'mac_disk_checked':'The selected N810 disk and USB port match. No data was written.',
                'ram_installer_booted':'RAM installer booted; internal storage is unchanged. Choose Erase and write.',
                'rootfs_written':'Root image was read back successfully. Return this tablet to update mode, then flash its matching kernel.',
                'kernel_flashed_reboot_requested':'Matching kernel flash and reboot command completed. Watch the tablet for first boot.',
            }.get(state,'Setup step completed: '+state)
        except Exception as error:
            action=self.active_action
            self.error=str(error)[:512]
            if isinstance(error,InterruptedError):self.status='Install paused between device operations; inspect the kit receipt.' if action=='install' else 'Local preparation cancelled.'
            elif action in ('install','write','flash','mac-write'):self.status='Install step failed. The target may have changed; inspect it before retrying.'
            elif action=='boot':self.status='RAM boot failed; no internal write was requested.'
            else:self.status='Setup step unavailable; tablet unchanged.'
        self.active_action=None
        return True
    def key(self,key):
        if key=='i':return self.start('install')
        if key=='b':return self.start('flasher')
        if key=='k':return self.start('kit')
        if key=='g':return self.start('source-kit')
        if key=='v':return self.start('check')
        if key=='p':return self.start('prepare')
        if key=='d':return self.start('identify')
        if key=='r':return self.start('boot')
        if key=='w':return self.start('write')
        if key=='m':return self.start('mac-check')
        if key=='x':return self.start('mac-write')
        if key=='f':return self.start('flash')
        if key=='c':
            if self.pending and self.active_action=='install':
                self.cancelled.set();self.status='Pausing after the current device operation completes…';return True
            if self.pending and self.active_action in ('check','prepare','kit','source-kit','flasher'):
                self.cancelled.set();self.status='Cancelling local preparation…'
            elif self.pending:self.status='This device operation is in progress; wait for its result.'
            else:self.status='No preparation is running'
            return True
        if key in ('up','down','pageup','pagedown','home','end'):
            self.scroll=0 if key=='home' else self._length if key=='end' else max(0,self.scroll+(-1 if key in ('up','pageup') else 1)*(max(1,self.height//2) if key in ('pageup','pagedown') else 1));return True
        return False
    def body(self):
        result=self.result;rows=[]
        if self.tool_result:rows+=['HOST FLASHER READY',self.tool_result['binary'],'Built from pinned upstream source. USB flashing remains an explicit separate action.','']
        if result:
            if result.get('kind'):
                rows += ['VERIFIED '+result['release'],'Kind: '+result['kind'],str(len(result['files']))+' files · '+str(result['total_bytes'])+' bytes']
                rows += [row['role']+': '+row['path'] for row in result['files']]
                if result.get('destination'):rows+=['Kit folder: '+result['destination']]
            else:
                rows += ['INSTALL STEP: '+result['state']]
                if result.get('model'):rows += ['Target model: '+result['model']]
                if result.get('kernel_release'):rows += ['Matching kernel: '+result['kernel_release']]
                if result.get('internal_storage_changed') is False:rows += ['Internal storage is unchanged.']
                if result.get('rootfs_written'):rows += ['Internal root written and readback verified.']
            rows += ['',self.status,'']
        if not result or result.get('kind')=='n810-internal':
            return rows+['N810 INTERNAL INSTALLATION',
                'Install Debian and Pocket on internal MMC. No SD card is needed.',
                'Choose Check files. On macOS, Install writes the selected Maemo USB disk, waits for update mode, then flashes the matching kernel.',
                'For a new kit, enter a new output folder, SSH public key and local password; choose Build kit from source.',
                'Build from plan accepts reviewed prebuilt Linux inputs as an advanced path.',
                'For an existing kit, enter its INSTALLATION.json and choose Check files.',
                'Build host flasher creates pinned 0xFFFF on this computer.',
                'On macOS, boot stock Maemo and export its internal USB storage; enter its whole disk and USB location above.',
                'Check Mac N810 disk validates both identities without writing. Write Mac N810 disk erases and reads back all 2 GB.',
                'The RAM-installer path uses Detect target and Boot RAM installer; its physical install remains unaccepted.',
                'Erase and write requires the RAM installer identity, one internal MMC and full root readback.',
                'After the root write, return the same tablet to update mode and flash the matching kernel.',
                'The final flash command reboots the tablet; first-boot desktop acceptance is checked separately.',
                'Keep the target battery installed and charger connected throughout the install.']
        rows += ['FRESH DEBIAN TEST — FOLLOW THESE STEPS IN ORDER',
                 '1. Build a private image on the host. From the repository root in a terminal:',
                 '   make sd-image SSH_PUBLIC_KEY="$HOME/.ssh/id_ed25519.pub" SD_SIZE_MIB=4096',
                 '   Choose the new nokia account password at the local prompt. The output is dist/n810-sd/. Keep it private.',
                 '2. Enter dist/n810-sd/INSTALLATION.json above and choose Check files. This verifies the image, matching kernel, modules and boot guide.',
                 '   Prepare local kit is an optional copy for a kit obtained elsewhere. It does not build or install Debian.',
                 '3. Identify the removable SD card on the Mac with diskutil list. The card writer verifies its size, type and image checksum. Replace N with its current whole-disk number:',
                 '   make sd-card-check SD_CARD=diskN',
                 '   make sd-card-write SD_CARD=diskN',
                 '   The second command erases the card after an explicit ERASE diskN confirmation. It does not touch the N810.',
                 '4. Put that card in the target N810. Before kernel flash, verify that the built-in root path names this removable card, not internal eMMC. Enter Nokia update mode. On Linux with 0xFFFF, confirm RX-44, then install the matching kernel:',
                 '   sudo 0xFFFF -I',
                 '   sudo 0xFFFF -m kernel:dist/n810-sd/n810-kernel-ramboot.bin -f -r',
                 '   Kernel flash changes NAND boot state. It does not repartition internal eMMC; the new root remains on the removable card.',
                 '5. On the tablet: complete touch setup, log in with the password from step 1, verify kernel/modules and USB networking, then Wi-Fi and Bluetooth.',
                 '   Pocket and large map/FCC data are separate installs after Debian boots. The first hardware trial is not a complete Pocket installation.',
                 '', 'THIS SCREEN',
                 'Check files verifies local sizes, SHA-256 and matching release. It cannot identify a disk, write a card, flash a kernel or prove hardware boot.',
                 'The system-image builder currently selects /dev/mmcblk0p1 as root. Confirm removable-card enumeration on the target before relying on that boot path.']
        return rows
    def lines(self):
        self.poll();c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'N810 Setup · host / tablet installation preparation');self._spans.append((0,0,self.width,'toolbar'))
        mac_fields=self.field in ('disk','usb_location','mac-check','mac-write') or (self.field=='install' and sys.platform=='darwin')
        source_fields=self.field in ('ssh_key','password','source-kit')
        fields=((1,'disk','New N810 disk (macOS /dev/diskN)',self.disk),
                (3,'usb_location','New N810 USB port (0x...)',self.usb_location)) if mac_fields else ((
                (1,'ssh_key','Ed25519 public key file',self.ssh_key),
                (3,'password','Local nokia password (hidden)',self.password)) if source_fields else (
                (1,'manifest','Installation manifest or build plan',self.manifest),
                (3,'destination','New local kit folder',self.destination)))
        for y,key,label,field in fields:
            c.put(0,y,label);c.put(0,y+1,field.draw(self.width));self._hits.append((y+1,key))
            self._spans.append((y+1,0,self.width,'input' if self.field==key else 'muted'))
        controls=[('check','Check files'),('install','Install Debian + Pocket'),
                  ('prepare','Prepare local kit'),('cancel','Cancel'),('flasher','Build host flasher'),
                  ('source-kit','Build kit from source'),('kit','Build from plan'),('identify','Detect target'),('boot','Boot RAM installer'),
                  ('write','RAM installer: erase + write'),('mac-check','Check Mac N810 disk'),
                  ('mac-write','Write Mac N810 disk'),('flash','Flash kernel + reboot')]
        visible=max(2,min(6,self.height-10))
        selected=next((i for i,item in enumerate(controls) if item[0]==self.field),0)
        first=max(0,min(selected-visible+1,len(controls)-visible))
        for index,(key,label) in enumerate(controls[first:first+visible]):
            row=6+index;text='[ '+label+' ]'
            c.put(0,row,text);self._hits.append((row,key,0,min(len(text),self.width)))
            self._spans.append((row,0,min(len(text),self.width),'selected' if self.field==key else 'toolbar'))
        body=[]
        for line in self.body():body.extend(textwrap.wrap(line,max(1,self.width-1)) or [''])
        self._length=len(body);start=6+visible;room=max(0,self.height-start-2);offset=min(self.scroll,max(0,len(body)-room))
        for i,line in enumerate(body[offset:offset+room]):c.put(0,start+i,line)
        c.put(0,self.height-2,self.error or self.status)
        c.put(0,self.height-1,'Tab / Shift-Tab controls · arrows scroll steps · Enter activate · Esc back')
        return c.lines()
    def spans(self):return tuple(self._spans)
    def pointer(self,column,row,width,button=0,released=False):
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        for hit in self._hits:
            if row==hit[0] and (len(hit)==2 or hit[2]<=column<hit[2]+hit[3]):
                self.field=hit[1];nav=self.__dict__.get('_navigation')
                if nav:nav.target=self.field
                if len(hit)>2:return self.key({'check':'v','prepare':'p','cancel':'c','flasher':'b','kit':'k','source-kit':'g',
                    'identify':'d','boot':'r','write':'w','mac-check':'m','mac-write':'x',
                    'flash':'f','install':'i'}[self.field])
                return True
        self.field='steps';nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def session_state(self):return dict(manifest=self.manifest.text,destination=self.destination.text,
                                        ssh_key=self.ssh_key.text,disk=self.disk.text,usb_location=self.usb_location.text)
    def restore_session(self,state):
        for key in ('manifest','destination','ssh_key','disk','usb_location'):
            value=state.get(key)
            if isinstance(value,str) and len(value)<=2048:setattr(self,key,TextInput(value,limit=2048))
    def help_pages(self):
        return (('N810 Setup',('To build a new kit, enter a new local folder, your Ed25519 public key path and a local nokia password. Build kit from source uses the same n810-build-internal Make target as the CLI. Docker must be running.',
                 'The password is hidden, sent to the local builder through stdin, and cleared from the form when building starts. The private kit contains its password hash and SSH access material.',
                 'Build from plan is the advanced Linux path. Enter a build-plan JSON naming root, kernel_package, gpu_runtime, gpu_module_package and gpu_mesa_package; recovery is optional for the RAM-installer path.',
                 'After a kit is built, Check files validates the root, matching kernel and GPU Pocket autostart as nokia. It also checks a RAM installer when one is included.',
                 'Prepare local kit makes a verified copy. Build host flasher runs the pinned make flasher build and does not open USB.',
                 'Build kit from source runs on macOS or Linux with Docker. Build from plan runs on Linux; run sudo -v in the launching terminal first. On macOS, run sudo -v before Detect target, Boot RAM installer or Flash kernel. Detection uses read-only 0xFFFF -I and accepts RX-44 only.',
                 'On macOS, stock Maemo can export its internal MMC as a whole USB disk. Enter /dev/diskN and the new tablet USB location shown by macOS; Check Mac N810 disk performs identity checks. Write Mac N810 disk erases and fully reads back that disk, then saves a receipt for Flash kernel. Run sudo -v in the launching terminal first.',
                 'On macOS, Install Debian + Pocket runs that guarded write and full readback, waits for you to return the same tablet to update mode, then flashes the matching kernel. A saved receipt lets Install resume after an interrupted wait.',
                 'Boot RAM installer loads the verified kernel and initramfs with 0xFFFF -l -b. It does not flash internal storage.',
                 'Erase and write internal storage replaces the target N810 MMC. The installer verifies the MMC model, capacity and CID, then reads back the root image checksum.',
                 'After the root write, return the same tablet to Nokia update mode. Flash kernel writes the matching kernel with 0xFFFF -f -r and reboots it.',
                 'A successful flash command is not proof of first boot. Confirm the graphical Pocket desktop starts as nokia on the target. Keep the original tablet in normal Linux mode.',
                 'Install Debian + Pocket runs the stages in order and waits for the pinned USB installer at 169.254.81.1. After root readback it powers off the new tablet; hold Home while powering it on to return to update mode. The saved receipt allows resuming before the permanent kernel flash.')),)
    def close(self):
        self.password.text='';self.password.cursor=0
        self.closed=True;self.wakeup=None;self.cancelled.set()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
