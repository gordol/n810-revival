"""Check the internal image's SysV boot order without a tablet."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import shutil
import sys
import time

from stage_sysv import START, stage


class StageSysVTest(unittest.TestCase):
    @unittest.skipUnless(sys.platform=='linux' and shutil.which('start-stop-daemon'),
                         'Requires the real Debian service launcher')
    def test_shell_daemons_launch_with_debian_start_stop_daemon(self):
        device=Path(__file__).resolve().parents[1]/'device'
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in ('n810-ledd','n810-powerd','n810-displayd'):
                with self.subTest(service=name):
                    daemon=root/name;marker=root/(name+'.started');run=root/(name+'.run')
                    daemon.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n')
                    daemon.chmod(0o755)
                    script=(device/(name+'.init')).read_text().replace(
                        'daemon=/usr/local/sbin/'+name,'daemon='+str(daemon)).replace(
                        'run_dir=/run/'+name,'run_dir='+str(run))
                    init=root/(name+'.init');init.write_text(script)
                    result=subprocess.run(['sh',str(init),'start'],capture_output=True,text=True,timeout=5)
                    self.assertEqual(result.returncode,0,result.stderr)
                    deadline=time.monotonic()+2
                    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertTrue(marker.exists(),result.stderr)

    def test_ssh_keys_start_before_ssh_and_pocket_after_touch(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('var/lib/dpkg', 'etc/init.d', 'etc/ssh/sshd_config.d', 'etc/rc2.d'):
                (root / name).mkdir(parents=True, exist_ok=True)
            (root / 'var/lib/dpkg/status').write_text(
                'Package: sysvinit-core\nStatus: install ok installed\n\n'
                'Package: openssh-server\nStatus: install ok installed\n')
            (root / 'etc/init.d/ssh').write_text('#!/bin/sh\n')
            (root / 'etc/init.d/.depend.start').write_text('TARGETS = ssh dbus\n')
            (root / 'etc/rc2.d/S01ssh').symlink_to('../init.d/ssh')
            (root / 'etc/ssh/sshd_config.d/10-n810-first-install.conf').write_text('PermitRootLogin no\n')
            self.assertEqual(stage(root, '1a2b3c4d'), sorted(START))
            self.assertTrue((root / 'etc/init.d/.legacy-bootordering').is_file())
            self.assertTrue((root / 'etc/rc2.d/S00n810-ssh-hostkeys').is_symlink())
            self.assertTrue((root / 'etc/rc2.d/S01n810-bluetooth-address').is_symlink())
            self.assertIn('/usr/local/sbin/n810-bluetooth-address --wait 15',
                          (root / 'etc/init.d/n810-bluetooth-address').read_text())
            self.assertTrue((root / 'etc/rc2.d/S04n810-setup-touch').is_symlink())
            self.assertTrue((root / 'etc/rc2.d/S05pocket-desktop').is_symlink())
            self.assertIn('HostKey /etc/ssh/ssh_host_ed25519_key',
                          (root / 'etc/ssh/sshd_config.d/10-n810-first-install.conf').read_text())
            self.assertIn('/dev/disk/by-partuuid/1a2b3c4d-01',
                          (root / 'etc/init.d/pocket-expand-internal-root').read_text())
            for name in START:
                subprocess.run(['sh', '-n', str(root / 'etc/init.d' / name)], check=True)

    def test_rejects_systemd_pid_one(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'var/lib/dpkg').mkdir(parents=True)
            (root / 'var/lib/dpkg/status').write_text(
                'Package: sysvinit-core\nStatus: install ok installed\n\n'
                'Package: systemd-sysv\nStatus: install ok installed\n')
            with self.assertRaisesRegex(ValueError, 'must not select systemd'):
                stage(root, '1a2b3c4d')


if __name__ == '__main__':
    unittest.main()
