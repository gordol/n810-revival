"""Radio revision comparisons must stay typed and notice mutable producers."""
from pathlib import Path
import copy,sys,unittest
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'shell'))
import radio_state

class SnapshotCacheTests(unittest.TestCase):
    def test_tokens_preserve_types_and_equal_copies(self):
        values=[{'value':value} for value in (False,0,0.0,True,1,1.0,'1',None,2**100)]
        tokens=[radio_state.snapshot_token(value) for value in values]
        self.assertEqual(len(set(tokens)),len(values))
        value={'rows':[{'value':1}]*2}
        self.assertEqual(radio_state.snapshot_token(value),radio_state.snapshot_token(copy.deepcopy(value)))
        before=radio_state.snapshot_token(value)
        value['rows'][0]['value']=2
        self.assertNotEqual(before,radio_state.snapshot_token(value))

    def test_same_object_edits_invalidate_retained_cache(self):
        payload={'catalog':{'radio_snapshot':{'label':'before'}},'live':{'captured':100.}}
        source=SimpleNamespace(read=lambda now:payload)
        state=radio_state.State(source=source,clock=lambda:100.)
        with patch.object(radio_state.adapter.model,'normalize_catalog',wraps=radio_state.adapter.model.normalize_catalog) as normalize:
            state.update();first=state.catalog_token
            state._source_changed();state.update()
            self.assertEqual(normalize.call_count,1)
            payload['catalog']['radio_snapshot']['label']='after!'
            state._source_changed();state.update()
            self.assertEqual(normalize.call_count,2)
            self.assertNotEqual(state.catalog_token,first)
            payload['catalog']['radio_snapshot']['label']=True
            state._source_changed();state.update();first=state.catalog_token
            payload['catalog']['radio_snapshot']['label']=1
            state._source_changed();state.update()
            self.assertNotEqual(state.catalog_token,first)

    def test_ages_and_connectivity_change_without_catalog_rebuild(self):
        now=[100.]
        payload={'live':{'captured':100.,'history_source':'feed'}}
        state=radio_state.State(source=SimpleNamespace(read=lambda now:payload),clock=lambda:now[0])
        state.update();catalog=state.catalog_model
        now[0]=135.;state.update()
        self.assertEqual(state.result,radio_state.adapter.adapt(payload,now[0]))
        payload['live'].update(receive_subscription=True,receive_connected=False)
        state._source_changed();state.update()
        self.assertEqual(state.result,radio_state.adapter.adapt(payload,now[0]))
        self.assertIs(state.catalog_model,catalog)
        self.assertFalse(state.result['statusbar']['feed']['transport_connected'])

    def test_cached_projection_detaches_nested_source_values(self):
        profiles={'test':{'channels':[{'enabled':True,'power':1.5}]}}
        payload={'catalog':{'radio_profiles':{'profiles':profiles}}}
        state=radio_state.State(source=SimpleNamespace(read=lambda now:payload))
        state.update();saved=state.catalog_model
        profiles['test']['channels'][0]['power']=2.5
        self.assertEqual(saved['presets']['profiles']['test']['channels'][0]['power'],1.5)
        state._source_changed();state.update()
        self.assertEqual(state.catalog_model['presets']['profiles']['test']['channels'][0]['power'],2.5)
        self.assertEqual(saved['presets']['profiles']['test']['channels'][0]['power'],1.5)

    def test_failed_projection_is_retried(self):
        state=radio_state.State(source=SimpleNamespace(read=lambda now:{}))
        with patch.object(radio_state.adapter,'adapt',side_effect=ValueError('bad projection')):
            with self.assertRaises(ValueError):state.update()
        self.assertIsNone(state.catalog_token)
        self.assertEqual(state._consumed_generation,0)
        state.update();self.assertIsNotNone(state.catalog_token)

    def test_system_and_packet_updates_publish_without_reprojecting_radio(self):
        payload={'live':{'system':{'observed_at':100.},'packets':[]}}
        source=SimpleNamespace(read=lambda now:payload)
        state=radio_state.State(source=source,clock=lambda:100.)
        state.update();result=state.result
        payload={'live':{'system':{'observed_at':105.},'packets':[{'raw':'new'}]}}
        with patch.object(radio_state.adapter,'adapt',wraps=radio_state.adapter.adapt) as adapt:
            state._source_changed();state.update()
            self.assertEqual(adapt.call_count,0)
        self.assertIs(state.result,result)
        self.assertEqual(state.payload['live']['system']['observed_at'],105.)
        self.assertEqual(state.payload['live']['packets'],[{'raw':'new'}])

    def test_arrival_during_read_remains_pending(self):
        state=radio_state.State()
        state.source=SimpleNamespace(read=lambda now:(state._source_changed() or {}))
        state.update();self.assertTrue(state.publication_pending())

if __name__=='__main__':unittest.main()

class DynamicReadEndpointTests(unittest.TestCase):
    def test_connection_change_adopts_control_endpoint_without_reading_radio(self):
        source=SimpleNamespace(read=lambda now:{},radio_read_endpoint=None)
        state=radio_state.State(source=source)
        try:
            state.update();self.assertFalse(state.can_read)
            source.radio_read_endpoint=Path('/tmp/test-bridge/radio-control.sock')
            state._source_changed();state.update()
            client=state.read_client
            self.assertTrue(state.can_read);self.assertEqual(client.path,source.radio_read_endpoint)
            self.assertIsNone(client.worker);self.assertIsNone(client.request)
            source.radio_read_endpoint=None;state._source_changed();state.update()
            self.assertFalse(state.can_read);self.assertTrue(client.closed)
        finally:state.close()
    def test_explicit_endpoint_is_not_replaced_by_connection(self):
        from radio_read_client import RadioRead
        explicit=RadioRead('/tmp/explicit-radio/control.sock')
        source=SimpleNamespace(read=lambda now:{},radio_read_endpoint=Path('/tmp/other/control.sock'))
        state=radio_state.State(source=source,read_client=explicit)
        try:state.update();self.assertIs(state.read_client,explicit)
        finally:state.close()
    def test_live_owner_change_time_is_not_presented_as_stale_telemetry(self):
        state=radio_state.State()
        state.result={'statusbar':{'radio':{'link':dict(source='feed_live_owner',current_known=True,observed_at=100.,age_seconds=80000,freshness='current')}}}
        text=state.link_observation()
        self.assertIn('last changed',text);self.assertIn('live owner subscribed',text)
        self.assertNotIn('age 80000',text)

    def test_snapshot_receipt_does_not_redate_received_packets(self):
        import time_display
        state=radio_state.State()
        state.payload={'live':{'data':{'captured':1793904000.,'raw_records':[
            {'time':'2026-11-05T17:51:32+00:00','direction':'radio_to_host'},
            {'time':'2026-11-05T18:59:00+00:00','direction':'host_to_radio_written'}]}}}
        with patch.object(time_display,'_zone',__import__('datetime').timezone.utc):
            lines=state.receive_observations()
        self.assertIn('2026-11-05 17:51:32',lines[0])
        self.assertTrue(lines[1].startswith('Receive snapshot loaded:'))
        self.assertNotEqual(lines[0].split(': ',1)[1],lines[1].split(': ',1)[1])

class ReconnectedRadioTests(unittest.TestCase):
    def test_reused_forwarded_path_discards_old_device_readback(self):
        source=SimpleNamespace(source=object(),read=lambda now:{},radio_read_endpoint=Path('/tmp/reused-radio/control.sock'))
        state=radio_state.State(source=source)
        try:
            state.update();previous=state.read_client
            state.read_telemetry={'version':2,'published_at':100,'station':'old-device'}
            source.source=object()
            state._source_changed();state.update()
            self.assertTrue(previous.closed)
            self.assertIsNot(state.read_client,previous)
            self.assertIsNone(state.read_telemetry)
            self.assertIsNone(state.read_client.worker)
        finally:state.close()
