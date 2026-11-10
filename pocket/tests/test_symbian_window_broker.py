import array,importlib.util,os,pathlib,select,socket,subprocess,sys,tempfile,unittest
from types import SimpleNamespace
from unittest.mock import patch
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'shell'),str(ROOT/'platform/n810')]

@unittest.skipUnless(sys.platform=='linux','Linux descriptor broker')
class BrokerTest(unittest.TestCase):
    def test_only_dead_owned_socket_is_retired(self):
        from symbian_windows import retire_stale_control
        with tempfile.TemporaryDirectory() as directory:
            path=pathlib.Path(directory)/'desktop.sock'
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as server:
                server.bind(str(path));server.listen()
                with self.assertRaises(RuntimeError):retire_stale_control(path,os.getuid())
                self.assertTrue(path.exists())
            retire_stale_control(path,os.getuid());self.assertFalse(path.exists())
            path.write_text('keep')
            with self.assertRaises(RuntimeError):retire_stale_control(path,os.getuid())
            self.assertEqual(path.read_text(),'keep')

    def test_client_gets_transport_only_and_close_reaps_guest(self):
        from symbian_windows import Broker
        with tempfile.TemporaryDirectory() as home:
            root=pathlib.Path(home)/'.local/share/symbian-private/runtime';root.mkdir(parents=True)
            account=SimpleNamespace(pw_dir=home,pw_uid=os.getuid(),pw_gid=os.getgid())
            gpu=os.open('/dev/null',os.O_RDWR);lock=os.memfd_create('window-test')
            broker=Broker(account,gpu,lock,{},lambda:None)
            request,reply=socket.socketpair(socket.AF_UNIX,socket.SOCK_SEQPACKET)
            descriptors=array.array('i');real_popen=subprocess.Popen
            def spawn(argv,**kwargs):
                self.assertEqual(set(kwargs['pass_fds'])&{gpu,lock},{gpu,lock})
                self.assertNotIn('N810_SYMBIAN_FB_FD',kwargs['env'])
                self.assertNotIn('N810_MBX_SURFACE_CHECKPOINT',kwargs['env'])
                self.assertEqual(kwargs['env']['N810_MBX_WINDOW_COUNT'],'6')
                self.assertEqual(kwargs['env']['N810_MBX_SEPARATE_ALPHA'],'1')
                self.assertEqual(kwargs['stdin'],subprocess.DEVNULL)
                return real_popen(argv,**kwargs)
            try:
                with patch('symbian_windows.command',return_value=[sys.executable,'-c','import time;time.sleep(30)']),patch('symbian_windows.subprocess.Popen',side_effect=spawn):
                    broker.start('2000730f',request)
                data,ancillary,_,_=reply.recvmsg(256,socket.CMSG_SPACE(12),socket.MSG_CMSG_CLOEXEC)
                self.assertEqual(data,b'window')
                for level,kind,payload in ancillary:
                    if level==socket.SOL_SOCKET and kind==socket.SCM_RIGHTS:descriptors.frombytes(payload)
                self.assertEqual(len(descriptors),3)
                self.assertTrue(all(not os.get_inheritable(fd) for fd in descriptors))
                control=socket.socket(fileno=descriptors.pop())
                control.sendall(b'C');broker.service(select.select(broker.sources(),[],[],3)[0])
                broker.service(select.select(broker.sources(),[],[],3)[0])
                self.assertIsNone(broker.active);control.close()
            finally:
                broker.close();request.close();reply.close();os.close(gpu);os.close(lock)
                for fd in descriptors:os.close(fd)

if __name__=='__main__':unittest.main()
