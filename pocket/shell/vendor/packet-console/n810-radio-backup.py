#!/usr/bin/env python3
"""Vendor-protocol configuration export. Run only with the feed disconnected."""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import signal
import socket
import struct
import subprocess
import time

READ_COMMANDS={1,4,10,13,20,22,29,33,36,39,55,63,72,73,75}


def decode(raw,layout):
    value=int.from_bytes(raw,'big');total=len(raw)*8;offset=0;result={}
    for name,width,kind in layout:
        if offset+width>total:break
        part=(value>>(total-offset-width))&((1<<width)-1);offset+=width
        if kind=='str':part=part.to_bytes(width//8,'big').split(b'\0',1)[0].decode('gbk',errors='replace')
        elif kind=='bool':part=bool(part)
        result[name]=part
    result['_decoded_bits']=offset;result['_available_bits']=total;return result


def frame(command,payload=b''):
    return b'\xff\x01\0'+bytes([len(payload)])+struct.pack('>HH',2,command)+payload


class Link:
    def __init__(self,radio):self.radio=radio;self.pending=bytearray();self.trace=[]
    def request(self,command,payload=b'',index=None,permit_select=False,restore=None):
        if command not in READ_COMMANDS:
            if not (command==60 and permit_select) and not (command==11 and restore is not None and payload==restore):
                raise ValueError('Write operation rejected')
        for attempt in range(2):
            self.radio.sendall(frame(command,payload));end=time.monotonic()+3
            while time.monotonic()<end:
                try:chunk=self.radio.recv(8192)
                except socket.timeout:continue
                if not chunk:raise ConnectionError('Radio disconnected')
                self.pending.extend(chunk)
                while len(self.pending)>=8:
                    if self.pending[:2]!=b'\xff\x01':del self.pending[0];continue
                    size=8+self.pending[3]+(self.pending[2]&1)
                    if len(self.pending)<size:break
                    raw=bytes(self.pending[:size]);del self.pending[:size]
                    group,word=struct.unpack('>HH',raw[4:8]);body=raw[8:8+raw[3]]
                    self.trace.append(dict(time=datetime.datetime.now(datetime.timezone.utc).isoformat(),frame=raw.hex()))
                    if group==2 and word==(command|0x8000):
                        if index is not None and body[:1]==b'\0' and (len(body)<2 or body[1]!=index):continue
                        return dict(command=command,request_hex=payload.hex(),reply_hex=body.hex(),status=body[0] if body else None)
        return dict(command=command,request_hex=payload.hex(),reply_hex=None,status=None,error='timeout')


def main():
    def stop(*_):raise KeyboardInterrupt('Backup interrupted')
    signal.signal(signal.SIGTERM,stop)
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--address',default='02:00:00:00:00:13')
    p.add_argument('--output',type=Path,required=True);p.add_argument('--all-banks',action='store_true');args=p.parse_args()
    layouts=json.loads(Path(__file__).with_name('radio-read-layouts.json').read_text())
    output=args.output;output.mkdir(parents=True,exist_ok=False);os.chmod(output,0o700)
    capture=dict(version=1,address=args.address,started=datetime.datetime.now(datetime.timezone.utc).isoformat(),reads={},banks=[],complete=False)
    def save():
        temp=output/'backup.tmp';temp.write_text(json.dumps(capture,indent=2)+'\n');os.chmod(temp,0o600);temp.replace(output/'backup.json')
    save()
    sdp=subprocess.check_output(['sdptool','search','--bdaddr',args.address,'SP'],timeout=25,text=True)
    match=re.search(r'Channel: (\d+)',sdp)
    if not match:raise RuntimeError('Serial service not found')
    capture['sdp']=sdp;capture['rfcomm_channel']=int(match[1])
    radio=socket.socket(socket.AF_BLUETOOTH,socket.SOCK_STREAM,socket.BTPROTO_RFCOMM);radio.settimeout(.5)
    original_bank=None;original_settings=None;switched=False
    def read(command,payload=b'',index=None):
        response=link.request(command,payload,index)
        return response
    def parsed(response,name):
        if response['status']!=0:raise RuntimeError('Read failed: '+str(response))
        return decode(bytes.fromhex(response['reply_hex'])[1:],layouts[name])
    try:
        radio.connect((args.address,int(match[1])));link=Link(radio)
        info=read(4,b'\3');capture['reads']['device_info']=info
        device=parsed(info,'DevInfo');capture['device']=device
        settings=read(10);capture['reads']['settings']=settings
        capture['settings']=parsed(settings,'Settings');original_settings=bytes.fromhex(settings['reply_hex'])[1:]
        status=read(20);capture['reads']['status']=status
        decoded_status=parsed(status,'StatusExt' if len(bytes.fromhex(status['reply_hex']))>=5 else 'Status')
        capture['status']=decoded_status;original_bank=decoded_status.get('curr_region')
        print('Device:',json.dumps(device),flush=True);print('Initial status:',json.dumps(decoded_status),flush=True)
        for label,command,payload in [('beacon',33,b'\2'),('advanced',29,b''),('advanced2',63,b''),('buttons',55,b''),('button_actions',75,b''),('aprs_path',72,b''),('volume',22,b''),('vfo',36,b'')]:
            response=read(command,payload);capture['reads'][label]=response
            if label=='beacon' and response['status']==0:
                raw=bytes.fromhex(response['reply_hex'])[1:]
                capture['beacon']=decode(raw,layouts['BSSSettingsV2'] if len(raw)>=52 else layouts['BSSSettings'])
            save()
        for index in range(min(device.get('freq_range_count',0),16)):
            capture['reads']['frequency_range_'+str(index)]=read(39,bytes([index]));save()
        names=[]
        for index in range(min(device.get('region_count',0),32)):
            response=read(73,bytes([index]),index);capture['reads']['bank_name_'+str(index)]=response
            raw=bytes.fromhex(response['reply_hex'] or '')
            names.append(raw[2:].split(b'\0',1)[0].decode('gbk',errors='replace') if response['status']==0 else '')
        capture['bank_names']=names;save()
        count=device.get('channel_count',0)
        if not 0<count<=255:raise RuntimeError('Invalid channel count')
        def get_bank(index):
            bank=dict(index=index,name=names[index] if index is not None and index<len(names) else '',channels=[])
            capture['banks'].append(bank)
            for channel in range(count):
                response=read(13,bytes([channel]),channel)
                entry=dict(index=channel,response=response)
                if response['status']==0:
                    raw=bytes.fromhex(response['reply_hex'])[1:];entry['decoded']=decode(raw,layouts['RfChDMR'] if len(raw)>=27 else layouts['RfCh'])
                bank['channels'].append(entry)
                if channel%10==9:print('Bank',index,'read',channel+1,'/',count,flush=True)
                save()
            bank['complete']=all(row['response']['status']==0 for row in bank['channels']);save()
        get_bank(original_bank)
        if args.all_banks:
            if original_bank is None:raise RuntimeError('Current bank unknown; refusing bank switch')
            if capture.get('beacon',{}).get('should_share_location') is not False:
                raise RuntimeError('Automatic beaconing enabled or unknown; current-bank backup saved, no bank switches made')
            for index in range(len(names)):
                if index==original_bank:continue
                switched=True
                response=link.request(60,bytes([index]),permit_select=True)
                if response['status']!=0:raise RuntimeError('Bank selection failed: '+str(response))
                time.sleep(.2)
                check=parsed(read(20),'StatusExt')
                if check.get('curr_region')!=index:raise RuntimeError('Bank selection readback mismatch')
                get_bank(index)
        capture['complete']=all(bank['complete'] for bank in capture['banks']) and (not args.all_banks or len(capture['banks'])==len(names))
    except BaseException as exc:
        capture['error']=str(exc);raise
    finally:
        try:
            if switched and original_bank is not None:
                restored=link.request(60,bytes([original_bank]),permit_select=True);capture['restore_bank']=restored
                current=read(10)
                if current['status']==0 and bytes.fromhex(current['reply_hex'])[1:]!=original_settings:
                    capture['restore_settings']=link.request(11,original_settings,restore=original_settings)
                capture['final_settings']=read(10);capture['final_status']=read(20)
                final_bank=parsed(capture['final_status'],'StatusExt').get('curr_region')
                capture['restored']=final_bank==original_bank and capture['final_settings']['reply_hex']==settings['reply_hex']
                print('Original bank/settings restored:',capture['restored'],flush=True)
            if 'link' in locals():capture['protocol_trace']=link.trace
        finally:
            radio.close();capture['finished']=datetime.datetime.now(datetime.timezone.utc).isoformat();save()
            print('Saved',output/'backup.json',flush=True)
    if switched and not capture.get('restored'):raise RuntimeError('Restore verification failed')
    if not capture['complete']:raise RuntimeError('Backup incomplete; inspect saved responses')

if __name__=='__main__':main()
