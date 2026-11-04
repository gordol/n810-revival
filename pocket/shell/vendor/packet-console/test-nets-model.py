"""Nets shared-model state and agenda contracts without UI or transport."""
import collections
import datetime as dt
import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('model',HERE/'n810-nets-model.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
NOW=dt.datetime(2026,10,15,12,tzinfo=m.cal.UTC)

class NetsModelTests(unittest.TestCase):
    def test_terminal_free_import(self):
        subprocess.run([sys.executable,'-c',"import runpy,sys;runpy.run_path(sys.argv[1]);assert not any(k in sys.modules for k in ('curses','socket','subprocess'))",str(HERE/'n810-nets-model.py')],check=True)
    def test_restore_and_state_format_remain_opt_in(self):
        state=m.restore({'version':1,'lead':15,'enabled':['net']})
        self.assertEqual(state[0:2],(0,set()))
        lead,enabled,confirmed,sent,heard=m.restore({'version':2,'lead':30,'enabled':['net']})
        encoded=m.state_payload(lead,enabled,confirmed,sent,heard)
        self.assertEqual(encoded,dict(version=2,lead=30,enabled=['net'],confirmed=[],sent=[],heard=[]))
    def test_observations_and_serialized_history_are_bounded(self):
        observed=collections.OrderedDict()
        for i in range(220):m.observe(observed,dict(id=str(i)))
        self.assertEqual(len(observed),200);self.assertNotIn('0',observed)
        payload=m.state_payload(0,set(),[],range(600),observed)
        self.assertEqual(len(payload['sent']),500);self.assertEqual(len(payload['heard']),200)
    def test_confirmed_radio_schedule_stays_unsubscribed(self):
        row=dict(id='abc',call='TEST',raw='original',text='Net Mon')
        values=dict(name='Net',time='19:30',days='Mon,Wed',timezone='America/Los_Angeles',frequency='146.82')
        net=m.confirmed_schedule(row,values,NOW)
        self.assertEqual(net['raw'],'original');self.assertEqual(net['weekdays'],[0,2]);self.assertNotIn('reminders',net)
        observed=collections.OrderedDict(abc=row)
        scheduled,rows=m.agenda(dict(nets=[]),[net],observed,set(),NOW)
        self.assertTrue(scheduled);self.assertTrue(all(not r['reminders'] for r in scheduled));self.assertEqual(rows,scheduled)
        _,heard=m.agenda(dict(nets=[]),[net],observed,set(),NOW,heard=True)
        self.assertEqual(heard,[row])
    def test_today_keeps_unknown_time_announcements(self):
        row=dict(id='a',call='TEST',text='Net soon')
        _,rows=m.agenda(dict(nets=[]),[],collections.OrderedDict(a=row),set(),NOW,today=True)
        self.assertEqual(rows,[row])

if __name__=='__main__':unittest.main()
