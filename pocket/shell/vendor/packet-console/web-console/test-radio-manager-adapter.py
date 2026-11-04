import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
spec=importlib.util.spec_from_file_location('radio_manager',Path(__file__).with_name('radio-manager-adapter.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)
NOW=2000000000


def sample():
    return dict(live={'data':{'captured':'2033-05-18T03:33:20+00:00','history_source':'feed RAM snapshot',
                             'radio_live':dict(heartbeat=NOW,connected=True,enabled=False,fields={})}},
                connector={'ssh':{'success':True,'observed_at':NOW}})


class Tests(unittest.TestCase):
    def test_link_up_with_paused_unknown_details(self):
        result=a.adapt(sample(),NOW)
        self.assertEqual(result['statusbar']['radio']['state'],'paused')
        self.assertEqual(result['statusbar']['radio']['link']['state'],'reported_up')
        self.assertEqual(result['statusbar']['radio']['label'],'Radio connected; detailed telemetry paused')
        self.assertEqual(a.adapt(sample(),NOW+16)['statusbar']['radio']['label'],'Radio observation stale')
        self.assertIsNone(result['model']['live']['active']['selected_memory_index'])
        self.assertEqual(result['statusbar']['ssh']['state'],'recent')
        self.assertEqual(result['statusbar']['feed']['state'],'recent')
        self.assertAlmostEqual(result['next_invalidation_at'],NOW+15.001,places=3)

    def test_feed_traffic_not_bluetooth_proof(self):
        p=sample();p['live']['data']['radio_live']=None
        r=a.adapt(p,NOW)
        self.assertEqual(r['statusbar']['feed']['state'],'recent')
        self.assertEqual(r['statusbar']['radio']['link']['state'],'unknown')
        self.assertEqual(r['statusbar']['radio']['state'],'unavailable')

    def test_missing_transport_evidence_not_connected(self):
        p=sample();del p['connector']
        self.assertEqual(a.adapt(p,NOW)['statusbar']['ssh']['state'],'unknown')
        p['connector']={'ssh':{'success':1,'observed_at':NOW}}
        self.assertEqual(a.adapt(p,NOW)['statusbar']['ssh']['state'],'unknown')

    def test_old_and_failed_transport_is_independent(self):
        p=sample();p['connector']['ssh']['success']=False
        self.assertEqual(a.adapt(p,NOW)['statusbar']['ssh']['state'],'failed')
        p['live']['error']='SSH unavailable'
        self.assertEqual(a.adapt(p,NOW)['statusbar']['feed']['state'],'stale')
        r=a.adapt(p,NOW+31)
        self.assertEqual(r['statusbar']['ssh']['state'],'stale')
        self.assertEqual(r['statusbar']['radio']['link']['state'],'unknown')
        self.assertEqual(r['statusbar']['radio']['link']['freshness'],'stale')
        self.assertFalse(r['statusbar']['radio']['link']['current_known'])
        self.assertEqual(r['statusbar']['radio']['state'],'owner_unavailable')
        self.assertEqual(r['statusbar']['radio']['label'],'Radio observation stale')

    def test_no_factory_presets_or_write_capabilities(self):
        r=a.adapt({},NOW)
        self.assertEqual(r['model']['presets']['banks'],[])
        self.assertEqual(r['model']['presets']['profiles'],{})
        for name in ('hardware_commands','telemetry_control','preset_write'):self.assertFalse(r['capabilities'][name])
        with self.assertRaises(ValueError):a.adapt({'operation':'tune'},NOW)

    def test_comparison_resolves_explicit_pair(self):
        p=sample();p.update(operation='compare',selection=dict(bank_index=0,memory_index=0,preset_bank_id='b',preset_channel_id='c'),
          catalog=dict(radio_snapshot=dict(complete=True,banks=[dict(index=0,name='Ham',channels=[dict(index=0,decoded=dict(channel_id=0,name_str='APRS',rx_freq=144390000))])]),
                       radio_banks=dict(banks=[dict(id='b',name='Draft',channels=[dict(id='c',name='APRS',rx_mhz=144.39)])])))
        r=a.adapt(p,NOW)
        self.assertEqual(next(f for f in r['comparison']['fields'] if f['field']=='rx_hz')['state'],'equal')
        for value in (True,'0',-1):
            p['selection']['memory_index']=value
            with self.assertRaises(ValueError):a.adapt(p,NOW)
        p['selection']['memory_index']=0
        p['catalog']['radio_banks']['banks'].append(copy.deepcopy(p['catalog']['radio_banks']['banks'][0]))
        with self.assertRaises(ValueError):a.adapt(p,NOW)

    def test_normalized_cached_data_expires(self):
        t=dict(mode='live',connected=True,enabled=True,heartbeat_age_seconds=0,
               sections={'status':dict(state='fresh',age_seconds=19,values={'curr_region':0})},active={'bank_index':0})
        p={'live':{'captured':'2033-05-18T03:33:20+00:00','radio_model':{'live':t}}}
        self.assertEqual(a.adapt(p,NOW+2)['statusbar']['radio']['state'],'stale')
        self.assertEqual(a.adapt(p,NOW+16)['statusbar']['radio']['state'],'owner_unavailable')
        self.assertEqual(t['sections']['status']['state'],'fresh')

    def test_signal_projection_does_not_revive_paused_or_aged_cache(self):
        p=sample();t=p['live']['data']['radio_live']
        t.update(status=dict(rssi=15,is_in_rx=False,is_in_tx=True),fields={'status':NOW})
        self.assertIsNone(a.adapt(p,NOW)['statusbar']['radio']['indicators']['signal']['raw'])
        t['enabled']=True
        self.assertEqual(a.adapt(p,NOW)['statusbar']['radio']['indicators']['signal']['raw'],15)
        self.assertTrue(a.adapt(p,NOW)['statusbar']['radio']['indicators']['activity']['tx'])
        self.assertIsNone(a.adapt(p,NOW+16)['statusbar']['radio']['indicators']['signal']['raw'])
        normalized=a.model.normalize_radio({},t,NOW)
        p['live']['data'].pop('radio_live');p['live']['data']['radio_model']=normalized
        self.assertIsNone(a.adapt(p,NOW+16)['statusbar']['radio']['indicators']['signal']['raw'])

    def test_downloaded_bank_list_survives_absent_local_drafts(self):
        # Historical bank names; synthetic channel data, not a new device read.
        names=['Ham','GMRS','GMRS WA','MURS/FRS','Marine','WA Interop']
        p=sample();p['catalog']={'radio_snapshot':{'complete':True,'banks':[
            {'index':i,'name':name,'channels':[]} for i,name in enumerate(names)]},
            'radio_banks':None,'radio_profiles':None}
        before=copy.deepcopy(p)
        result=a.adapt(p,NOW)
        self.assertEqual([b['name'] for b in result['model']['snapshot']['banks']],names)
        self.assertEqual([b['index'] for b in result['model']['snapshot']['banks']],list(range(6)))
        self.assertEqual(result['model']['presets']['banks'],[])
        self.assertEqual(result['model']['presets']['profiles'],{})
        self.assertEqual(result['statusbar']['radio']['state'],'paused')
        self.assertFalse(result['capabilities']['hardware_commands'])
        self.assertEqual(p,before)

    def test_no_input_mutation(self):
        p=sample();before=copy.deepcopy(p);a.adapt(p,NOW);self.assertEqual(p,before)

    def test_cli_offline_and_unsupported(self):
        path=Path(__file__).with_name('radio-manager-adapter.py')
        ok=subprocess.run([sys.executable,str(path)],input='{}',text=True,capture_output=True)
        self.assertEqual(ok.returncode,0);self.assertEqual(json.loads(ok.stdout)['statusbar']['radio']['state'],'unavailable')
        bad=subprocess.run([sys.executable,str(path)],input='{"operation":"transmit"}',text=True,capture_output=True)
        self.assertEqual(bad.returncode,2);self.assertTrue(json.loads(bad.stdout)['read_only'])


if __name__=='__main__':unittest.main()
