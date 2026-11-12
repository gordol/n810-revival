import unittest
import gzip,hashlib,io,json,tempfile,threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock,patch
from internal_installer import (internal_target,partition_table,Installer,verify_local_kit,
                                boot_installer,configure_installer_network,flash_kernel,_run_flasher)
from build_internal_image import load_plan
from internal_installer import install_device,install_macos

class InternalTarget(unittest.TestCase):
    def row(self,name='mmcblk0',kind='MMC',sectors=3900000,cid='a'*32):
        return f'{name} {kind} {sectors} {cid}'
    def test_internal_mmc_selected_independently_of_sd_order(self):
        result=internal_target(self.row('mmcblk0','SD')+'\n'+self.row('mmcblk1'),512*1024*1024)
        self.assertEqual(result['device'],'/dev/mmcblk1')
    def test_rejects_ambiguous_missing_oversized_and_malformed_targets(self):
        for rows,size in ((self.row(kind='SD'),1),(self.row()+'\n'+self.row('mmcblk1'),1),
                          (self.row(),4*1024**3),(self.row(sectors=100),1),
                          (self.row(name='mmcblk0;reboot'),1),(self.row(cid='bad'),1)):
            with self.subTest(rows=rows),self.assertRaises(ValueError):internal_target(rows,size)

    def test_partition_table_spans_internal_mmc_with_stable_identity(self):
        table=partition_table('1234abcd',3900000)
        self.assertEqual(len(table),512)
        self.assertEqual(table[440:444],b'\xcd\xab\x34\x12')
        self.assertEqual(table[450],0x83)
        self.assertEqual(int.from_bytes(table[454:458],'little'),2048)
        self.assertEqual(int.from_bytes(table[458:462],'little'),3900000-2048)
        self.assertEqual(table[510:],b'\x55\xaa')

    def test_macos_network_configures_only_the_new_interface(self):
        with patch('internal_installer.platform.system',return_value='Darwin'), \
                patch('internal_installer.socket.if_nameindex',return_value=[(1,'lo0'),(7,'en7'),(8,'en8')]), \
                patch('internal_installer.subprocess.run',return_value=SimpleNamespace(returncode=0)) as run:
            self.assertEqual(configure_installer_network({'lo0','en7'}),'en8')
        self.assertEqual(run.call_args.args[0][-2:],['--configure-network','en8'])

    def test_macos_network_rejects_ambiguous_new_interfaces(self):
        with patch('internal_installer.platform.system',return_value='Darwin'), \
                patch('internal_installer.socket.if_nameindex',return_value=[(8,'en8'),(9,'en9')]), \
                self.assertRaisesRegex(RuntimeError,'More than one'):
            configure_installer_network({'lo0'})

    def test_flasher_error_diagnostic_cannot_pass_with_zero_exit(self):
        completed=SimpleNamespace(returncode=0,stdout='Done\n',stderr='Error: Sending image failed\n')
        with patch('internal_installer._flasher_command',return_value=['fixture']), \
                patch('internal_installer.subprocess.run',return_value=completed), \
                self.assertRaisesRegex(RuntimeError,'Sending image failed'):
            _run_flasher('/fixture',[],1)

class BuildPlan(unittest.TestCase):
    def test_reads_bounded_plan_with_required_input_directories(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('root','kernel','recovery','runtime','module','mesa'):(root/name).mkdir()
            plan=root/'plan.json';plan.write_text(json.dumps(dict(root=str(root/'root'),
                kernel_package=str(root/'kernel'),recovery=str(root/'recovery'),
                gpu_runtime=str(root/'runtime'),gpu_module_package=str(root/'module'),
                gpu_mesa_package=str(root/'mesa'),size_mib=1200)))
            result=load_plan(plan)
            self.assertEqual(result['size_mib'],1200)
            self.assertEqual(result['kernel_package'],(root/'kernel').resolve())
            without_recovery=json.loads(plan.read_text())
            without_recovery.pop('recovery')
            plan.write_text(json.dumps(without_recovery))
            self.assertNotIn('recovery',load_plan(plan))
            plan.write_text('{"root":"a","root":"b","kernel_package":"c","recovery":"d"}')
            with self.assertRaisesRegex(ValueError,'Duplicate'):load_plan(plan)

class CompressedKit(unittest.TestCase):
    def test_maemo_storage_kit_needs_no_ram_installer(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            _,manifest=self.kit(root)
            manifest['install_transport']='maemo-usb-mass-storage'
            for name in ('installer_kernel_release','installer_kernel_sha256',
                         'ram_installer_manifest_sha256'):
                manifest.pop(name)
            (root/'INTERNAL.json').write_text(json.dumps(manifest))
            installation=json.loads((root/'INSTALLATION.json').read_text())
            installation['files']=[row for row in installation['files']
                                   if not row['role'].startswith(('installer-',))]
            plan_row=next(row for row in installation['files'] if row['role']=='install-plan')
            plan_row['sha256']=hashlib.sha256((root/'INTERNAL.json').read_bytes()).hexdigest()
            plan_row['bytes']=(root/'INTERNAL.json').stat().st_size
            (root/'INSTALLATION.json').write_text(json.dumps(installation))
            for name in ('installer-kernel.bin','installer-initramfs.cpio.xz',
                         'installer-known-hosts','INSTALLER-BUILD.json'):
                (root/name).unlink()
            _,verified,files=verify_local_kit(root)
            self.assertEqual(verified['install_transport'],'maemo-usb-mass-storage')
            self.assertNotIn('installer-kernel',files)
            with patch('internal_installer.identify_device') as identify, \
                 self.assertRaisesRegex(ValueError,'contains no RAM installer'):
                boot_installer(root,'/fixture/flasher')
            identify.assert_not_called()

    def test_complete_install_never_flashes_after_a_failed_root_write(self):
        with tempfile.TemporaryDirectory() as folder:
            self.kit(folder)
            with patch('internal_installer.boot_installer') as boot, \
                    patch('internal_installer.configure_installer_network'), \
                    patch('internal_installer.Installer.remote') as remote, \
                    patch('internal_installer.install_root',side_effect=ValueError('readback mismatch')), \
                    patch('internal_installer.flash_kernel') as flash:
                with self.assertRaisesRegex(ValueError,'readback mismatch'):
                    install_device(folder)
                boot.assert_called_once();flash.assert_not_called()
                self.assertEqual(remote.call_count,1)
    def kit(self,folder):
        root=Path(folder);raw=b'fictional root fixture'*1024
        archive=root/'root.ext4.gz';archive.write_bytes(gzip.compress(raw))
        kernel=root/'kernel.bin';kernel.write_bytes(b'fictional kernel fixture')
        (root/'installer-kernel.bin').write_bytes(b'fictional RAM kernel')
        (root/'installer-initramfs.cpio.xz').write_bytes(b'\xfd7zXZ\x00fictional cpio initramfs')
        (root/'installer-known-hosts').write_text('192.168.11.1 ssh-ed25519 FAKE\n')
        (root/'INSTALL.txt').write_text('Fictional fixture only.\n')
        kernel_digest=hashlib.sha256(kernel.read_bytes()).hexdigest()
        installer_kernel=root/'installer-kernel.bin';installer_initfs=root/'installer-initramfs.cpio.xz'
        kernel_build=dict(release='fixture-kernel',root_device='PARTUUID=1234abcd-01',
                          files={'zImage-omap2420-n810':kernel_digest,'kernel.config':'c'*64})
        (root/'KERNEL-BUILD.json').write_text(json.dumps(kernel_build))
        installer_build=dict(kind='n810-ram-installer',kernel_release='fixture-installer-kernel',
            filesystem_format='cpio-xz',root_device='initramfs:/init',files={
            'kernel.bin':hashlib.sha256(installer_kernel.read_bytes()).hexdigest(),
            'initramfs.cpio.xz':hashlib.sha256(installer_initfs.read_bytes()).hexdigest()})
        (root/'INSTALLER-BUILD.json').write_text(json.dumps(installer_build))
        manifest=dict(kind='n810-internal',root_bytes=len(raw),root_sha256=hashlib.sha256(raw).hexdigest(),
            compressed_root_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),
            kernel_sha256=kernel_digest,kernel_release='fixture-kernel',
            installer_kernel_release='fixture-installer-kernel',installer_kernel_sha256=hashlib.sha256(installer_kernel.read_bytes()).hexdigest(),
            kernel_package_manifest_sha256=hashlib.sha256((root/'KERNEL-BUILD.json').read_bytes()).hexdigest(),
            ram_installer_manifest_sha256=hashlib.sha256((root/'INSTALLER-BUILD.json').read_bytes()).hexdigest(),
            disk_id='1234abcd',desktop_ready=True,desktop=dict(desktop_user='nokia',autostart=True,
                renderer='native-mbx-gpu',module_sha256='d'*64,mesa_sha256='e'*64),
            first_boot=dict(profile='n810-internal-v3',
                root_manifest_sha256='a'*64,keyboard_remapper_sha256='b'*64,
                keyboard_backlight_sha256='c'*64,
                enabled_services=['n810-setup-touch.service','n810-fn-remap.service',
                    'n810-keyboard.service','n810-backlightd.service','n810-powerd.service',
                    'n810-ledd.service','n810-display-keys.service','pocket-desktop.service']))
        (root/'INTERNAL.json').write_text(json.dumps(manifest))
        roles={'root-filesystem':archive,'kernel':kernel,'installer-kernel':root/'installer-kernel.bin',
            'installer-filesystem':root/'installer-initramfs.cpio.xz','install-plan':root/'INTERNAL.json',
            'kernel-build-manifest':root/'KERNEL-BUILD.json','installer-build-manifest':root/'INSTALLER-BUILD.json',
            'installer-host-key':root/'installer-known-hosts','install-guide':root/'INSTALL.txt'}
        files=[dict(role=role,path=path.name,bytes=path.stat().st_size,
                    sha256=hashlib.sha256(path.read_bytes()).hexdigest()) for role,path in roles.items()]
        (root/'INSTALLATION.json').write_text(json.dumps(dict(version=1,kind='n810-internal',
            release='fixture-internal',kernel_release='fixture-kernel',files=files)))
        installer=Installer(root,'192.168.11.1')
        identity=('release=fixture-installer-kernel\n'
                  'cmdline=root=/dev/ram0 rw rdinit=/init\n'
                  'rootfs=tmpfs\npid1=/bin/busybox\n')
        installer.remote=Mock(side_effect=[SimpleNamespace(stdout=identity),
            SimpleNamespace(stdout='mmcblk0 MMC 3900000 '+'a'*32+'\n')])
        return installer,manifest
    def test_compressed_only_kit_is_verified_before_target_inspection(self):
        with tempfile.TemporaryDirectory() as folder:
            installer,manifest=self.kit(folder)
            _,target=installer.inspect()
            self.assertEqual(target['device'],'/dev/mmcblk0')
            self.assertEqual(installer.remote.call_count,2)

    def test_old_kit_without_input_and_power_profile_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            _, manifest = self.kit(folder)
            manifest.pop('first_boot')
            root = Path(folder)
            (root/'INTERNAL.json').write_text(json.dumps(manifest))
            rows = json.loads((root/'INSTALLATION.json').read_text())
            plan_row = next(row for row in rows['files'] if row['role']=='install-plan')
            plan_row['sha256'] = hashlib.sha256((root/'INTERNAL.json').read_bytes()).hexdigest()
            plan_row['bytes'] = (root/'INTERNAL.json').stat().st_size
            (root/'INSTALLATION.json').write_text(json.dumps(rows))
            with self.assertRaisesRegex(ValueError,'predates the verified keyboard'):
                verify_local_kit(root)

    def test_new_profile_requires_lock_slider_service(self):
        with tempfile.TemporaryDirectory() as folder:
            _, manifest = self.kit(folder)
            root = Path(folder)
            manifest['first_boot']['profile'] = 'n810-internal-v4'
            manifest['first_boot']['lock_slider_sha256'] = 'f' * 64
            for enabled in (False, True):
                if enabled:
                    manifest['first_boot']['enabled_services'].append('n810-wake.service')
                (root/'INTERNAL.json').write_text(json.dumps(manifest))
                rows = json.loads((root/'INSTALLATION.json').read_text())
                plan_row = next(row for row in rows['files'] if row['role']=='install-plan')
                plan_row['sha256'] = hashlib.sha256((root/'INTERNAL.json').read_bytes()).hexdigest()
                plan_row['bytes'] = (root/'INTERNAL.json').stat().st_size
                (root/'INSTALLATION.json').write_text(json.dumps(rows))
                if enabled:self.assertEqual(verify_local_kit(root)[1]['first_boot']['profile'], 'n810-internal-v4')
                else:
                    with self.assertRaisesRegex(ValueError,'first-boot services'):
                        verify_local_kit(root)

    def test_macos_install_waits_for_same_written_usb_port(self):
        with tempfile.TemporaryDirectory() as folder:
            self.kit(folder)
            root=Path(folder)
            manifest=json.loads((root/'INTERNAL.json').read_text())
            def writer(*args,**kwargs):
                (root/'INSTALL-STATE.json').write_text(json.dumps(dict(
                    version=1,state='rootfs_written',transport='maemo-usb-mass-storage',
                    device='/dev/disk5',usb_location=0x02100000,rootfs_readback_verified=True,
                    kernel_flashing_pending=True,root_sha256=manifest['root_sha256'],
                    kernel_sha256=manifest['kernel_sha256'])))
                return SimpleNamespace(stdout=io.StringIO('Full disk readback verified.\n'),wait=lambda:0)
            with patch('internal_installer.sys.platform','darwin'), \
                 patch('internal_installer.os.geteuid',return_value=0), \
                 patch('internal_installer.subprocess.Popen',side_effect=writer) as launch, \
                 patch('internal_installer.identify_device',return_value={'usb_location':0x02100000}) as identify, \
                 patch('internal_installer.flash_kernel',return_value={'state':'kernel_flashed_reboot_requested'}) as flash:
                result=install_macos(root,'/dev/disk5',0x02100000,Path('/fixture/0xFFFF'))
            self.assertEqual(result['state'],'kernel_flashed_reboot_requested')
            self.assertIn('--write',launch.call_args.args[0])
            identify.assert_called_once()
            flash.assert_called_once()
            with patch('internal_installer.sys.platform','darwin'), \
                 patch('internal_installer.identify_device',return_value={'usb_location':0x00100000}), \
                 patch('internal_installer.flash_kernel') as flash:
                with self.assertRaisesRegex(ValueError,'different USB port'):
                    install_macos(root,'',0,Path('/fixture/0xFFFF'))
            flash.assert_not_called()
            with patch('internal_installer.sys.platform','darwin'), \
                 patch('internal_installer.identify_device') as identify:
                with self.assertRaisesRegex(ValueError,'Selected disk differs'):
                    install_macos(root,'/dev/disk6',0,Path('/fixture/0xFFFF'))
            identify.assert_not_called()
            receipt=json.loads((root/'INSTALL-STATE.json').read_text())
            receipt['kernel_sha256']='0'*64
            (root/'INSTALL-STATE.json').write_text(json.dumps(receipt))
            with patch('internal_installer.sys.platform','darwin'), \
                 patch('internal_installer.identify_device') as identify:
                with self.assertRaisesRegex(ValueError,'does not match this kit'):
                    install_macos(root,'',0,Path('/fixture/0xFFFF'))
            identify.assert_not_called()
            cancelled=threading.Event();cancelled.set()
            with patch('internal_installer.sys.platform','darwin'),self.assertRaises(InterruptedError):
                install_macos(root,'',0,cancelled=cancelled)

    def test_cpu_desktop_kit_is_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            _, manifest = self.kit(folder)
            root = Path(folder)
            manifest['desktop']['renderer'] = 'native-cpu-framebuffer'
            (root/'INTERNAL.json').write_text(json.dumps(manifest))
            installation = json.loads((root/'INSTALLATION.json').read_text())
            record = next(row for row in installation['files'] if row['role'] == 'install-plan')
            record['sha256'] = hashlib.sha256((root/'INTERNAL.json').read_bytes()).hexdigest()
            record['bytes'] = (root/'INTERNAL.json').stat().st_size
            (root/'INSTALLATION.json').write_text(json.dumps(installation))
            with self.assertRaisesRegex(ValueError, 'matching MBX GPU'):
                verify_local_kit(root)

    def test_flashed_initfs_or_wrong_kernel_cannot_reach_mmc_inventory(self):
        with tempfile.TemporaryDirectory() as folder:
            installer,_=self.kit(folder)
            installer.remote=Mock(return_value=SimpleNamespace(stdout=
                'release=fixture-installer-kernel\ncmdline=root=/dev/mtdblock3\n'
                'rootfs=jffs2\npid1=/bin/busybox\n'))
            with self.assertRaisesRegex(ValueError,'not the verified RAM initramfs'):
                installer.inspect()
            self.assertEqual(installer.remote.call_count,1)
    def test_corruption_and_expansion_size_fail_without_contacting_tablet(self):
        for mode in ('corrupt','expanded'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as folder:
                installer,manifest=self.kit(folder)
                if mode=='corrupt':(Path(folder)/'root.ext4.gz').write_bytes(b'changed')
                else:
                    manifest['root_bytes']-=1
                    (Path(folder)/'INTERNAL.json').write_text(json.dumps(manifest))
                with self.assertRaises(ValueError):installer.inspect()
                installer.remote.assert_not_called()
    def test_ram_boot_loads_kernel_and_initfs_without_flash_flags(self):
        with tempfile.TemporaryDirectory() as folder:
            installer,_=self.kit(folder)
            with patch('internal_installer.identify_device',return_value={'model':'RX-44'}), \
                    patch('internal_installer._run_flasher',return_value='booted') as run:
                result=boot_installer(folder,'/fixture/flasher')
            self.assertEqual(result['state'],'ram_installer_booted')
            args=run.call_args.args[1]
            self.assertIn('initfs:'+str((Path(folder)/'installer-initramfs.cpio.xz').resolve()),args)
            self.assertEqual(args[-2:],['-l','-b'])
            self.assertNotIn('-f',args)
    def test_permanent_kernel_flash_requires_verified_root_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            self.kit(folder)
            with patch('internal_installer.identify_device') as identify:
                with self.assertRaisesRegex(ValueError,'Write and verify'):
                    flash_kernel(folder,'/fixture/flasher')
                identify.assert_not_called()

    def test_permanent_kernel_flash_uses_manifested_kernel_after_write_receipt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);self.kit(root)
            _,manifest,_=verify_local_kit(root)
            receipt=dict(version=1,state='rootfs_written',root_sha256=manifest['root_sha256'],
                kernel_sha256=manifest['kernel_sha256'],target_cid='a'*32,
                rootfs_readback_verified=True,kernel_flashing_pending=True)
            (root/'INSTALL-STATE.json').write_text(json.dumps(receipt))
            with patch('internal_installer.identify_device',return_value={'model':'RX-44'}), \
                    patch('internal_installer._run_flasher',return_value='flashed') as run:
                result=flash_kernel(root,'/fixture/flasher')
            self.assertEqual(result['state'],'kernel_flashed_reboot_requested')
            self.assertEqual(run.call_args.args[1][-2:],['-f','-r'])
            self.assertFalse(json.loads((root/'INSTALL-STATE.json').read_text())['kernel_flashing_pending'])
    @patch('internal_installer._update_mode_locations', return_value=[0x02000000])
    def test_read_only_detection_accepts_only_n810_model(self, locations):
        from internal_installer import identify_device
        with patch('internal_installer._run_flasher',return_value='Found USB device: RX-34/RX-44/RX-48/RX-51\nDetected USB device: RX-44\nDevice: RX-44'):
            self.assertEqual(identify_device('/fixture/flasher')['model'],'RX-44')
        with patch('internal_installer._run_flasher',return_value='Device: RX-48'):
            with self.assertRaisesRegex(ValueError,'Expected exactly one'):
                identify_device('/fixture/flasher')

if __name__=='__main__':unittest.main()
