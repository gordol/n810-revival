#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Collect private build-time setup in a mode-0600 file; never print credentials."""
import argparse
import getpass
import json
import os
from pathlib import Path
from setup_profile import validate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    profile={};ssid=input('Wi-Fi network name (blank to configure later): ')
    if ssid:profile['wifi']={'ssid':ssid,'passphrase':getpass.getpass('Wi-Fi password: '),'country':input('Country code [US]: ').strip().upper() or 'US'}
    labels={'receive':'UV-PRO APRS reception','meshcore':'MeshCore','reticulum':'Reticulum'}
    profile['startup']={name:input('Start '+label+' at boot? [y/N]: ').strip().lower()=='y' for name,label in labels.items()}
    password=getpass.getpass('Set nokia login/sudo password: ')
    if not password or '\n' in password or password!=getpass.getpass('Repeat nokia password: '):raise ValueError('Nonempty matching passwords required')
    profile=validate(profile)
    a.output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(password+'\n'+json.dumps(profile)+'\n')
    print('Private setup saved to '+str(a.output)+'. Delete it after the image build consumes it.')

if __name__=='__main__':main()
