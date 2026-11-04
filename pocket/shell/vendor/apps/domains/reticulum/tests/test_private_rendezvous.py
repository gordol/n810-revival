"""Private-contact selection checks without network access or external dependencies."""
import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from private_rendezvous import destination_for

class Identity:
    def __init__(self,create_keys=False):pass
    def load_public_key(self,key):self.hash=hashlib.sha256(key).digest()[:16]

class PrivateContact(unittest.TestCase):
    def setUp(self):
        self.key=bytes(range(64));self.peer=hashlib.sha256(self.key).digest()[:16].hex()
        self.records={self.peer:dict(state='verified',card=dict(public_key=self.key.hex()))}
        self.calls=[]
        def destination(identity,*args):
            self.calls.append(args)
            return SimpleNamespace(hash=b'destination')
        self.RNS=SimpleNamespace(Identity=Identity,Destination=SimpleNamespace())
        class Dest:
            OUT=1;SINGLE=0
            def __new__(cls,identity,*args):return destination(identity,*args)
        self.RNS.Destination=Dest
        self.RNS.Transport=SimpleNamespace(has_path=lambda value:False)
        self.owner=SimpleNamespace(book=SimpleNamespace(contacts=self.records),RNS=self.RNS,stack=object(),identity=object())

    def test_verified_direct_contact_no_probe_or_grant(self):
        d,route=destination_for(self.owner,self.peer,self.key)
        self.assertEqual(route,'direct_contact')
        self.assertEqual(self.calls,[(1,0,'pocket','data','v1')])
        self.assertEqual(self.records[self.peer]['state'],'verified')

    def test_existing_route_is_reused(self):
        self.RNS.Transport.has_path=lambda value:True
        self.assertEqual(destination_for(self.owner,self.peer)[1],'cached_path')

    def test_unverified_revoked_changed_and_bad_identity_rejected(self):
        for state in ('unverified','revoked'):
            self.records[self.peer]['state']=state
            with self.assertRaises(ValueError):destination_for(self.owner,self.peer)
        self.records[self.peer]['state']='verified'
        with self.assertRaises(ValueError):destination_for(self.owner,self.peer,bytes(64))
        self.records[self.peer]['card']['public_key']=bytes(64).hex()
        with self.assertRaises(ValueError):destination_for(self.owner,self.peer)
        self.assertEqual(self.calls,[])

    def test_no_implicit_transport_start(self):
        self.owner.stack=None
        with self.assertRaises(ValueError):destination_for(self.owner,self.peer)
        self.assertEqual(self.calls,[])
        for peer in ('',self.peer[:8],self.peer.upper()+'0',None):
            with self.assertRaises(ValueError):destination_for(self.owner,peer)

if __name__=='__main__':unittest.main()
