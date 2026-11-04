import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('radio_read_model',Path(__file__).with_name('radio-read-model.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=2000000000


def native(**changes):
    p=dict(channel_id=0,name_str='APRS',rx_freq=144390000,tx_freq=144990000,rx_sub_audio=0,
           tx_sub_audio=10000,rx_mod=0,tx_mod=1,bandwidth=0,tx_at_max_power=False,
           tx_at_med_power=True,tx_disable=True,scan=False,mute=False,talk_around=False,
           pre_de_emph_bypass=True)
    p.update(changes)
    return dict(index=0,response={'status':0},decoded=p)


def catalog(row=None):
    return {'radio_snapshot':{'complete':True,'finished':'2026-10-16T12:00:00Z','banks':[
        {'index':0,'name':'Ham','channels':[row or native()]}]}}


def telemetry():
    return dict(connected=True,enabled=True,heartbeat=NOW-1,fields=dict(status=NOW-1,settings=NOW-2,beacon=NOW-3),
                status=dict(curr_region=0,curr_ch_id_lower=0,curr_channel_id_upper=0,is_in_tx=False,is_in_rx=True),
                settings=dict(channel_a_lower=0,channel_a_upper=0,channel_b_lower=2,channel_b_upper=0,
                              auto_share_loc_ch=1,auto_share_loc_ch_upper=0),beacon={'should_share_location':False})


class ModelTests(unittest.TestCase):
    def test_normalized_units_and_flags(self):
        c=m.normalize_radio(catalog(),None,NOW)['snapshot']['banks'][0]['channels'][0]
        self.assertEqual((c['rx_hz'],c['offset_hz']),(144390000,600000))
        self.assertEqual(c['rx_tone'],{'kind':'off','value':None})
        self.assertEqual(c['tx_tone'],{'kind':'ctcss','value':100})
        self.assertEqual(c['tx_mode'],'AM');self.assertEqual(c['power'],'Medium')
        self.assertFalse(c['tx_enabled']);self.assertEqual(c['bandwidth'],'Narrow')
        self.assertEqual(m.tone(23),{'kind':'dcs','value':23})

    def test_empty_is_distinct_from_failed_or_truncated(self):
        self.assertEqual(m.channel(native(rx_freq=0),0)['state'],'empty')
        row=native();row['response']['status']=1
        self.assertEqual(m.channel(row,0)['state'],'unavailable')
        self.assertEqual(m.channel(native(_decoded_bits=160,_available_bits=200),0)['state'],'unavailable')
        self.assertEqual(m.channel({'index':0},0)['state'],'unavailable')

    def test_missing_flags_remain_unknown(self):
        c=m.channel({'index':0,'decoded':{'rx_freq':144390000}},0)
        for key in ('power','bandwidth','tx_enabled','scan','rx_mode','rx_tone'):
            self.assertIsNone(c[key])

    def test_snapshot_validation(self):
        for update in ({'complete':False},{'restore_bank':{},'restored':False}):
            c=catalog();c['radio_snapshot'].update(update)
            result=m.normalize_radio(c,None,NOW)['snapshot']
            self.assertFalse(result['available']);self.assertEqual(result['banks'],[])

    def test_live_indices_and_digital_zero(self):
        t=telemetry();v=m.normalize_radio({},t,NOW)['live']
        self.assertEqual(v['mode'],'live')
        self.assertEqual(v['active']['selected_memory_index'],0)
        self.assertEqual(v['active']['digital_memory_index'],0)
        self.assertEqual(v['active']['activity'],'RX')
        t['settings']['auto_share_loc_ch']=0
        a=m.normalize_radio({},t,NOW)['live']['active']
        self.assertTrue(a['digital_current']);self.assertIsNone(a['digital_memory_index'])

    def test_section_freshness_not_capture_time(self):
        t=telemetry();t['fields']['settings']=NOW-46;t['fields']['beacon']=NOW-76
        v=m.normalize_radio({},t,NOW)['live']
        self.assertEqual(v['mode'],'live')
        self.assertEqual(v['sections']['settings']['state'],'stale')
        self.assertEqual(v['sections']['beacon']['state'],'stale')
        t['fields']['status']=NOW-21
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'stale')

    def test_disconnected_paused_and_old_heartbeat(self):
        t=telemetry();t['enabled']=False
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'paused')
        t['connected']=False
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'disconnected')
        t['heartbeat']=NOW-16
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'disconnected')
        self.assertEqual(m.normalize_radio({},None,NOW)['live']['mode'],'unavailable')

    def test_paused_one_shot_uses_actual_reply_age_and_provenance(self):
        t=telemetry();t['enabled']=False;t['status']['rssi']=7
        t['read_request']=dict(operation='read_current',state='complete',results={
            '20':dict(observed_at=t['fields']['status'],decoded=copy.deepcopy(t['status']))})
        v=m.normalize_radio({},t,NOW)['live']
        self.assertEqual(v['sections']['status']['state'],'fresh')
        self.assertEqual(v['sections']['status']['source'],'one_shot')
        self.assertEqual(v['sections']['settings']['state'],'paused')
        self.assertEqual(v['indicators']['signal']['raw'],7);self.assertFalse(v['enabled'])
        t['heartbeat']=NOW+25
        v=m.normalize_radio({},t,NOW+26)['live']
        self.assertEqual(v['sections']['status']['state'],'stale')
        self.assertIsNone(v['indicators']['signal']['raw'])
        t['read_request']['results']['20']['observed_at']=NOW
        self.assertEqual(m.normalize_radio({},t,NOW+26)['live']['sections']['status']['state'],'paused')
    def test_one_shot_does_not_override_disconnect_or_owner_age(self):
        t=telemetry();t['enabled']=False
        t['read_request']=dict(operation='read_current',results={'20':dict(observed_at=t['fields']['status'],decoded=copy.deepcopy(t['status']))})
        t['connected']=False
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'disconnected')
        t['connected']=True;t['heartbeat']=NOW-16
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'owner_unavailable')

    def test_disconnected_evidence_survives_owner_expiry(self):
        t=telemetry();t['connected']=False;t['heartbeat']=NOW
        for elapsed in (0,16,60):
            v=m.normalize_radio({},t,NOW+elapsed)['live'];link=v['link']
            self.assertEqual(v['mode'],'disconnected')
            self.assertEqual(link['state'],'reported_down')
            self.assertFalse(link['last_reported_connected'])
            self.assertEqual(link['observed_at'],NOW);self.assertEqual(link['age_seconds'],elapsed)
            self.assertEqual(link['freshness'],'recent' if elapsed<=15 else 'stale')
            if elapsed>15:
                self.assertIsNone(v['connected']);self.assertFalse(link['current_known'])
                self.assertEqual(v['sections']['status']['state'],'owner_unavailable')
                self.assertIsNone(v['indicators']['signal']['raw'])
    def test_stale_up_is_not_current_and_new_observation_replaces_down(self):
        t=telemetry();t['heartbeat']=NOW;t['connected']=True
        v=m.normalize_radio({},t,NOW+16)['live']
        self.assertEqual(v['link']['state'],'unknown');self.assertIsNone(v['connected'])
        self.assertTrue(v['link']['last_reported_connected'])
        t['connected']=False
        self.assertEqual(m.normalize_radio({},t,NOW+16)['live']['mode'],'disconnected')
        t['connected']=True;t['heartbeat']=NOW+17
        v=m.normalize_radio({},t,NOW+17)['live']
        self.assertEqual(v['link']['state'],'reported_up');self.assertTrue(v['connected'])
    def test_missing_invalid_time_or_flag_stays_unknown(self):
        for stamp in (None,0,NOW+6,float('nan')):
            t=telemetry();t['connected']=False;t['heartbeat']=stamp
            v=m.normalize_radio({},t,NOW)['live']
            self.assertEqual(v['link']['state'],'unknown');self.assertIsNone(v['connected'])
            self.assertIsNone(v['link']['observed_at'])
        t=telemetry();del t['connected']
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'unknown')
    def test_fetch_or_packet_dates_never_refresh_link(self):
        t=telemetry();t['heartbeat']=NOW-60;t['connected']=False
        t['captured']=NOW;t['last_packet']=NOW;t['fields']['status']=NOW
        v=m.normalize_radio({'captured':NOW},t,NOW)['live']
        self.assertEqual(v['link']['age_seconds'],60);self.assertEqual(v['link']['freshness'],'stale')
        self.assertEqual(v['mode'],'disconnected')

    def test_future_and_missing_times(self):
        for stamp in (NOW+6,float('nan'),0):
            t=telemetry();t['heartbeat']=stamp
            self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'owner_unavailable')
        t=telemetry();del t['fields']['status']
        self.assertEqual(m.normalize_radio({},t,NOW)['live']['mode'],'waiting')

    def test_never_fills_live_values_from_download(self):
        v=m.normalize_radio(catalog(),{},NOW)
        self.assertTrue(v['snapshot']['available'])
        self.assertIsNone(v['live']['active']['bank_index'])
        self.assertEqual(v['live']['sections']['settings']['values'],{})

    def test_draft_comparison_is_explicit_and_partial(self):
        c=m.channel(native(),0)
        draft=m.draft_channel(dict(id='uuid',name='APRS',rx_mhz=144.39,tx_mhz=144.99,
                                  rx_ctcss=None,tx_ctcss=100,power='Low',bandwidth='Narrow',
                                  scan=False,tx_enabled=False))
        comparison={r['field']:r['state'] for r in m.compare_channels(c,draft)['fields']}
        self.assertEqual(comparison['rx_hz'],'equal')
        self.assertEqual(comparison['power'],'different')
        self.assertEqual(comparison['tx_mode'],'not_represented')
        draft['tx_tone']=None
        self.assertEqual(next(r for r in m.compare_channels(c,draft)['fields'] if r['field']=='tx_tone')['state'],'unknown')
        self.assertIsNone(draft['hardware_slot'])

    def test_complete_group_lists_and_saved_membership_counts(self):
        c=catalog();c['radio_snapshot']['banks'].append(dict(index=5,name='WA Interop',channels=[]))
        c['radio_banks']={'version':1,'banks':[dict(id='saved-a',name='Local',channels=[dict(id='row-a',name='Draft',rx_mhz=146.52)]),dict(id='saved-b',name='Empty local',channels=[])]}
        r=m.normalize_radio(c,None,NOW)
        self.assertEqual([(b['index'],b['name']) for b in r['snapshot']['banks']],[(0,'Ham'),(5,'WA Interop')])
        self.assertEqual([(b['id'],b['channel_count']) for b in r['presets']['banks']],[('saved-a',1),('saved-b',0)])
        self.assertTrue(all(b['source']=='saved_draft' for b in r['presets']['banks']))
        self.assertEqual(m.normalize_radio({},None,NOW)['presets']['banks'],[])

    def test_no_input_mutation(self):
        c=catalog();t=telemetry();before=copy.deepcopy((c,t))
        result=m.normalize_radio(c,t,NOW);result['live']['sections']['status']['values']['curr_region']=9
        self.assertEqual((c,t),before)

    def test_fixed_and_raw_sign_flags(self):
        row=native(fixed_freq=True,fixed_bandwidth=False,fixed_tx_power=True,sign=False)
        c=m.channel(row,0)
        self.assertTrue(c['fixed_freq']);self.assertFalse(c['fixed_bandwidth'])
        self.assertTrue(c['fixed_tx_power']);self.assertFalse(c['sign'])
        row['response']['status']=1
        for key in ('fixed_freq','fixed_bandwidth','fixed_tx_power','sign'):
            self.assertIsNone(m.channel(row,0)[key])
            self.assertIsNone(m.channel(native(),0)[key])

    def test_relative_signal_and_activity_require_fresh_status(self):
        t=telemetry();t['status']['rssi']=0
        v=m.normalize_radio({},t,NOW)['live']['indicators']
        self.assertEqual(v['signal']['raw'],0);self.assertEqual(v['signal']['maximum'],15)
        self.assertEqual(v['signal']['unit'],'relative')
        self.assertTrue(v['activity']['rx']);self.assertFalse(v['activity']['tx'])
        for state in ('paused','stale','disconnected','owner_unavailable'):
            sections={'status':{'state':state,'values':t['status'],'observed_at':NOW-1,'age_seconds':1}}
            i=m.status_indicators(sections)
            self.assertIsNone(i['signal']['raw']);self.assertEqual(i['signal']['last_reported_raw'],0)
            self.assertIsNone(i['activity']['rx']);self.assertIsNone(i['activity']['tx'])
        for raw in (None,True,-1,16,7.5):
            t['status']['rssi']=raw
            i=m.normalize_radio({},t,NOW)['live']['indicators']
            self.assertEqual(i['signal']['state'],'unknown');self.assertIsNone(i['signal']['raw'])

    def test_channel_index_mismatch_exposed(self):
        c=m.channel(native(channel_id=3),0)
        self.assertTrue(c['index_mismatch']);self.assertEqual(c['state'],'unavailable')
        self.assertTrue(c['diagnostics']);self.assertIsNone(c['rx_hz'])
        draft=m.draft_channel(dict(name='APRS',rx_mhz=144.39))
        result={r['field']:r['state'] for r in m.compare_channels(c,draft)['fields']}
        self.assertEqual(result['name'],'unknown')
        self.assertEqual(result['rx_hz'],'unknown')

    def test_invalid_fixed_lookup_identity_is_unavailable(self):
        for index in (None,True,-1,256,'0'):
            row=native();row['index']=index
            c=m.channel(row,0)
            self.assertEqual(c['state'],'unavailable');self.assertTrue(c['diagnostics'])
        self.assertEqual(m.channel(native(),0)['index'],0)

    def test_failed_reply_never_compares_cached_decoded_values(self):
        row=native();row['response']['status']=1
        c=m.channel(row,0)
        self.assertEqual(c['state'],'unavailable');self.assertTrue(c['diagnostics'])
        draft=m.draft_channel(dict(name='APRS',rx_mhz=144.39,power='Medium'))
        compared=m.compare_channels(c,draft)
        self.assertTrue(all(r['state'] in ('unknown','not_represented') for r in compared['fields']))


if __name__=='__main__':unittest.main()
