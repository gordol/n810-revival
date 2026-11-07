#!/usr/bin/env python3
"""In-memory upstream IBSS RSN tests; no radio, serial or production secrets."""
import collections
import ctypes as C
import time
import unittest
from build_host import build

P=C.POINTER(C.c_uint8)
SEND=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_int,P,P,C.c_size_t,C.c_int)
KEY=C.CFUNCTYPE(C.c_int,C.c_void_p,P,C.c_int,C.c_int,C.c_int,P,C.c_size_t,P,C.c_size_t,C.c_int)
AUTH=C.CFUNCTYPE(None,C.c_void_p,C.c_int)
SEQ=C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_int,P)
class Callbacks(C.Structure):
    _fields_=[('send',SEND),('key',KEY),('authorized',AUTH),('get_seqnum',SEQ)]
def buf(b):return (C.c_uint8*len(b)).from_buffer_copy(b)

class Pair:
    def __init__(self,lib,wrong=False,rekey=600,fail_key=False):
        self.lib=lib;self.nodes=[];self.queue=collections.deque();self.sent=[]
        self.keys=[[],[]];self.events=[[],[]];self.callbacks=[];self.errors=[];self.sequence=[{},{}];self.sequence_reads=[[],[]]
        self.mac=[bytes.fromhex('020000000001'),bytes.fromhex('0002eec0ffee')]
        self.bssid=bytes.fromhex('024e38313002');self.fail_key=fail_key;self.fail_group=False
        for i in range(2):
            def send(ctx,kind,dest,data,length,encrypted,i=i):
                if length>1024 or C.string_at(dest,6)!=self.mac[1-i]:return -1
                packet=(i,kind,C.string_at(data,length),encrypted)
                self.queue.append(packet);self.sent.append(packet);return 0
            def key(ctx,addr,alg,index,tx,data,length,seq,seq_len,flags,i=i):
                self.keys[i].append((C.string_at(addr,6) if addr else None,alg,index,tx,
                                    C.string_at(data,length),C.string_at(seq,seq_len),flags))
                return -1 if length and ((self.fail_key and index==0) or (self.fail_group and index>0)) else 0
            def authorized(ctx,value,i=i):self.events[i].append(value)
            def sequence(ctx,index,out,i=i):
                self.sequence_reads[i].append(index)
                value=self.sequence[i].get(index,0)
                C.memmove(out,value.to_bytes(8,'little'),8);return 0
            cb=Callbacks(SEND(send),KEY(key),AUTH(authorized),SEQ(sequence));self.callbacks.append(cb)
            # Explicit test fixture, unrelated to any device password.
            pmk=bytes([0x42+(wrong and i==1)])*32
            node=lib.pocket_rsn_create(buf(self.mac[i]),buf(self.bssid),buf(pmk),rekey,C.byref(cb),None)
            if not node:raise RuntimeError('RSN context allocation failed')
            self.nodes.append(node)
        for i,node in enumerate(self.nodes):
            if lib.pocket_rsn_start(node,buf(self.mac[1-i])):raise RuntimeError('RSN start failed')
    def ready(self):return all(self.lib.pocket_rsn_ready(p) for p in self.nodes)
    def pump(self,seconds=0.1,drop=None):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            self.lib.pocket_rsn_poll()
            for _ in range(min(64,len(self.queue))):
                i,kind,data,encrypted=self.queue.popleft()
                if drop and drop(i,kind,data,encrypted):continue
                self.lib.pocket_rsn_receive(self.nodes[1-i],buf(self.mac[i]),kind,buf(data),len(data),encrypted)
            time.sleep(.001)
    def close(self):
        for node in self.nodes:self.lib.pocket_rsn_destroy(node)
        self.nodes=[]

class RSNTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.lib=C.CDLL(str(build()))
        cls.lib.pocket_rsn_create.argtypes=[P,P,P,C.c_uint,C.POINTER(Callbacks),C.c_void_p]
        cls.lib.pocket_rsn_create.restype=C.c_void_p
        cls.lib.pocket_rsn_start.argtypes=[C.c_void_p,P]
        cls.lib.pocket_rsn_receive.argtypes=[C.c_void_p,P,C.c_int,P,C.c_size_t,C.c_int]
        cls.lib.pocket_rsn_ready.argtypes=[C.c_void_p]
        cls.lib.pocket_rsn_destroy.argtypes=[C.c_void_p]
    def pair(self,**kw):
        pair=Pair(self.lib,**kw);self.addCleanup(pair.close);return pair
    def test_handshake_and_pairwise_key_agreement(self):
        p=self.pair();p.pump(.2)
        self.assertTrue(p.ready())
        keys=[[k[4] for k in side if k[2]==0 and len(k[4])==16] for side in p.keys]
        self.assertEqual(len(keys[0]),1);self.assertEqual(keys[0],keys[1])
        self.assertEqual(p.events,[[1],[1]])
    def test_driver_group_sequence_is_advertised_to_receiver(self):
        p=self.pair();p.sequence=[{1:0x123456789abc,2:0x123456789abc} for _ in range(2)]
        p.pump(.2);self.assertTrue(p.ready())
        expected=bytes.fromhex('bc9a78563412')
        for i in range(2):
            self.assertTrue(p.sequence_reads[i])
            received=[key for key in p.keys[i] if key[2]>0 and not key[3] and key[4]]
            self.assertTrue(any(key[5]==expected for key in received))
    def test_wrong_password_stays_unauthorized(self):
        p=self.pair(wrong=True);p.pump(1.3)
        self.assertFalse(p.ready());self.assertEqual(p.events,[[],[]])
        self.assertFalse(any(k[2]==0 and k[4] for side in p.keys for k in side))
    def test_driver_key_failure_stays_unauthorized(self):
        p=self.pair(fail_key=True);p.pump(.2)
        self.assertFalse(p.ready());self.assertEqual(p.events,[[],[]])
    def test_driver_group_key_failure_stays_unauthorized(self):
        p=self.pair();p.fail_group=True;p.pump(.2)
        self.assertFalse(p.ready());self.assertEqual(p.events,[[],[]])
    def test_driver_rekey_failure_revokes_authorization(self):
        p=self.pair(rekey=1);p.pump(.2);self.assertTrue(p.ready())
        p.fail_group=True;p.pump(1.2)
        self.assertFalse(p.ready());self.assertEqual(p.events,[[1,0],[1,0]])
    def test_group_rekey(self):
        p=self.pair(rekey=1);p.pump(.2);self.assertTrue(p.ready())
        before=[len(side) for side in p.keys];p.pump(1.2)
        self.assertTrue(p.ready())
        for i in range(2):
            new=p.keys[i][before[i]:]
            self.assertTrue(any(k[2]>0 and len(k[4])==16 for k in new))
            tx=[k for k in new if k[2]>0 and k[3] and len(k[4])==16]
            self.assertEqual(len(tx),1)
            received=[k for k in p.keys[1-i][before[1-i]:] if k[2]>0 and not k[3]]
            self.assertTrue(any(k[2]==tx[0][2] and k[4]==tx[0][4] for k in received))
            old=[k[4] for k in p.keys[i][:before[i]] if k[2]>0 and k[3]]
            self.assertNotIn(tx[0][4],old)
        # Every group-key EAPOL exchange requests pairwise transport encryption.
        group=[packet for packet in p.sent if packet[1]==2 and
               not (int.from_bytes(packet[2][5:7],'big')&8)]
        self.assertEqual(len(group),4);self.assertTrue(all(packet[3] for packet in group))
    def test_replayed_handshake_does_not_reinstall_keys(self):
        p=self.pair();p.pump(.2);self.assertTrue(p.ready())
        counts=list(map(len,p.keys))
        # Replay every recorded EAPOL packet, including each message 3.
        for i,kind,data,encrypted in list(p.sent):
            if kind==2:
                self.lib.pocket_rsn_receive(p.nodes[1-i],buf(p.mac[i]),kind,buf(data),len(data),encrypted)
        p.pump(.1)
        self.assertEqual(list(map(len,p.keys)),counts);self.assertTrue(p.ready())
    def test_reconnect_uses_fresh_pairwise_key(self):
        p=self.pair();p.pump(.2);self.assertTrue(p.ready())
        old=next(k[4] for k in p.keys[0] if k[2]==0 and k[4]);p.close()
        q=self.pair();q.pump(.2);self.assertTrue(q.ready())
        new=next(k[4] for k in q.keys[0] if k[2]==0 and k[4]);self.assertNotEqual(old,new)
        counts=list(map(len,q.keys))
        for i,kind,data,encrypted in p.sent:
            if kind==2 and (int.from_bytes(data[5:7],'big')&0x1c0)==0x1c0:
                self.lib.pocket_rsn_receive(q.nodes[1-i],buf(q.mac[i]),kind,buf(data),len(data),encrypted)
        q.pump(.1);self.assertEqual(list(map(len,q.keys)),counts);self.assertTrue(q.ready())
    def test_lost_message_four_retransmits_without_key_reinstallation(self):
        p=self.pair();dropped=set()
        def drop(i,kind,data,encrypted):
            if kind==2 and int.from_bytes(data[5:7],'big')==0x30a and i not in dropped:
                dropped.add(i);return True
            return False
        p.pump(1.5,drop=drop)
        self.assertEqual(dropped,{0,1});self.assertTrue(p.ready())
        for side in p.keys:
            self.assertEqual(len([k for k in side if k[2]==0 and k[4]]),1)
    def test_input_bounds_and_peer_binding(self):
        p=self.pair();p.pump(.2);self.assertTrue(p.ready())
        node=p.nodes[0];peer=buf(p.mac[1]);frame=buf(b'\0'*1025)
        self.assertEqual(self.lib.pocket_rsn_receive(node,peer,2,frame,1025,0),-1)
        self.assertEqual(self.lib.pocket_rsn_receive(node,buf(p.mac[0]),2,frame,4,0),-1)
        self.assertEqual(self.lib.pocket_rsn_start(node,buf(bytes.fromhex('020000000001'))),-1)
        self.assertEqual(self.lib.pocket_rsn_receive(node,peer,1,frame,30,0),-1)

if __name__=='__main__':unittest.main(verbosity=2)
