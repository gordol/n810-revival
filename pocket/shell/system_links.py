"""Project observed interfaces and selected service transports; never probe radios."""
import time
from urllib.parse import urlsplit


def project(data, meshcore=None, now=None):
    now=time.time() if now is None else now
    stamp=(data.get('system') or {}).get('observed_at')
    supplied=data.get('connectivity') or {}
    base=supplied if isinstance(supplied,dict) and supplied.get('version')==1 else {}
    rows={row['id']:dict(row) for row in base.get('links',()) if isinstance(row,dict) and isinstance(row.get('id'),str)}
    for identity,name,label in (('wifi-sta','wlan0','Wi-Fi STA'),('usb-ip','usb0','USB networking')):
        state=(data.get('network') or {}).get(name)
        wifi=(data.get('wifi') or {}).get(name,{})
        connected=True if wifi.get('state')=='connected' or state=='up' else False if wifi.get('state')=='disconnected' or state=='down' else None
        row=rows.setdefault(identity,dict(id=identity,label=label))
        if connected is not None:row.update(connected=connected,observed_at=stamp)
    meshcore=meshcore or {}
    port=meshcore.get('port','')
    if isinstance(port,str) and port.startswith('htit://'):
        uri=urlsplit(port);parts=uri.path.strip('/').split('/')
        phase=meshcore.get('connection_state','unknown')
        bridge=meshcore.get('bridge') or {}
        observed=bridge.get('observed_at')
        age=max(0.,now-observed) if type(observed) in (int,float) else None
        fresh=bool(meshcore.get('owner_online') and bridge.get('kind')=='htit' and bridge.get('phase')=='online' and age is not None and age<=15)
        detail='status unavailable' if age is None else ('status '+str(int(age))+'s old'+(' (stale)' if not fresh else ''))
        if fresh:
            detail+=' · MTU '+str(bridge.get('mtu') or '?')+' · owner '+str(bridge.get('owner') if bridge.get('owner') is not None else '?')
        for identity,label,peer,key in (('htit-classic','HTIT Bluetooth',uri.netloc,'classic_connected'),('htit-ble','MeshCore BLE',parts[1] if len(parts)>1 else '','ble_connected')):
            connected=bridge.get(key) if fresh and type(bridge.get(key)) is bool else None
            if meshcore.get('owner_online') and bridge.get('phase')=='stopped' and key=='classic_connected':connected=False
            extra=detail
            if key=='ble_connected':extra+=' · companion '+phase
            if fresh and key=='ble_connected':extra+=' · BLE '+('ready' if bridge.get('ble_ready') else 'not ready')
            rows[identity]=dict(id=identity,label=label,configured=True,connected=connected,peer=peer,detail=extra,observed_at=observed)
    return dict(base,version=1,links=list(rows.values()))
