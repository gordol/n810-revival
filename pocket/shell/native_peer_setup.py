# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compact direct peer form, shared by keyboard and touch."""
from app_widgets import Canvas
from peer_profile import create_profile

class PeerSetup:
    def __init__(self,selection,close):
        self.selection=selection;self.close=close;self.mode='listen';self.values=['0.0.0.0','4242','n810'];self.focus=0;self.error='';self.hits=[];self._spans=()
    def key(self,key):
        if key in ('\x1b','escape'):self.close();return True
        if key in ('\t','down'):self.focus=(self.focus+1)%5;return True
        if key in ('backtab','up'):self.focus=(self.focus-1)%5;return True
        if self.focus==0 and key in (' ','left','right','\r','\n'):
            self.mode='connect' if self.mode=='listen' else 'listen';self.values[0]='' if self.mode=='connect' else '0.0.0.0';return True
        if key in ('\r','\n'):
            if self.focus<4:self.focus+=1;return True
            try:
                folder=create_profile(self.selection.state_directory,self.mode,*self.values)
                if not self.selection.connect('local',str(folder)):raise ValueError('Wait for the current connection request')
                self.close(str(folder))
            except (ValueError,OSError) as error:self.error=str(error)
            return True
        if 1<=self.focus<=3:
            index=self.focus-1
            if key in ('\x7f','\b','backspace'):self.values[index]=self.values[index][:-1]
            elif len(key)==1 and key.isprintable() and len(self.values[index])<80:self.values[index]+=key
            return True
        return True
    def pointer(self,column,row,width=None,button=0,released=False):
        if button or released:return False
        for y,index in self.hits:
            if y==row:
                self.focus=index
                if index in (0,4):self.key('\r')
                return True
        if row==0 and column>=getattr(self,'back_x',0):self.close();return True
        return False
    def lines(self,width,height):
        c=Canvas(width,height);self.hits=[]
        c.put(0,0,'Direct peer setup');self.back_x=max(0,width-10);c.put(self.back_x,0,'[Esc Back]')
        c.put(0,2,'One device listens; the other connects to its IP.')
        labels=[('Mode: '+self.mode+'  [Space changes]',0),('IP: '+self.values[0],1),('Port: '+self.values[1],2),('Your device name: '+self.values[2],3),('[Use this link]',4)]
        for row,(label,index) in enumerate(labels,4):
            c.put(0,row,('> ' if self.focus==index else '  ')+label);c.role(0,row,width,'input' if self.focus==index else 'control');self.hits.append((row,index))
        c.put(0,10,self.error or 'Then open Reticulum and choose Connect.')
        c.put(0,12,'Next: Messages > Reticulum > Discovery.')
        c.put(0,13,'Save the peer; compare full fingerprints.')
        c.put(0,14,'Uses Wi-Fi or USB IP. No radio activation.')
        c.put(0,height-1,'Tab fields · Enter next/use · Esc back');c.role(0,height-1,width,'control')
        self._spans=tuple(c.spans);return c.lines()
