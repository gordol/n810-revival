"""Explicit carrier profiles for the existing encrypted RNS service links."""
import ipaddress
import re

TYPES = {'tcp-client':'TCPClientInterface', 'tcp-server':'TCPServerInterface',
         'lan':'AutoInterface', 'serial':'SerialInterface', 'usb':'SerialInterface',
         'bluetooth':'SerialInterface', 'kiss':'KISSInterface', 'ax25':'AX25KISSInterface'}


def configuration(carriers, relay=False):
    if type(relay) is not bool or not isinstance(carriers,list) or not 1 <= len(carriers) <= 8:
        raise ValueError('Select one to eight carriers and an explicit boolean relay setting')
    sections=[]
    for index, spec in enumerate(carriers):
        if not isinstance(spec,dict) or spec.get('type') not in TYPES:
            raise ValueError('Unknown carrier type')
        kind=spec['type']; values={'type':TYPES[kind], 'enabled':'Yes'}; fields={'type'}
        def integer(key, low, high, default=None):
            fields.add(key); value=spec.get(key,default)
            if type(value) is not int or not low <= value <= high: raise ValueError('Invalid carrier '+key)
            return value
        def text(key, pattern):
            fields.add(key);value=spec.get(key)
            if not isinstance(value,str) or not re.fullmatch(pattern,value): raise ValueError('Invalid carrier '+key)
            return value
        if kind in ('tcp-client','tcp-server'):
            host=text('host',r'[A-Za-z0-9_.:%-]{1,253}')
            if kind=='tcp-server':
                try:ipaddress.ip_address(host)
                except ValueError:raise ValueError('Listener host must be an explicit IP address') from None
            prefix='target_' if kind=='tcp-client' else 'listen_'
            values[prefix+('host' if kind=='tcp-client' else 'ip')]=host
            values[prefix+'port']=integer('port',1,65535)
        elif kind=='lan':
            fields.add('devices'); devices=spec.get('devices')
            if not isinstance(devices,list) or not 1<=len(devices)<=8 or any(not isinstance(d,str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,64}',d) for d in devices):
                raise ValueError('Select explicit LAN interfaces')
            values['devices']=', '.join(devices)
        else:
            values['port']=text('port',r'/dev/[A-Za-z0-9_./-]{1,160}')
            if '..' in values['port'].split('/'):raise ValueError('Invalid device path')
            values.update(speed=integer('speed',300,4000000,115200),databits=8,parity='none',stopbits=1)
            if kind in ('kiss','ax25'):
                values.update(preamble=integer('preamble',0,2550,150),txtail=integer('txtail',0,2550,10),
                              persistence=integer('persistence',0,255,200),slottime=integer('slottime',0,2550,20),flow_control='False')
            if kind=='ax25':
                values.update(callsign=text('callsign',r'[A-Z0-9]{1,6}'),ssid=integer('ssid',0,15,0))
        if set(spec)-fields:raise ValueError('Unknown carrier options: '+', '.join(sorted(set(spec)-fields)))
        sections.append('  [[Carrier '+str(index+1)+']]\n'+''.join('    '+k+' = '+str(v)+'\n' for k,v in values.items()))
    return ('[reticulum]\nenable_transport = '+('Yes' if relay else 'No')+
            '\nshare_instance = No\ndiscover_interfaces = No\nautoconnect_discovered_interfaces = 0\n'
            'enable_remote_management = No\nenable_interface_management = No\nrespond_to_probes = No\n'
            '[logging]\nloglevel = 3\n[interfaces]\n'+''.join(sections))
