# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
import hashlib,json,sys,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import n810_bootstrap as bootstrap
from native_setup import N810Setup
from native_navigation import native_key,navigation

class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
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
        native_key(form,'\t');native_key(form,'\t');self.assertEqual(navigation(form).target,'check')
        native_key(form,'\r')
        self.assertIsNotNone(form.pool)
    def test_open_render_and_help_do_not_start_work(self):
        form=N810Setup();self.addCleanup(form.close)
        for width,height in ((40,14),(80,24),(110,36)):
            form.width=width;form.height=height
            self.assertEqual(len(form.lines()),height)
            self.assertTrue(all(len(row)<=width for row in form.lines()))
        form.help_pages();self.assertIsNone(form.pool);self.assertIsNone(form.pending)

if __name__=='__main__':unittest.main()
