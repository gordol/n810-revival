import importlib.util
import unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
spec=importlib.util.spec_from_file_location('preview',Path(__file__).with_name('n810-radio-preview.py'))
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)

class Window:
    def __init__(self,size=(39,133),keys=()):self.size=size;self.keys=iter(keys);self.text=[]
    def getmaxyx(self):return self.size
    def erase(self):self.text=[]
    def refresh(self):pass
    def keypad(self,value):pass
    def timeout(self,value):pass
    def getch(self):return next(self.keys)
    def addnstr(self,y,x,text,n,attr):
        assert 0<=y<self.size[0] and 0<=x<self.size[1] and n<=self.size[1]-x-1
        self.text.append(text[:n])

class Tests(unittest.TestCase):
    def test_snapshot_and_empty_memory(self):
        data={'started':'2026-10-15T14:00:00+00:00','banks':[{'index':0,'name':'Ham','channels':[{'index':0,'decoded':{'rx_freq':0}}]}]}
        for size in [(39,133),(24,80)]:
            win=Window(size);p.draw(win,data,0,0,0,None,0,'')
            self.assertIn('Empty memory',win.text)
            self.assertTrue(any('live radio status unavailable' in row for row in win.text))
    def test_browsing_keeps_radio_header(self):
        fields=dict(name_str='APRS',rx_freq=144390000,tx_freq=144390000,tx_at_max_power=True,tx_at_med_power=False,rx_sub_audio=0,tx_sub_audio=0,rx_mod=0,bandwidth=0,tx_disable=False,scan=False,mute=False,talk_around=False,pre_de_emph_bypass=True)
        data=dict(started='2026-10-15T14:00:00+00:00',status={'curr_region':0},banks=[dict(index=0,name='Ham',channels=[dict(index=0,decoded=fields),dict(index=1,decoded=dict(fields,name_str='CALL',rx_freq=146520000))])])
        win=Window();p.draw(win,data,0,1,1,None,0,'')
        self.assertTrue(any('A  00 APRS' in row for row in win.text))
        self.assertIn('Browsing only / does not tune',win.text)
        self.assertTrue(any('CALL' in row for row in win.text))
    def test_presets_return_to_preview(self):
        calls=[];win=Window(keys=[ord('2'),ord('q')])
        control=SimpleNamespace(STORE=Path('/unused'),run=lambda w,a:calls.append('presets'))
        with patch.object(p.curses,'curs_set'),patch.object(p.readback,'latest',return_value=(None,None)),patch.object(p,'module',return_value=control):p.run(win)
        self.assertEqual(calls,['presets'])
        self.assertIn('RADIO PREVIEW',win.text)

if __name__=='__main__':unittest.main()
