"""Exercise root helper dispatch without root privileges or radio/display devices."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

REPO=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('spp_policy',REPO/'pocket/platform/n810/rnode_spp_prepare.py')
spp=importlib.util.module_from_spec(spec);spec.loader.exec_module(spp)

class SystemHelpersTests(unittest.TestCase):
    def test_per_device_configuration_is_explicit_and_bounded(self):
        good=dict(controller='02:00:00:00:00:01',address='02:00:00:00:00:02')
        self.assertEqual(spp.validate_configuration(good),good)
        for bad in ({},dict(good,channel=2),dict(good,address=good['controller']),dict(good,address='../../etc/shadow')):
            with self.assertRaises(ValueError):spp.validate_configuration(bad)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'config';p.write_text(json.dumps(good));p.chmod(0o600)
            info=SimpleNamespace(st_mode=stat.S_IFREG|0o600,st_uid=0,st_nlink=1)
            with patch.object(spp.os,'fstat',return_value=info):self.assertEqual(spp.load_configuration(p),good)
            info.st_mode=stat.S_IFREG|0o644
            with patch.object(spp.os,'fstat',return_value=info):
                with self.assertRaisesRegex(ValueError,'private'):spp.load_configuration(p)
    def test_configure_never_pairs_binds_or_opens_a_device(self):
        sys.path.insert(0,str(REPO/'pocket/platform/n810'))
        import importlib.machinery
        loader=importlib.machinery.SourceFileLoader('rnode_configure',str(REPO/'platform/scripts/n810-rnode-configure'))
        module=importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name,loader));loader.exec_module(module)
        good=dict(controller='02:00:00:00:00:01',address='02:00:00:00:00:02')
        with tempfile.TemporaryDirectory() as folder:
            parent=Path(folder)/'config'
            actual_lstat=Path.lstat
            def root_owned(p,*a,**kw):
                value=actual_lstat(p,*a,**kw)
                return SimpleNamespace(st_mode=value.st_mode,st_uid=0) if p==parent else value
            with patch.object(module.subprocess,'run',return_value=SimpleNamespace(returncode=0,stdout='Controller '+good['controller']+' example\n')) as run,patch.object(Path,'lstat',root_owned):
                module.configure(json.dumps(good).encode(),parent)
            self.assertEqual(run.call_args.args[0],['/usr/bin/bluetoothctl','show'])
            self.assertEqual(json.loads((parent/'rnode-spp.json').read_text()),good)
            self.assertEqual((parent/'rnode-spp.json').stat().st_mode&0o777,0o600)
    def test_fresh_adapter_never_falls_back_to_an_example_endpoint(self):
        import contextlib,io,runpy
        from unittest.mock import Mock
        fake=SimpleNamespace(load_configuration=Mock(side_effect=FileNotFoundError('Configure this tablet first')),
            _existing_mapping_ready=Mock(return_value=True),prepare=Mock(),DEVICE='/dev/rfcomm0')
        script=REPO/'platform/scripts/n810-rnode-spp-prepare'
        output=io.StringIO()
        with patch.dict(sys.modules,{'rnode_spp_prepare':fake}),patch.object(os,'geteuid',return_value=0),patch.object(sys,'argv',[str(script)]),contextlib.redirect_stdout(output):
            with self.assertRaises(SystemExit) as result:runpy.run_path(str(script))
        self.assertEqual(result.exception.code,1)
        self.assertFalse(json.loads(output.getvalue())['ok'])
        fake._existing_mapping_ready.assert_not_called();fake.prepare.assert_not_called()

    def test_native_menu_restores_vt_without_legacy_session_switching(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);log=root/'argv'
            openvt=root/'openvt';openvt.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > '+str(log)+'\n');openvt.chmod(0o755)
            text=(REPO/'platform/scripts/n810-native-power-menu').read_text()
            text=text.replace('$(id -u)','0').replace('/run/lock/n810-power-menu.lock',str(root/'lock')).replace('flock -n 9','true').replace('exec openvt','exec '+str(openvt))
            result=subprocess.run(['sh','-c',text],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual(log.read_text().splitlines(),['-s','-w','--','/usr/local/sbin/n810-power-overlay'])
            self.assertNotIn('n810-gui',text);self.assertNotIn('runuser',text)
    def test_power_actions_dispatch_to_system_helpers(self):
        for choice in ('charging','airplane-on','balanced'):
            with self.subTest(action=choice),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);log=root/'actions';counter=root/'used'
                tool=root/'action';tool.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> '+str(log)+'\n');tool.chmod(0o755)
                menu=root/'whiptail';menu.write_text('#!/bin/sh\nif test -e '+str(counter)+'; then echo return >&2; else touch '+str(counter)+'; echo '+choice+' >&2; fi\n');menu.chmod(0o755)
                text=(REPO/'platform/scripts/n810-power-overlay').read_text().replace('whiptail',str(menu))
                for name in ('/usr/local/bin/n810-power','/usr/local/sbin/n810-radio','/usr/local/sbin/n810-mode','/usr/local/sbin/n810-cpu-policy'):
                    text=text.replace(name,str(tool))
                result=subprocess.run(['sh','-c',text],capture_output=True,text=True,timeout=3)
                self.assertEqual(result.returncode,0,result.stderr)
                self.assertIn(choice,log.read_text().splitlines())
