import hashlib
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'shell/vendor/apps/domains/reticulum'))
from RNS.vendor import umsgpack
from data_bridge import DataBridge,SERVICE,projection

class Identity:
    def __init__(self,key=b'a'*64,create_keys=True):self.load_public_key(key)
    def load_public_key(self,key):self.key=key;self.hash=hashlib.sha256(key).digest()[:16]
    def get_public_key(self):return self.key
class Destination:
    IN,OUT,SINGLE,ALLOW_LIST=1,2,3,4
    def __init__(self,identity,*args):
        self.identity=identity;self.hash=identity.hash;self.links=[];self.announce=Mock();self.deregister_request_handler=Mock()
    def set_max_request_size(self,n):pass
    def register_request_handler(self,*args,**kwargs):pass
class Link:
    def __init__(self,destination,established_callback,closed_callback):
        self.destination=destination;self.established=established_callback;self.closed=closed_callback
        self.teardown=Mock();self.identify=Mock();self.request=Mock(return_value=object())
    def get_remote_identity(self):return self.destination.identity
class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.a,self.b=Identity(b'b'*64),Identity(b'c'*64)
        self.owner=SimpleNamespace(identity=Identity(),stack=object(),post=Mock(),book=SimpleNamespace(contacts={
            i.hash.hex():dict(state='verified',card=dict(public_key=i.key.hex())) for i in (self.a,self.b)}),
            RNS=SimpleNamespace(Identity=Identity,Destination=Destination,Link=Link,Transport=SimpleNamespace(
                has_path=Mock(return_value=True),request_path=Mock(),deregister_destination=Mock())))
        self.bridge=DataBridge(self.owner);self.addCleanup(self.bridge.close)
    def action(self,action,peer):
        self.bridge.dispatch('data_bridge_'+action,dict(peer=peer.hash.hex(),expected_public_key=peer.key.hex(),service=SERVICE,capabilities=['status']))
    def response(self,peer):return self.bridge.respond('',umsgpack.packb(dict(v=1,cap='status')),None,None,peer,None)
    def test_grant_does_not_announce_or_answer_public_path_probes(self):
        self.action('connect',self.a)
        original=self.bridge.destination.announce.__closure__
        announce=next(cell.cell_contents for cell in original if isinstance(cell.cell_contents,Mock))
        self.bridge.destination.announce(path_response=True)
        announce.assert_not_called()
        self.bridge.dispatch('service_discovery',dict(enabled=True))
        announce.assert_called_once()
        self.bridge.dispatch('service_discovery',dict(enabled=False))
        self.bridge.destination.announce(path_response=True)
        announce.assert_called_once()

    def test_multiple_grants_revocation_and_no_transitive_trust(self):
        self.assertIsNone(self.bridge.destination)
        self.action('connect',self.a);self.action('connect',self.b)
        self.assertIsNotNone(self.response(self.a));self.assertIsNotNone(self.response(self.b))
        self.assertIsNone(self.response(Identity(b'd'*64)))
        self.owner.book.contacts[self.a.hash.hex()]['state']='revoked'
        self.assertIsNone(self.response(self.a))
        self.bridge.revoke(self.a.hash.hex());self.assertIsNotNone(self.response(self.b))
    def test_request_does_not_grant_and_late_response_cannot_return(self):
        self.action('request',self.a);row=self.bridge.requests[self.a.hash.hex()];token=row['token'];link=row['link']
        self.assertFalse(self.bridge.grants);self.assertIsNone(self.bridge.destination)
        self.bridge.revoke(self.a.hash.hex());link.established(link)
        self.bridge.received(self.a.hash.hex(),token,SimpleNamespace(response=umsgpack.packb(dict(v=1,station=self.a.hash.hex(),epoch='a'*16,capability='status',snapshot=projection({})))))
        self.assertFalse(self.bridge.requests);link.teardown.assert_called()
    def test_parallel_requests_and_malformed_responses(self):
        for peer in (self.a,self.b):self.action('request',peer)
        with self.assertRaises(ValueError):self.action('request',self.a)
        row=self.bridge.requests[self.a.hash.hex()]
        self.bridge.received(self.a.hash.hex(),row['token'],SimpleNamespace(response=b'x'*2049))
        self.assertFalse(row['pending']);self.assertIsNotNone(row['error'])
        self.assertTrue(self.bridge.requests[self.b.hash.hex()]['pending'])
    def test_malformed_and_unverified_requests_cannot_share(self):
        self.owner.book.contacts[self.a.hash.hex()]['state']='unverified'
        with self.assertRaises(ValueError):self.action('connect',self.a)
        self.action('connect',self.b)
        for raw in (b'\xc1',b'x'*257,umsgpack.packb(dict(v=True,cap='status')),umsgpack.packb(dict(v=1,cap='history'))):
            self.assertIsNone(self.bridge.respond('',raw,None,None,self.b,None))
    def test_synchronous_close_during_link_creation_does_not_retain_link(self):
        def closed(destination,established_callback,closed_callback):
            link=Link(destination,established_callback,closed_callback);closed_callback(link);self.link=link;return link
        self.owner.RNS.Link=closed
        self.action('request',self.a)
        row=self.bridge.requests[self.a.hash.hex()]
        self.assertFalse(row['pending']);self.assertIsNone(row['link']);self.link.teardown.assert_called_once()

class ServiceTests(BridgeTests):
    def grant(self,peer,operations):
        self.bridge.services.register('notes','/tmp/fixture-owner.sock',['put'])
        self.bridge.services.grant(dict(peer=peer.hash.hex(),expected_public_key=peer.key.hex(),service='notes',operations=operations))
    def invoke(self,peer,request,identity='a'*32):
        from service_transport import encode
        raw=encode(dict(version=1,id=identity,service='notes',request=request))
        return self.bridge.services.respond('',raw,None,None,peer,None)
    def test_command_permissions_duplicate_suppression_and_revocation(self):
        import json
        from unittest.mock import patch
        from service_transport import decode
        self.grant(self.a,['snapshot','put']);self.grant(self.b,['snapshot'])
        transport=Mock();transport.exchange.return_value=dict(version=1,written=True)
        with patch('service_bridge.SocketTransport',return_value=transport):
            request=dict(version=1,action='put',payload=dict(value='message'))
            self.assertTrue(decode(self.invoke(self.a,request))['written'])
            self.assertTrue(decode(self.invoke(self.a,request))['written'])
            transport.exchange.assert_called_once()
            with self.assertRaisesRegex(ValueError,'different operation'):
                decode(self.invoke(self.a,dict(version=1,action='put',payload=dict(value='changed'))))
            with self.assertRaisesRegex(ValueError,'not granted'):decode(self.invoke(self.b,request))
            self.bridge.revoke(self.a.hash.hex())
            with self.assertRaisesRegex(ValueError,'not granted'):decode(self.invoke(self.a,request))
    def test_authorization_is_checked_after_local_operation(self):
        from unittest.mock import patch
        from service_transport import decode
        self.grant(self.a,['put'])
        def operate(request):
            self.owner.book.contacts[self.a.hash.hex()]['state']='revoked'
            return dict(version=1,secret='must not be returned')
        with patch('service_bridge.SocketTransport',return_value=SimpleNamespace(exchange=operate)):
            with self.assertRaisesRegex(ValueError,'revoked'):
                decode(self.invoke(self.a,dict(version=1,action='put')))
    def test_out_of_order_or_cancelled_updates_cannot_replace_current_state(self):
        from service_transport import encode
        identifier=(self.a.hash.hex(),'notes','s'*16)
        row=dict(active=True,key=self.a.key,snapshot=None,link=None)
        self.bridge.services.clients[identifier]=row
        def update(sequence,value):self.bridge.services.accept_update(identifier,row,encode(dict(version=1,sequence=sequence,snapshot=dict(version=1,value=value))))
        update(2,'new');update(1,'old');self.assertEqual(row['snapshot']['value'],'new')
        self.bridge.services.cancel(dict(zip(('peer','service','session'),identifier)))
        update(3,'late');self.assertNotIn(identifier,self.bridge.services.clients)

    def test_slow_subscription_coalesces_to_latest_and_revoke_stops_it(self):
        import threading
        self.grant(self.a,['subscribe'])
        sent=[]
        def resource(raw,link,callback,auto_compress):sent.append((raw,callback))
        resource.COMPLETE=7;self.owner.RNS.Resource=resource
        identifier=(self.a.hash.hex(),'notes',b'link')
        row=dict(stop=threading.Event(),transport=Mock(),link=Mock(),latest=b'first',sending=False)
        self.bridge.services.subscribers[identifier]=row
        self.bridge.services.push(identifier)
        row['latest']=b'intermediate';self.bridge.services.push(identifier)
        row['latest']=b'latest';self.bridge.services.push(identifier)
        self.assertEqual([r[0] for r in sent],[b'first'])
        sent[0][1](SimpleNamespace(status=7))
        self.assertEqual([r[0] for r in sent],[b'first',b'latest'])
        self.bridge.revoke(self.a.hash.hex());self.assertTrue(row['stop'].is_set());row['transport'].close.assert_called()
        sent[1][1](SimpleNamespace(status=7));self.assertEqual(len(sent),2)

    def test_failed_grant_change_keeps_previous_permissions(self):
        self.grant(self.a,['snapshot'])
        self.bridge.destination.register_request_handler=Mock(side_effect=RuntimeError('offline'))
        with self.assertRaises(RuntimeError):self.grant(self.a,['snapshot','put'])
        self.assertEqual(self.bridge.services.grants[self.a.hash.hex(),'notes'][1],frozenset(['snapshot']))

if __name__=='__main__':unittest.main()
