import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]
MODULE=ROOT/'platform/n810/hardening/install.py'
spec=importlib.util.spec_from_file_location('nokia_hardening_test',MODULE)
hardening=importlib.util.module_from_spec(spec);spec.loader.exec_module(hardening)


class NokiaHardeningTests(unittest.TestCase):
    def test_payloads_are_fixed_and_have_no_secrets(self):
        ssh=(MODULE.parent/'10-n810-usb-recovery.conf').read_text()
        sysctl=(MODULE.parent/'60-n810-radio-hardening.conf').read_text()
        self.assertIn('Match LocalAddress 192.168.10.1',ssh)
        self.assertIn('PasswordAuthentication no',ssh)
        self.assertNotRegex(ssh+sysctl,r'(?i)(password|pin|secret)\s*=')
        self.assertIn('kernel.randomize_va_space = 2',sysctl)
        self.assertIn('net.ipv4.conf.all.accept_redirects = 0',sysctl)

    @unittest.skipUnless(Path('/usr/sbin/sshd').exists() and shutil.which('ssh-keygen'),'requires OpenSSH tools')
    def test_openssh_effective_policy_is_usb_password_only(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);key=root/'hostkey';config=root/'sshd_config'
            subprocess.run(['ssh-keygen','-q','-t','ed25519','-N','','-f',str(key)],check=True)
            config.write_text('HostKey '+str(key)+'\n'+(MODULE.parent/'10-n810-usb-recovery.conf').read_text())
            for address,expected in (('192.168.10.1','yes'),('10.10.30.80','no')):
                output=subprocess.check_output(['/usr/sbin/sshd','-T','-f',str(config),'-C',
                    'user=nokia,host=n810,addr=192.168.10.2,laddr='+address+',lport=22'],text=True)
                values=dict(line.split(None,1) for line in output.splitlines() if ' ' in line)
                self.assertEqual(values['passwordauthentication'],expected)

    def test_atomic_writer_replaces_regular_file_without_following_link(self):
        with tempfile.TemporaryDirectory() as root:
            target=Path(root)/'config';target.write_bytes(b'old')
            with patch.object(hardening.os,'chown',lambda *args:None):hardening.write_file(target,b'new')
            self.assertEqual(target.read_bytes(),b'new')
            target.unlink();outside=Path(root)/'outside';outside.write_bytes(b'outside');target.symlink_to(outside)
            with self.assertRaises(ValueError):hardening.protected_file(target)
            self.assertEqual(outside.read_bytes(),b'outside')


if __name__=='__main__':unittest.main()
