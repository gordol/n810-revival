#!/usr/bin/env python3
"""Offline Nets state, confirmation, receive-only feed and rendering checks."""
import importlib.util
import json
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('nets',Path(__file__).with_name('n810-nets.py'))
nets=importlib.util.module_from_spec(spec);spec.loader.exec_module(nets)

class Screen:
    def __init__(self,keys=(),size=(40,133)):self.keys=iter(keys);self.size=size
    def keypad(self,value):pass
    def timeout(self,value):pass
    def getmaxyx(self):return self.size
    def erase(self):pass
    def refresh(self):pass
    def addnstr(self,y,x,text,width,attr):
        assert 0<=y<self.size[0] and 0<=x<self.size[1]
        assert width>=0
    def getch(self):return next(self.keys)
    def get_wch(self):return next(self.keys)

class NetsTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.addCleanup(self.folder.cleanup)
        root=Path(self.folder.name)
        self.args=type('Args',(),dict(data=Path(__file__).with_name('data')/'nets-puget-sound.json',lead=0,socket=str(root/'absent.sock')))()
        self.state=root/'state.json'
        for target,value in [('STATE',self.state),('style.init_screen',lambda w:None),('style.accent',lambda:0),('style.selection',lambda:0),('notify',lambda *a:self.fail('Unexpected notice'))]:
            obj=nets;parts=target.split('.')
            for part in parts[:-1]:obj=getattr(obj,part)
            p=patch.object(obj,parts[-1],value);p.start();self.addCleanup(p.stop)
        self.packet=dict(id='sample',call='TEST',packet_time='12:00:00',kind='Net mention',text='Net Mon 19:30 146.820MHz',raw='original packet',time_basis='Unverified; packet may be replayed')
    def run_keys(self,*keys):
        nets.run(Screen([ord(k) for k in keys]),self.args)
        return json.loads(self.state.read_text())
    def test_legacy_setting_migrates_to_off(self):
        nets.cal.atomic(self.state,dict(version=1,lead=15,heard=[self.packet]))
        state=self.run_keys('q')
        self.assertEqual((state['version'],state['lead'],state['enabled']),(2,0,[]))
        self.assertEqual(state['heard'],[self.packet])
    def test_adjusting_lead_does_not_subscribe(self):
        state=self.run_keys('.','q')
        self.assertEqual(state['lead'],5);self.assertEqual(state['enabled'],[])
    def test_explicit_toggle_and_restart(self):
        state=self.run_keys('a','q')
        self.assertEqual(len(state['enabled']),1);self.assertEqual(state['lead'],15)
        self.assertEqual(self.run_keys('q')['enabled'],state['enabled'])
        self.assertEqual(self.run_keys('a','q')['enabled'],[])
    def test_unknown_radio_cannot_enable_reminder(self):
        nets.cal.atomic(self.state,dict(version=2,lead=0,heard=[self.packet]))
        self.assertEqual(self.run_keys('h','a','q')['enabled'],[])
    def test_confirm_retains_provenance_and_cancels(self):
        row=nets.confirm(Screen(list('\n19:30\nMon,Wed\n\n146.82\n')),self.packet)
        self.assertEqual(row['weekdays'],[0,2]);self.assertEqual(row['raw'],'original packet')
        self.assertEqual(row['timezone'],'America/Los_Angeles')
        self.assertNotIn('reminders',row)
        self.assertIsNone(nets.confirm(Screen(['\x1b']),self.packet))
    def test_confirmation_saved_without_enabling(self):
        nets.cal.atomic(self.state,dict(version=2,lead=0,heard=[self.packet]))
        row=nets.confirm(Screen(list('\n19:30\nMon\n\n146.82\n')),self.packet)
        with patch.object(nets,'confirm',return_value=row):state=self.run_keys('h','f','q')
        self.assertEqual(state['confirmed'],[row]);self.assertEqual(state['enabled'],[])
    def test_receive_stream_is_fragmented_and_receive_only(self):
        reader,writer=socket.socketpair();reader.setblocking(False)
        feed=nets.Feed('unused');feed.socket=reader
        try:
            writer.sendall(b'12:00:00 TEST>APRS ctl=03 pid=f0 >Net Mon')
            self.assertEqual(feed.poll(),[])
            writer.sendall(b' 19:30\nstatus only\n')
            self.assertEqual(len(feed.poll()),1)
            writer.setblocking(False)
            with self.assertRaises(BlockingIOError):writer.recv(1)
            writer.close();self.assertEqual(feed.poll(),[]);self.assertIsNone(feed.socket)
        finally:feed.close();writer.close()
    def test_window_navigation_uses_existing_helper_without_bluetooth(self):
        for name,script in [('Nets','n810-nets.py'),('Radio Services','n810-repeaters.py')]:
            with patch.dict(nets.os.environ,{'TMUX_PANE':'%1'}), \
                 patch.object(nets.windows.subprocess,'check_output',side_effect=['pocket','']), \
                 patch.object(nets.windows.subprocess,'run') as run:
                nets.windows.open_window(name)
                self.assertEqual(run.call_args.args[0][-2:],['python3','/home/nokia/'+script])

    def test_render_schedules_announcements_and_empty(self):
        rows=nets.cal.upcoming(nets.cal.load(self.args.data))
        for size in [(40,133),(24,80),(18,65)]:
            for data in [rows,[self.packet],[],rows+[self.packet]]:
                for selected in (0,max(0,len(data)-1)):
                    nets.draw(Screen(size=size),data,selected,False,0,False,'','Offline')

if __name__=='__main__':unittest.main()
