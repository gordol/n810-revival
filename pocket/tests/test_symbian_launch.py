import importlib.util
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'shell'))
from symbian_launch import launch
spec=importlib.util.spec_from_file_location('symbian_session',ROOT/'platform/n810/symbian_session.py')
session=importlib.util.module_from_spec(spec);spec.loader.exec_module(session)

class SymbianLaunchTest(unittest.TestCase):
    def test_unknown_app_never_connects(self):
        with self.assertRaises(ValueError):launch('../shell')
    @unittest.skipUnless(sys.platform=="linux", "Linux descriptor handoff")
    def test_runtime_receives_only_owned_descriptors_and_gpu_mode(self):
        with tempfile.TemporaryDirectory() as home:
            root=Path(home)/'.local/share/symbian-private'
            binary=root/'code/symbian-runtime';binary.parent.mkdir(parents=True);binary.touch()
            library=root/'code/lib/libOSMesa.so.8';library.parent.mkdir();library.touch()
            app=root/'runtime/data/drives/c/sys/bin/ChessGenius_20036D63.exe';app.parent.mkdir(parents=True);app.touch()
            fd=os.open('/dev/null',os.O_RDONLY);seen=[]
            def popen(argv,**options):
                self.assertEqual(argv[0],str(binary))
                self.assertEqual(options['stdout'].name,options['stdout'].fileno())
                self.assertEqual(options['stderr'],subprocess.STDOUT)
                env=options['env'];self.assertEqual(env['N810_SYMBIAN_FIXED_FUNCTION'],'gpu')
                self.assertEqual(env['N810_SYMBIAN_CPU'],'native')
                self.assertNotIn('N810_SYMBIAN_TRACE_ATLAS',env)
                self.assertNotIn('N810_MBX_DESKTOP_TARGET',env)
                self.assertNotIn('N810_MBX_EXCLUSIVE_SURFACE',env)
                self.assertEqual(env['N810_SYMBIAN_GPU_MASK'],'1')
                self.assertEqual(env['N810_SYMBIAN_MASK_CACHE'],'1')
                self.assertEqual(env['N810_SYMBIAN_SPRITE_BATCH'],'1')
                self.assertEqual(env['N810_SYMBIAN_BATCH_LISTS'],'0')
                self.assertEqual(env['N810_SYMBIAN_COMPACT_COMMANDS'],'1')
                self.assertTrue(env['LD_PRELOAD'].endswith('/code/lib/libOSMesa.so.8'))
                for descriptor in options['pass_fds']:os.fstat(descriptor)
                self.assertEqual(os.read(int(env['N810_SYMBIAN_DISPLAY_GRANT_FD']),1),b'G')
                return SimpleNamespace(wait=lambda:0)
            try:
                with patch.object(session,'keyboard_device',return_value='/dev/null'),patch.object(session.subprocess,'Popen',side_effect=popen):
                    self.assertEqual(session.run('chess',SimpleNamespace(pw_dir=home,pw_uid=os.getuid(),pw_gid=os.getgid()),fd,fd,{'N810_SYMBIAN_TRACE_ATLAS':'1','N810_MBX_DESKTOP_TARGET':'1'},fd,lambda:None,seen.append),0)
                self.assertEqual(len(seen),1)
                self.assertEqual((root/'runtime/session.log').read_text(),'launcher_exit_status=0\n')
                os.fstat(fd)
            finally:os.close(fd)

    @unittest.skipUnless(sys.platform=="linux", "Linux terminal sessions")
    def test_reopen_terminal_for_second_session(self):
        import pty,fcntl
        master,slave=pty.openpty();name=os.ttyname(slave)
        def claim():os.setsid();fcntl.ioctl(0,0x540e,0)
        try:
            first=subprocess.Popen([sys.executable,'-c','pass'],stdin=slave,preexec_fn=claim)
            self.assertEqual(first.wait(),0)
            os.close(slave);slave=os.open(name,os.O_RDWR|os.O_NOCTTY)
            second=subprocess.Popen([sys.executable,'-c','pass'],stdin=slave,preexec_fn=claim)
            self.assertEqual(second.wait(),0)
        finally:os.close(slave);os.close(master)

    def test_missing_app_refuses_handoff(self):
        with tempfile.TemporaryDirectory() as home:
            with self.assertRaises(RuntimeError):session.command('chess',home)
    @unittest.skipUnless(sys.platform=="linux", "Linux owner primitives")
    def test_owner_request_and_exit(self):
        with tempfile.TemporaryDirectory() as directory:
            server=session.Session(directory,os.getuid(),os.getgid())
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
            result=[]
            thread=threading.Thread(target=lambda:result.append(server.wait(child,lambda app:None)))
            thread.start()
            try:
                with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as client:
                    client.connect(str(server.path));client.sendall(b'chess');self.assertEqual(client.recv(256),b'accepted')
                thread.join(3);self.assertFalse(thread.is_alive());self.assertEqual(result,['chess'])
            finally:child.terminate();child.wait();server.close()
    @unittest.skipUnless(sys.platform=="linux", "Linux owner primitives")
    def test_bad_request_preserves_desktop(self):
        with tempfile.TemporaryDirectory() as directory:
            server=session.Session(directory,os.getuid(),os.getgid())
            child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
            result=[];admitted=[]
            thread=threading.Thread(target=lambda:result.append(server.wait(child,admitted.append)))
            thread.start()
            try:
                for name in (b'../shell',b'chess --debug'):
                    with socket.socket(socket.AF_UNIX,socket.SOCK_SEQPACKET) as client:
                        client.connect(str(server.path));client.sendall(name)
                        self.assertIn(b'Invalid',client.recv(256))
                    self.assertIsNone(child.poll());self.assertEqual(admitted,[])
                child.terminate();child.wait();thread.join(3)
                self.assertEqual(result,[None])
            finally:
                if child.poll() is None:child.terminate();child.wait()
                server.close()

    @unittest.skipUnless(sys.platform=="linux", "Linux owner primitives")
    def test_normal_exit_needs_no_poll_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            server=session.Session(directory,os.getuid(),os.getgid())
            child=subprocess.Popen([sys.executable,'-c','pass'])
            try:self.assertIsNone(server.wait(child,lambda app:None));child.wait()
            finally:server.close()

if __name__=='__main__':unittest.main()
