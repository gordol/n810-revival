# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native host/tablet setup guide with explicit local file preparation."""
from concurrent.futures import ThreadPoolExecutor
import os
import json
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


def _local_internal_manifests():
    """Discover local outputs; selecting one never substitutes for verification."""
    found=[]
    for path in (REPOSITORY/'dist').glob('*/INSTALLATION.json'):
        try:
            if path.is_symlink() or path.parent.is_symlink() or path.stat().st_size>65536:continue
            data=json.loads(path.read_text())
            if isinstance(data,dict) and data.get('version')==1 and data.get('kind')=='n810-internal' and data.get('files'):
                found.append(path)
        except (OSError,ValueError):continue
    for path in (REPOSITORY/'dist').glob('*/AB.json'):
        try:
            if not path.is_symlink() and path.stat().st_size<=65536 and json.loads(path.read_text()).get('kind')=='n810-ab-kit':found.append(path)
        except (OSError,ValueError):pass
    return sorted(found,key=lambda path:(path.stat().st_mtime_ns,str(path)),reverse=True)


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
    if (Path(output)/'AB.json').is_file():
        from native_setup_ab import verify
        result=verify(output,progress);result['state']='ab_kit_built';return result
    sys.path.insert(0,str(BOOTSTRAP))
    from internal_installer import verify_local_kit
    installation,manifest,files=verify_local_kit(output)
    return dict(state='internal_kit_built',kind='n810-internal',release=installation['release'],
                files=[dict(role=role,path=path.name,bytes=path.stat().st_size) for role,path in files.items()],
                total_bytes=sum(path.stat().st_size for path in files.values()),
                storage_target=manifest.get('storage_target','internal'),kernel_release=manifest['kernel_release'],desktop_user='nokia',autostart=True,
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


def _build_internal_source_kit(destination,ssh_key,password,progress,cancelled,setup=None):
    password = password or 'nokia'
    setup=dict(setup or {})
    reference={name:setup.pop(name,None) for name in ('reference_data','reference_maps')}
    if any(reference.values()) and setup.get('storage_target')!='sd-ab':raise ValueError('Reference-data seeding requires an SD A/B kit')
    if reference['reference_maps'] and not reference['reference_data']:raise ValueError('Choose the offline data folder before separate map views')
    output=Path(destination).expanduser().absolute()
    key=Path(ssh_key).expanduser().absolute()
    if output.parent==REPOSITORY/'dist':output.parent.mkdir(exist_ok=True)
    if output.exists() or not output.parent.is_dir():
        raise ValueError('Choose a new kit folder below an existing directory')
    if not key.is_file() or key.is_symlink():
        raise ValueError('Choose an Ed25519 public key file. To create one, run ssh-keygen -t ed25519 in your terminal; see ? Help.')
    if not password or '\n' in password or '\r' in password:
        raise ValueError('Enter a local nokia password without a line break')
    argv=['make','--no-print-directory','n810-build-internal',
          'SSH_PUBLIC_KEY='+str(key),'INTERNAL_KIT='+str(output),'INTERNAL_PASSWORD_STDIN=1','INTERNAL_SETUP_STDIN=1','N810_STORAGE='+str((setup or {}).get('storage_target','internal'))]
    if (setup or {}).get('storage_target')=='sd-ab':
        argv=[sys.executable,str(BOOTSTRAP/'build_ab_host.py'),'--output',str(output),'--ssh-key',str(key),'--setup-stdin']
        for name,value in reference.items():
            if value:argv.extend(['--'+name.replace('_','-'),str(Path(value).expanduser().absolute())])
    if progress:progress('Building kernel, graphics, Debian and Pocket from tracked source…')
    process=subprocess.Popen(argv,cwd=REPOSITORY,stdin=subprocess.PIPE,stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT,start_new_session=True)
    try:
        process.stdin.write((password+'\n'+json.dumps(setup or {})+'\n').encode());process.stdin.close()
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
    if sys.platform.startswith('linux'):
        argv=[sys.executable,str(BOOTSTRAP/'linux_storage.py'),'--kit',str(kit),
              '--disk',disk,'--usb-port',usb_location]
        if action=='mac-write':argv=['sudo','-n',*argv,'--write']
        process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        lines=[]
        for line in process.stdout:
            lines.append(line.rstrip())
            if progress:progress(line.rstrip()[:180])
        if process.wait():raise RuntimeError('Linux storage step failed: '+'\n'.join(lines[-6:]))
        return dict(state='linux_disk_checked' if action=='mac-check' else 'rootfs_written',
                    device=disk,usb_port=usb_location,rootfs_readback_verified=action=='mac-write')
    if sys.platform!='darwin':raise RuntimeError('Maemo USB storage installation requires macOS')
    if not re.fullmatch(r'/dev/disk[0-9]+',disk):
        raise ValueError('Enter the new tablet whole disk as /dev/diskN')
    try:location=int(usb_location,0)
    except ValueError as error:raise ValueError('Enter the new tablet USB location as 0x...') from error
    if not 0<location<=0xffffffff:raise ValueError('Invalid USB location')
    sd=json.loads((Path(kit)/'INTERNAL.json').read_text()).get('storage_target')=='sd'
    writer=BOOTSTRAP/'write_sd_card.py' if sd else MAC_WRITER
    argv=[sys.executable,str(writer),'--kit',str(kit),'--disk',disk,
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
                storage_target='sd' if sd else 'internal',rootfs_written=action=='mac-write',rootfs_readback_verified=action=='mac-write')


def _setup_work(action,manifest,destination,progress,cancelled,disk='',usb_location='',ssh_key='',password='',setup=None):
    if action=='identify':
        sys.path.insert(0,str(BOOTSTRAP))
        from internal_installer import identify_device
        return identify_device(FLASHER,progress)
    from native_setup_ab import selected as ab_selected,work as ab_work
    if ab_selected(manifest) and action not in ('source-kit','kit'):
        return ab_work(action,manifest,disk,ssh_key,FLASHER,progress,cancelled)
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
                    storage_target=plan.get('storage_target','internal'),kernel_release=plan['kernel_release'],desktop_user='nokia',autostart=True)
    if action=='kit':return _build_internal_kit(manifest,destination,progress,cancelled)
    if action=='source-kit':return _build_internal_source_kit(destination,ssh_key,password,progress,cancelled,setup)
    if not manifest.strip():raise ValueError('Choose an internal INSTALLATION.json manifest first')
    sys.path.insert(0,str(BOOTSTRAP))
    if action in ('mac-check','mac-write'):
        return _mac_storage(action,Path(manifest).expanduser().parent,disk,usb_location,progress)
    from internal_installer import boot_installer,flash_kernel,install_root,install_device,install_macos
    kit=Path(manifest).expanduser().parent
    if action=='install' and json.loads((kit/'INTERNAL.json').read_text()).get('storage_target')=='sd':
        return _mac_storage('mac-write',kit,disk,usb_location,progress)
    if action=='install' and sys.platform.startswith('linux'):
        return _mac_storage('mac-write',kit,disk,usb_location,progress)
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
    navigation_help_keys=('?','help')
    def __new__(cls):
        if Path('/etc/n810-image/bootstrap.json').is_file() and os.uname().machine.startswith('arm'):
            from native_device_setup import DeviceSetup
            return DeviceSetup()
        return super().__new__(cls)
    def __init__(self):
        self.width=86;self.height=28
        self.local_kits=_local_internal_manifests()
        self._explicit_manifest=bool(os.environ.get('N810_INSTALLATION_MANIFEST'))
        default_manifest=Path(os.environ['N810_INSTALLATION_MANIFEST']) if self._explicit_manifest else (self.local_kits[0] if self.local_kits else None)
        self.manifest=TextInput(str(default_manifest) if default_manifest else '',limit=2048)
        output=REPOSITORY/'dist/n810-internal';index=2
        while output.exists():
            output=REPOSITORY/f'dist/n810-internal-{index}';index+=1
        self.destination=TextInput(str(output),limit=2048)
        self.ssh_key=TextInput(str(Path.home()/'.ssh/id_ed25519.pub'),limit=2048)
        self.password=SecretInput('nokia',limit=128)
        from setup_choices import SetupChoices
        self.choices=SetupChoices();self.options_open=False
        self.disk=TextInput('',limit=64);self.usb_location=TextInput('',limit=32)
        self.field='manifest';self.scroll=0;self._length=0;self._spans=();self._hits=[]
        self.result=None;self.tool_result=None;self.error=''
        self.status='Kit selected. Choose Check files before installation.' if default_manifest else 'No local kit found. Choose Build kit from source.'
        self.pool=None;self.pending=None;self.active_action=None;self.wakeup=None;self.closed=False;self.cancelled=threading.Event();self._session_callback=None
    def bind_wakeup(self,callback):self.wakeup=callback
    def bind_session(self,callback):self._session_callback=callback
    def navigation_targets(self):
        from native_navigation import Target
        if self.options_open:return self.choices.targets()
        targets=[Target('manifest','Installation manifest','input'),Target('destination','New local kit folder','input'),
                Target('ssh_key','Ed25519 public key','input'),Target('password','Local nokia password','input'),
                Target('disk','New N810 whole disk','input'),Target('usb_location','New N810 USB location','input'),
                Target('check','Check files','action','v'),Target('install','Install Debian + Pocket','action','i'),Target('prepare','Prepare local kit','action','p'),
                Target('cancel','Cancel preparation','action','c'),Target('flasher','Build host flasher','action','b'),
                Target('source-kit','Build kit from source','action','g'),Target('kit','Build from plan','action','k'),
                Target('identify','Detect target','action','d'),Target('boot','Boot SD installer','action','r'),
                Target('write','SD installer: erase and write','action','w'),
                Target('mac-check','Check target disk','action','m'),
                Target('mac-write','Write target disk','action','x'),
                Target('flash','Flash kernel and reboot','action','f')]+([
                Target('next-kit','Choose another local kit','action','next-kit')] if len(self.local_kits)>1 else [])+[
                Target('options','Storage, Wi-Fi and startup choices','action','o'),Target('steps','Setup results','details')]
        from native_setup_ab import selected as ab_selected
        if ab_selected(self.manifest.text):
            targets=[t._replace(title='Install next A/B step') if t.key=='install' else t for t in targets if t.key not in ('prepare','kit')]
        return targets
    def navigation_focus(self):return self.choices.field if self.options_open else self.field
    def navigation_input(self,key):
        if self.options_open:return self.choices.input(key)
        return {'manifest':self.manifest,'destination':self.destination,
                                            'ssh_key':self.ssh_key,'password':self.password,
                                            'disk':self.disk,'usb_location':self.usb_location}.get(key)
    def navigation_accept_input(self):return True if self.options_open else self.start('check')
    def changed(self):
        nav=self.__dict__.get('_navigation')
        if nav:
            if self.options_open:self.choices.field=nav.target
            else:self.field=nav.target
        if self._session_callback:self._session_callback()
    def navigation_back(self):
        if self.options_open:
            self.options_open=False;self.field='options'
            nav=self.__dict__.get('_navigation')
            if nav:nav.target=self.field
            return True
        self.field='manifest'
        nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def poll_interval(self):return .1 if self.pending else None
    def start(self,action):
        if self.pending:self.status='A setup step is already running';return True
        if action=='next-kit':
            paths=[str(path) for path in self.local_kits]
            if paths:
                index=paths.index(self.manifest.text) if self.manifest.text in paths else -1
                self.manifest=TextInput(paths[(index+1)%len(paths)],limit=2048)
                self.result=None;self.error='';self.status='Local kit selected. Choose Check files before installation.'
                if self._session_callback:self._session_callback()
            return True
        if action=='flasher':return self.start_flasher()
        if action not in ('identify','source-kit') and not self.manifest.text.strip():self.error='Choose an INSTALLATION.json manifest first.';return True
        if action in ('prepare','kit','source-kit') and not self.destination.text.strip():self.error='Choose a new local kit folder first';return True
        if action=='source-kit' and not self.ssh_key.text.strip():
            self.error='Enter an Ed25519 public key path first';return True
        from native_setup_ab import selected as ab_selected
        is_ab=ab_selected(self.manifest.text)
        if action in ('mac-check','mac-write') and (not self.disk.text.strip() or (not is_ab and not self.usb_location.text.strip())):
            self.error='Enter the new N810 whole disk and USB location first';return True
        if action=='install' and not is_ab and sys.platform=='darwin' and not (Path(self.manifest.text).expanduser().parent/'INSTALL-STATE.json').is_file():
            if not self.disk.text.strip() or not self.usb_location.text.strip():
                self.error='Enter the new N810 whole disk and USB location before Install';return True
        self.error='';self.result=None;self.cancelled.clear()
        self.active_action=action
        labels={'check':'Verifying installation files…','prepare':'Preparing a local copy; tablet unchanged…',
                'install':'Preparing the selected storage installation…',
                'kit':'Building a private internal-install kit…',
                'source-kit':'Building a private kit from tracked source…','identify':'Identifying an N810 in update mode…',
                'boot':'Checking kit and booting the SD installer…',
                'write':'Connecting to the SD installer and preparing internal storage…',
                'flash':'Checking the write receipt and flashing the matching kernel…',
                'mac-check':'Checking the selected target disk…',
                'mac-write':'Writing and reading back the selected target disk…'}
        self.status=labels.get(action,'Working…')
        if self.pool is None:self.pool=ThreadPoolExecutor(max_workers=1,thread_name_prefix='n810-setup')
        manifest=self.manifest.text;destination=self.destination.text
        try:setup=self.choices.profile() if action=='source-kit' else None
        except ValueError as error:
            self.error=str(error);return True
        password=self.password.text if action=='source-kit' else ''
        if action=='source-kit':self.choices.wifi_pass.text='';self.choices.wifi_pass.cursor=0
        self.password.text='';self.password.cursor=0
        def progress(message):
            if self.closed:return
            self.status=message
            if self.wakeup:self.wakeup()
        self.pending=self.pool.submit(_setup_work,action,manifest,destination,progress,self.cancelled,
                                      self.disk.text,self.usb_location.text,self.ssh_key.text,password,setup)
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
            if state in ('internal_kit_built','ab_kit_built') and result.get('destination'):
                self.manifest.text=str(Path(result['destination'])/('AB.json' if state=='ab_kit_built' else 'INSTALLATION.json'))
            self.status={
                'ab_kit_built':'A/B kit built and verified. Select the SD card, then Install.',
                'sd_ab_written':'SD card verified and ejected. Insert it into the intended tablet, enter update mode, then choose Install again to boot the SD installer.',
                'sd_boot_requested':'Temporary SD kernel loaded. Once USB networking is ready, choose Install again to write internal recovery.',
                'recovery_written':'Internal recovery verified. Leave the SD inserted, return the tablet to update mode on the same port, then choose Install to flash recovery.',
                'recovery_kernel_flashed':'Recovery kernel flashed. Watch the tablet boot its selected SD slot.',
                'kit_prepared':'Local kit prepared. The tablet is not installed.',
                'internal_kit_built':'Kit built and verified. The tablet is not installed.',
                'files_verified':'Kit verified. Check and write the selected storage, then flash the matching kernel.',
                'device_identified':'One Nokia N810 RX-44 is in update mode.',
                'mac_disk_checked':'The selected disk checks passed. No data was written.',
                'linux_disk_checked':'The selected disk checks passed. No data was written.',
                'ram_installer_booted':'SD installer booted; internal storage is unchanged. Choose Erase and write.',
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
        if key=='o' and not self.pending:
            self.options_open=True;self.choices.field='wifi_ssid'
            nav=self.__dict__.get('_navigation')
            if nav:nav.target='wifi_ssid'
            return True
        if self.options_open:
            if key in ('options-done','escape','\x1b'):
                return self.navigation_back()
            return self.choices.key(key)
        if key=='next-kit':return self.start('next-kit')
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
        if not self.manifest.text.strip():
            rows+=['No installation kit has been built here.',
                   'Choose your SSH public key and Build kit from source. The build creates the image, matching kernel and installation manifest.',
                   'Docker must be running. Press ? for prerequisites and SSH key setup.']
        elif len(self.local_kits)>1 and not result:
            rows += [f'{len(self.local_kits)} local kits found. Use Choose another local kit to change the selection.']
        if self.tool_result:rows+=['HOST FLASHER READY',self.tool_result['binary'],'Built from pinned upstream source. USB flashing remains an explicit separate action.','']
        if result:
            rows += ['Root storage: '+({'sd':'SD card','sd-ab':'SD A/B + internal recovery'}.get(result.get('storage_target'),'internal MMC'))]
            if result.get('kind'):
                rows += ['VERIFIED '+result['release'],'Kind: '+result['kind'],str(len(result['files']))+' files · '+str(result['total_bytes'])+' bytes']
                rows += [row['role']+': '+row['path'] for row in result['files']]
                if result.get('destination'):rows+=['Kit folder: '+result['destination']]
            else:
                rows += ['INSTALL STEP: '+result['state']]
                if result.get('model'):rows += ['Target model: '+result['model']]
                if result.get('kernel_release'):rows += ['Matching kernel: '+result['kernel_release']]
                if result.get('internal_storage_changed') is False:rows += ['Internal storage is unchanged.']
                if result.get('rootfs_written'):rows += ['Selected root written and readback verified.']
            rows += ['',self.status,'']
        return rows
    def lines(self):
        if self.options_open:
            self.choices.width,self.choices.height=self.width,self.height
            return self.choices.lines()
        self.poll();c=Canvas(self.width,self.height);self._hits=[];self._spans=[]
        c.put(0,0,'N810 Setup · Debian + Pocket · ? Help')
        self._spans.append((0,0,self.width,'toolbar'))
        fields=(('manifest','Installation manifest or build plan',self.manifest),
                ('destination','New local kit folder',self.destination),
                ('ssh_key','Ed25519 public key file',self.ssh_key),
                ('password','Local nokia password (hidden)',self.password),
                ('disk','Target whole disk (/dev/sdX)' if sys.platform.startswith('linux') else 'New N810 disk (macOS /dev/diskN)',self.disk),
                ('usb_location','Tablet USB port (1-2.3)' if sys.platform.startswith('linux') else 'New N810 USB port (0x...)',self.usb_location))
        rows=[];spans=[];hits=[];focus=0
        for key,label,field in fields:
            if self.field==key:focus=len(rows)
            rows.append(label)
            text,roles=field.presentation(self.width,focused=self.field==key)
            row=len(rows);rows.append(text);hits.append((row,key))
            spans.extend((row,x,length,role) for x,length,role in roles)
        controls=[('check','Check files'),('install','Install Debian + Pocket'),
                  ('prepare','Prepare local kit'),('cancel','Cancel'),('flasher','Build host flasher'),
                  ('source-kit','Build kit from source'),('kit','Build from plan'),('options','Storage, Wi-Fi and startup choices'),('identify','Detect target'),('boot','Boot SD installer'),
                  ('write','SD installer: erase + write'),('mac-check','Check target disk'),
                  ('mac-write','Write target disk'),('flash','Flash kernel + reboot')]
        from native_setup_ab import selected as ab_selected
        if ab_selected(self.manifest.text):controls=[(key,('Install next A/B step' if key=='install' else label)) for key,label in controls if key not in ('prepare','kit')]
        if len(self.local_kits)>1:controls.append(('next-kit','Choose another local kit'))
        rows.append('');row=len(rows);rows.append('');column=0
        for key,label in controls:
            text='[ '+label+' ]'
            if column and column+len(text)>self.width:
                row=len(rows);rows.append('');column=0
            if self.field==key:focus=row
            rows[row]+=' '*max(0,column-len(rows[row]))+text
            length=min(len(text),max(0,self.width-column))
            hits.append((row,key,column,column+length))
            spans.append((row,column,length,'selected' if self.field==key else 'toolbar'))
            column+=len(text)+2
        rows.append('')
        if self.field=='steps':focus=len(rows)
        for line in self.body():rows.extend(textwrap.wrap(line,max(1,self.width-1)) or [''])
        self._length=len(rows);room=max(1,self.height-3)
        if self.field!=getattr(self,'_layout_focus',None):
            if focus<self.scroll:self.scroll=focus
            elif focus+1>=self.scroll+room:self.scroll=focus+2-room
            self._layout_focus=self.field
        offset=min(self.scroll,max(0,len(rows)-room));self.scroll=offset
        for i,line in enumerate(rows[offset:offset+room]):c.put(0,i+1,line)
        for row,*hit in hits:
            if offset<=row<offset+room:self._hits.append((row-offset+1,*hit))
        for row,x,length,role in spans:
            if offset<=row<offset+room:self._spans.append((row-offset+1,x,length,role))
        c.put(0,self.height-2,self.error or self.status)
        c.put(0,self.height-1,'Tab / Shift-Tab focus · Enter activate · ? Help · Esc back')
        return c.lines()
    def spans(self):return tuple(self.choices._spans if self.options_open else self._spans)
    def pointer(self,column,row,width,button=0,released=False):
        if self.options_open:
            if released or button:return False
            for y,key in self.choices._hits:
                if row==y:
                    self.choices.field=key
                    nav=self.__dict__.get('_navigation')
                    if nav:nav.target=key
                    if key=='storage-target':return self.key('toggle-storage')
                    if key.startswith('toggle-') or key=='options-done':return self.key(key)
                    return True
            return False
        if released:return False
        if button&64:return self.key('down' if button&1 else 'up')
        if button!=0:return False
        for hit in self._hits:
            if row==hit[0] and (len(hit)==2 or hit[2]<=column<hit[2]+hit[3]):
                self.field=hit[1];nav=self.__dict__.get('_navigation')
                if nav:nav.target=self.field
                if self.field=='next-kit':return self.start('next-kit')
                if len(hit)>2:return self.key({'check':'v','prepare':'p','cancel':'c','flasher':'b','kit':'k','source-kit':'g',
                    'identify':'d','boot':'r','write':'w','mac-check':'m','mac-write':'x',
                    'flash':'f','install':'i','options':'o'}[self.field])
                return True
        self.field='steps';nav=self.__dict__.get('_navigation')
        if nav:nav.target=self.field
        return True
    def session_state(self):return dict(manifest=self.manifest.text,destination=self.destination.text,
                                        ssh_key=self.ssh_key.text,disk=self.disk.text,usb_location=self.usb_location.text,setup=self.choices.public_state())
    def restore_session(self,state):
        self.choices.restore(state.get('setup',{}))
        for key in ('manifest','destination','ssh_key','disk','usb_location'):
            if key=='manifest' and self._explicit_manifest:continue
            value=state.get(key)
            if key=='manifest' and (not isinstance(value,str) or not Path(value).expanduser().is_file()):continue
            if key=='destination' and not value:continue
            if isinstance(value,str) and len(value)<=2048:setattr(self,key,TextInput(value,limit=2048))
    def help_pages(self):
        from native_setup_ab import selected as ab_selected
        if ab_selected(self.manifest.text) or self.choices.storage_target=='sd-ab':
            return (('SD A/B installation',(
                'Choose SD A/B + internal recovery in Storage, Wi-Fi and startup choices. Set the SSH public key, hidden account password, and optional Wi-Fi settings, then Build kit from source.',
                'Builds need Python 3.11+, Make, Git, tar and Docker: at least 4 GiB Docker RAM, 30 GiB Docker storage, and 6 GiB output space. With Docker Desktop reserve 40 GiB host free space.',
                'Check files verifies the complete kit. Enter the removable card whole disk. Authorize disk access with sudo -v in the terminal launching Pocket.',
                'Install next A/B step writes and verifies the SD card, then ejects it. Insert the card into the intended tablet, put that tablet into Nokia update mode, and choose Install again to boot its isolated SD installer.',
                'After USB networking is ready, choose Install again to write and verify internal recovery. This fresh installation erases the selected card and the tablet internal 2 GB storage.',
                'Leave the SD card inserted and return the same tablet to Nokia update mode on the same USB port. Choose Install again to flash only the matching recovery kernel.',
                'One flashed kernel runs both recovery and SD. Early startup selects the SD A/B root and persistent data without restarting the kernel. With no card, internal recovery starts after the card-detection wait.',
                'Future OS updates use n810-ab update with UPDATE.json and slot.ext4. They replace the inactive OS slot, preserving persistent homes, network settings, identities, maps and databases. Do not use the fresh-install card writer for updates.',
                'A rendered GPU desktop and persistent mounts confirm the trial boot. Failed trials return to the confirmed slot on a later restart; a hard hang still needs a restart.',
            )),)
        return (('N810 Setup',('For SD installation, choose SD in Storage, Wi-Fi and startup choices before building. Select the removable card reader disk and pin the new tablet USB location. Install prepares and verifies the card; insert it into that tablet before Flash kernel. SD does not require Maemo USB storage. On Linux, enter the whole disk and tablet topology port (for example 1-2.3). Install writes and verifies storage; Flash kernel is a separate step after returning that tablet to update mode. For an internal Mac installation, boot stock Maemo on the new tablet and export its internal USB storage. Run sudo -v in the launching terminal, select the kit manifest, enter the whole disk and USB port, then choose Check Mac N810 disk and Install Debian + Pocket. Keep the battery installed and charger connected. Install erases internal storage, verifies the full disk, waits for that same tablet in update mode, then flashes its matching kernel.',
                 'Setup finds internal-install manifests in this checkout\'s dist subfolders and initially selects the most recently written one. Choose another local kit cycles through other candidates. Restored sessions retain an existing selection. Check files verifies the selected kit before use.',
                 'A fresh clone has no private installation image. Install Python 3.11 or newer, Make and Docker with ARM Linux build support; start Docker. On macOS, the native flasher also needs the command-line compiler tools, pkg-config and libusb-compat. Build kit from source creates the image and installation manifest.',
                 'Choose your SSH public key file. If none exists, run ssh-keygen -t ed25519 in your terminal, then use its .pub file here. Keep the private key on your computer. The tablet generates its own unique SSH server key on first boot.',
                 'To build a new kit, enter a new local folder and your Ed25519 public key path. The console login defaults to nokia/nokia; the masked password field can override it. Build kit from source uses the same n810-build-internal Make target as the CLI. Docker must be running.',
                 'Storage, Wi-Fi and startup choices optionally preconfigure a Wi-Fi access point and boot preferences. Radio services default off. Configure the endpoints for this tablet, pairing and identity after first boot in Device Setup. Offline Data prepares regional maps on the laptop; ULS Lookup has the optional FCC download.',
                 'The password is hidden, sent to the local builder through stdin, and cleared from the form when building starts. The private kit contains its password hash and SSH access material.',
                 'Build from plan is the advanced Linux path. Enter a build-plan JSON naming root, kernel_package, gpu_runtime, gpu_module_package and gpu_mesa_package; recovery is optional for the RAM-installer path.',
                 'After a kit is built, Check files validates the root, matching kernel and GPU Pocket autostart as nokia. It also checks a SD installer when one is included.',
                 'Prepare local kit makes a verified copy. Build host flasher runs the pinned make flasher build and does not open USB.',
                 'Build kit from source runs on macOS or Linux with Docker. Build from plan runs on Linux; run sudo -v in the launching terminal first. On macOS, run sudo -v before Detect target, Boot SD installer or Flash kernel. Detection uses read-only 0xFFFF -I and accepts RX-44 only.',
                 'On macOS, stock Maemo can export its internal MMC as a whole USB disk. Enter /dev/diskN and the new tablet USB location shown by macOS; Check Mac N810 disk performs identity checks. Write Mac N810 disk erases and fully reads back that disk, then saves a receipt for Flash kernel. Run sudo -v in the launching terminal first.',
                 'On macOS, Install Debian + Pocket runs that guarded write and full readback, waits for you to return the same tablet to update mode, then flashes the matching kernel. A saved receipt lets Install resume after an interrupted wait.',
                 'Boot SD installer loads the verified kernel and initramfs with 0xFFFF -l -b. It does not flash internal storage.',
                 'Erase and write internal storage replaces the target N810 MMC. The installer verifies the MMC model, capacity and CID, then reads back the root image checksum.',
                 'After the root write, return the same tablet to Nokia update mode. Flash kernel writes the matching kernel with 0xFFFF -f -r and reboots it.',
                 'A successful flash command is not proof of first boot. Confirm the graphical Pocket desktop starts as nokia on the target. Keep the original tablet in normal Linux mode.',
                 'Install Debian + Pocket runs the stages in order and waits for the pinned USB installer at 169.254.81.1. After root readback it powers off the new tablet; hold Home while powering it on to return to update mode. The saved receipt allows resuming before the permanent kernel flash.')),)
    def close(self):
        self.password.text='';self.password.cursor=0
        self.choices.wifi_pass.text=''
        self.closed=True;self.wakeup=None;self.cancelled.set()
        if self.pool:self.pool.shutdown(wait=False,cancel_futures=True)
