# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib,json,sys,tempfile,threading,unittest
import io
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'platform'/'bootstrap'))
import n810_bootstrap as bootstrap
from native_setup import N810Setup,_build_internal_kit,_mac_storage
from native_navigation import native_key,navigation

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        isolated=patch('native_setup.REPOSITORY',self.root);isolated.start();self.addCleanup(isolated.stop)
    def manifest(self,kind='n810-system'):
        files=[]
        for role in bootstrap.KINDS[kind]:
            raw=('Fixture only: '+role+'\n').encode();name=role+'.fixture';(self.root/name).write_bytes(raw)
            files.append(dict(role=role,path=name,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
        self.data=dict(version=1,kind=kind,release='synthetic-fixture',kernel_release='fixture-kernel',files=files)
        path=self.root/'INSTALLATION.json';path.write_text(json.dumps(self.data));return path
    def test_check_and_prepare_are_local_and_not_installation(self):
        path=self.manifest();result=bootstrap.inspect(path)
        self.assertEqual(result['state'],'files_verified');self.assertFalse(result['tablet_installed'])
        with patch('subprocess.run',side_effect=AssertionError('No external command allowed')):
            kit=bootstrap.prepare(path,self.root/'kit')
        self.assertEqual(kit['state'],'kit_prepared');self.assertFalse(kit['tablet_installed'])
        checked=bootstrap.inspect(self.root/'kit/INSTALLATION.json');self.assertEqual(checked['files'],result['files'])
        self.assertIn('tablet is not installed',(self.root/'kit/README.txt').read_text())
    def test_internal_kit_requires_its_ram_installer_and_plan(self):
        path=self.manifest('n810-internal')
        plan=bootstrap.inspect(path)
        self.assertEqual(plan['kind'],'n810-internal')
        self.assertFalse(plan['tablet_installed'])
        self.data['files']=[row for row in self.data['files'] if row['role']!='install-plan']
        path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'install-plan'):bootstrap.inspect(path)

    def test_update_requires_its_own_installer_and_guide(self):
        path=self.manifest('pocket-update');self.assertEqual(bootstrap.inspect(path)['kind'],'pocket-update')
        self.data['files'].pop();path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'install-guide'):bootstrap.inspect(path)
    def test_checksum_failure_and_existing_destination_preserved(self):
        path=self.manifest();(self.root/self.data['files'][0]['path']).write_bytes(b'broken bytes')
        with self.assertRaisesRegex(ValueError,'mismatch'):bootstrap.prepare(path,self.root/'kit')
        self.assertFalse((self.root/'kit').exists())
        path=self.manifest();destination=self.root/'existing';destination.mkdir();(destination/'keep').write_text('keep')
        with self.assertRaisesRegex(ValueError,'already exists'):bootstrap.prepare(path,destination)
        self.assertEqual((destination/'keep').read_text(),'keep')
    def test_parent_traversal_and_symlink_refused(self):
        path=self.manifest();self.data['files'][0]['path']='../image';path.write_text(json.dumps(self.data))
        with self.assertRaisesRegex(ValueError,'inside'):bootstrap.inspect(path)
        path=self.manifest();image=self.root/self.data['files'][0]['path'];raw=image.read_bytes();image.unlink();(self.root/'other').write_bytes(raw);image.symlink_to(self.root/'other')
        with self.assertRaisesRegex(ValueError,'symlink'):bootstrap.inspect(path)
    def test_duplicate_fields_and_device_destination_refused(self):
        path=self.manifest();path.write_text('{"version":1,"version":1}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):bootstrap.inspect(path)
        path=self.manifest()
        with self.assertRaisesRegex(ValueError,'device'):bootstrap.prepare(path,'/dev/n810-fixture')
    def test_cancel_and_changed_copy_clean_partial_folder(self):
        path=self.manifest();cancelled=threading.Event();cancelled.set()
        with self.assertRaises(InterruptedError):bootstrap.prepare(path,self.root/'cancelled',cancelled=cancelled)
        original=bootstrap.inspect
        def changing(*args):
            result=original(*args);(self.root/self.data['files'][0]['path']).write_bytes(b'changed');return result
        with patch.object(bootstrap,'inspect',side_effect=changing):
            with self.assertRaisesRegex(ValueError,'changed during copy'):bootstrap.prepare(path,self.root/'changed')
        self.assertFalse((self.root/'changed').exists());self.assertFalse(list(self.root.glob('.n810-setup-*')))
    def test_native_focus_literal_input_and_explicit_action(self):
        form=N810Setup();self.addCleanup(form.close)
        for key in 'pvc':native_key(form,key)
        self.assertEqual(form.manifest.text,'pvc');self.assertIsNone(form.pool)
        native_key(form,'\t');self.assertEqual(navigation(form).target,'destination')
        native_key(form,'backtab');self.assertEqual(navigation(form).target,'manifest')
        for _ in range(4):native_key(form,'\t')
        self.assertEqual(navigation(form).target,'check')
        native_key(form,'\r')
        self.assertIsNotNone(form.pool)
    def test_flasher_action_uses_shared_builder_without_manifest(self):
        form=N810Setup();self.addCleanup(form.close)
        with patch('n810_flasher.build',return_value={'state':'flasher_built','binary':'/fixture/0xFFFF','source_revision':'fixture'}) as build:
            for _ in range(8):native_key(form,'\t')
            self.assertEqual(navigation(form).target,'flasher')
            native_key(form,'\r')
            form.pending.result(timeout=2);form.poll()
            build.assert_called_once()
        self.assertIsNone(form.result)
        self.assertEqual(form.tool_result['state'],'flasher_built')
        self.assertIn('No tablet was accessed',form.status)

    def test_device_stages_are_registered_and_use_shared_backend(self):
        form=N810Setup();self.addCleanup(form.close)
        actions={target.key for target in form.navigation_targets()}
        self.assertTrue({'kit','identify','boot','write','mac-check','mac-write','flash'}<=actions)
        plan=self.root/'build-plan.json';plan.write_text('{}')
        output=self.root/'verified-kit'
        form.manifest.text=str(plan);form.destination.text=str(output)
        with patch('native_setup._setup_work',return_value={'state':'internal_kit_built',
                'kind':'n810-internal','destination':str(output)}) as build:
            form.start('kit');form.pending.result(timeout=2);form.poll()
            build.assert_called_once()
        self.assertEqual(form.manifest.text,str(output/'INSTALLATION.json'))
        form.manifest.text=str(self.root/'INSTALLATION.json')
        results=(('identify',{'state':'device_identified','model':'RX-44'}),
                 ('boot',{'state':'ram_installer_booted','model':'RX-44','internal_storage_changed':False}),
                 ('write',{'state':'rootfs_written','rootfs_written':True}),
                 ('flash',{'state':'kernel_flashed_reboot_requested','model':'RX-44'}))
        with patch('native_setup._setup_work',side_effect=[row for _,row in results]) as work:
            for action,_ in results:
                form.start(action);form.pending.result(timeout=2);form.poll()
                self.assertIsNone(form.pending)
                self.assertTrue(form.status)
                form.lines()
        self.assertEqual([call.args[0] for call in work.call_args_list],[name for name,_ in results])
        self.assertTrue(any('return the same tablet to Nokia update mode' in line
                            for line in form.help_pages()[0][1]))

    def test_mac_storage_actions_use_identified_disk_and_shared_writer(self):
        process=type('Process',(),{'stdout':io.StringIO('Check only. Nothing written.\n'),
                                    'wait':lambda self:0})()
        with patch('native_setup.sys.platform','darwin'), \
             patch('native_setup.subprocess.Popen',return_value=process) as popen:
            result=_mac_storage('mac-check',self.root,'/dev/disk5','0x02100000',None)
        self.assertEqual(result['state'],'mac_disk_checked')
        command=popen.call_args.args[0]
        self.assertNotIn('sudo',command)
        self.assertNotIn('--write',command)
        self.assertEqual(command[command.index('--disk')+1],'/dev/disk5')
        self.assertEqual(command[command.index('--usb-location')+1],'0x2100000')
        process.stdout=io.StringIO('Full disk readback verified.\n')
        with patch('native_setup.sys.platform','darwin'), \
             patch('native_setup.subprocess.Popen',return_value=process) as popen:
            result=_mac_storage('mac-write',self.root,'/dev/disk5','0x02100000',None)
        self.assertTrue(result['rootfs_readback_verified'])
        self.assertEqual(popen.call_args.args[0][:2],['sudo','-n'])
        self.assertIn('--write',popen.call_args.args[0])
        with patch('native_setup.sys.platform','darwin'),self.assertRaisesRegex(ValueError,'whole disk'):
            _mac_storage('mac-write',self.root,'/dev/disk5s1','0x02100000',None)

    def test_internal_kit_ui_uses_plan_builder_and_verifies_output(self):
        plan=self.root/'build-plan.json';plan.write_text('{}')
        output=self.root/'private-kit'
        process=type('Process',(),{'stdout':io.StringIO(''), 'poll':lambda self:None,
                                   'wait':lambda self:0})()
        process.poll=lambda:next(polls)
        polls=iter((None,0))
        kit_manifest=dict(release='fixture-internal',files=[])
        internal=dict(kernel_release='fixture-kernel')
        files={}
        with patch('native_setup.sys.platform','linux'),patch('native_setup.os.geteuid',return_value=0), \
                patch('native_setup.subprocess.Popen',return_value=process) as popen, \
                patch('native_setup.select.select',return_value=([process.stdout],[],[])), \
                patch('internal_installer.verify_local_kit',return_value=(kit_manifest,internal,files)):
            result=_build_internal_kit(plan,output,None,threading.Event())
        self.assertEqual(result['state'],'internal_kit_built')
        command=popen.call_args.args[0]
        self.assertIn('--plan',command);self.assertIn(str(plan.resolve()),command)
        self.assertIn('--output',command);self.assertIn(str(output),command)

    def test_open_render_and_help_do_not_start_work(self):
        form=N810Setup();self.addCleanup(form.close)
        for width,height in ((40,14),(80,24),(110,36)):
            form.width=width;form.height=height
            self.assertEqual(len(form.lines()),height)
            self.assertTrue(all(len(row)<=width for row in form.lines()))
        form.width=80;form.height=14
        self.assertTrue(any('Check files' in row for row in form.lines()))
        form.field='disk'
        self.assertTrue(any('New N810 disk' in row for row in form.lines()))
        form.field='mac-write'
        self.assertTrue(any('Write Mac N810 disk' in row for row in form.lines()))
        form.help_pages();self.assertIsNone(form.pool);self.assertIsNone(form.pending)

if __name__=='__main__':unittest.main()
