"""Read existing N810 snapshots and the RX replay socket. No writes or radio access."""
import json
from pathlib import Path
import _socket as socket
import sys

def system_snapshot(proc=Path('/proc'),net=Path('/sys/class/net'),run=None):
    """Bounded Linux counters and an existing-link Wi-Fi observation."""
    import math,os,time
    def text(path,limit=65536):
        try:
            with path.open() as stream:return stream.read(limit)
        except OSError:return ''
    def number(value):
        try:
            result=int(value)
            return result if result>=0 else None
        except (ValueError,TypeError):return None
    stamp=time.time()
    system=dict(source=socket.gethostname(),platform=sys.platform,observed_at=stamp,
                boot_id=text(proc/'sys/kernel/random/boot_id',128).strip() or None,
                uptime_seconds=None,cpu=None,load_average=None)
    try:
        uptime=float(text(proc/'uptime',256).split()[0])
        if math.isfinite(uptime) and uptime>=0:system['uptime_seconds']=uptime
    except (ValueError,IndexError):pass
    first=text(proc/'stat',4096).splitlines()
    if first and first[0].startswith('cpu '):
        ticks=[number(v) for v in first[0].split()[1:9]]
        if len(ticks)>=4 and all(v is not None for v in ticks):
            system['cpu']=dict(total_ticks=sum(ticks),idle_ticks=ticks[3]+(ticks[4] if len(ticks)>4 else 0))
    try:
        load=[float(v) for v in text(proc/'loadavg',256).split()[:3]]
        if len(load)==3 and all(math.isfinite(v) and v>=0 for v in load):system['load_average']=load
    except ValueError:pass
    memory={}
    for line in text(proc/'meminfo',16384).splitlines():
        parts=line.split()
        if len(parts)==3 and parts[2]=='kB':
            value=number(parts[1])
            if value is not None:memory[parts[0].rstrip(':')]=value*1024
    system['memory_bytes']={k:memory.get(v) for k,v in [('total','MemTotal'),('available','MemAvailable'),('free','MemFree'),('buffers','Buffers'),('cached','Cached')]}
    vm={}
    for line in text(proc/'vmstat').splitlines():
        parts=line.split()
        if len(parts)==2 and parts[0] in ('pswpin','pswpout'):vm[parts[0]]=number(parts[1])
    system['swap']=dict(total_bytes=memory.get('SwapTotal'),free_bytes=memory.get('SwapFree'),
                        in_pages=vm.get('pswpin'),out_pages=vm.get('pswpout'),page_size_bytes=os.sysconf('SC_PAGE_SIZE'))
    interfaces={}
    for name in ('usb0','wlan0'):
        if (net/name).exists():
            interfaces[name]={key:number(text(net/name/'statistics'/key,128).strip()) for key in ('rx_bytes','tx_bytes','rx_packets','tx_packets')}
    wifi={}
    if (net/'wlan0').exists():
        observation=dict(state='unavailable',signal_dbm=None,observed_at=None)
        # A negative proc signal is dBm; positive quality values are not.
        # Missing/unsupported stats retain the existing nl80211 query fallback.
        carrier_path=net/'wlan0/carrier'
        carrier=text(carrier_path,8).strip()
        if carrier=='0':
            observation.update(state='disconnected',observed_at=time.time())
        elif carrier=='1':
            for line in text(proc/'net/wireless',8192).splitlines():
                name,separator,values=line.partition(':')
                if not separator or name.strip()!='wlan0':continue
                try:signal=float(values.split()[2])
                except (ValueError,IndexError):break
                if math.isfinite(signal) and -127<=signal<0:
                    # Do not publish an old signal if carrier dropped mid-read.
                    carrier=text(carrier_path,8).strip()
                    if carrier=='1':observation.update(state='connected',signal_dbm=signal,observed_at=time.time())
                    elif carrier=='0':observation.update(state='disconnected',observed_at=time.time())
                break
        if observation['state']=='unavailable':
            import re,shutil,subprocess
            iw=shutil.which('iw') or next((p for p in ('/usr/sbin/iw','/sbin/iw') if Path(p).is_file()),None)
            if iw or run is not None:
                try:
                    result=(run or subprocess.run)([iw or 'iw','dev','wlan0','link'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=1,check=False,text=True)
                    if result.returncode==0:
                        output=result.stdout[:8192];observation['observed_at']=time.time()
                        observation['state']='connected' if output.lstrip().startswith('Connected to ') else 'disconnected' if 'Not connected.' in output else 'unknown'
                        match=re.search(r'^\s*signal:\s*(-?\d+(?:\.\d+)?)\s*dBm',output,re.M)
                        if match and observation['state']=='connected':observation['signal_dbm']=float(match[1])
                except (OSError,subprocess.TimeoutExpired):pass
        wifi['wlan0']=observation
    return dict(system=system,network_stats=interfaces,wifi=wifi)

def local_status(proc=Path('/proc'),net=Path('/sys/class/net'),power=Path('/sys/class/power_supply'),run=None):
    """Read local system/link/power status without sockets or radio control."""
    result=system_snapshot(proc,net,run)
    result['power']=[]
    for path in power.glob('*/uevent'):
        try:result['power'].append(dict(line.split('=',1) for line in path.read_text().splitlines() if '=' in line))
        except OSError:pass
    result['network']={}
    for name in ('usb0','wlan0'):
        try:result['network'][name]=(net/name/'operstate').read_text().strip()
        except OSError:pass
    result['bluetooth_controller']=bluetooth_controller()
    return result

def bluetooth_controller():
    """Observe BlueZ power independently of the optional UV-Pro feed."""
    import time
    try:
        import dbus
        bus=dbus.SystemBus()
        adapter=bus.get_object('org.bluez','/org/bluez/hci0',introspect=False)
        powered=dbus.Interface(adapter,'org.freedesktop.DBus.Properties').Get(
            'org.bluez.Adapter1','Powered',timeout=2)
        return dict(available=True,powered=bool(powered),observed_at=time.time())
    except Exception:
        return None

root=Path.home()/'.local/state'
errors=[]
def read(path,limit=2000000):
    try:
        path=Path(path)
        if path.stat().st_size>limit:raise ValueError('snapshot too large')
        return json.loads(path.read_text())
    except (OSError,ValueError) as exc:
        errors.append(path.name+': unavailable');return None

def host_status():
    """Use the platform collector without depending on any radio endpoint."""
    if sys.platform.startswith('linux'):return local_status()
    import os,time
    try:load=list(os.getloadavg())
    except (AttributeError,OSError):load=None
    return dict(system=dict(source=socket.gethostname(),platform=sys.platform,
        observed_at=time.time(),load_average=load))


def main():
    import datetime
    import socket
    errors.clear()
    kind=sys.argv[1] if len(sys.argv)>1 else 'live'
    result={'captured':datetime.datetime.now(datetime.timezone.utc).isoformat(),'errors':errors}
    if kind=='live':
        result.update(local_status())
        result['history_source']='feed RAM snapshot'
        try:
            with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
                s.settimeout(2);s.connect('/dev/shm/n810-aprs-replay.sock')
                with s.makefile('rb') as f:
                    header=json.loads(f.readline(4096))
                    if header.get('type')!='snapshot' or header.get('version')!=1:raise ValueError('bad snapshot')
                    result['records']=[json.loads(f.readline(150000)) for _ in range(min(200,int(header['records'])))]
        except (OSError,ValueError,KeyError):
            result['history_source']='saved snapshot; feed unavailable'
            result['records']=(read(root/'n810-aprs/raw-frames.json') or {}).get('records',[])[-200:]
        result['radio_live']=read('/dev/shm/n810-radio-live.json')
    elif kind=='catalog':
        import sqlite3
        result['outbox']=(read(root/'n810-aprs/messages.json') or {}).get('outbox',[])
        result['nets_state']=read(root/'n810-aprs/nets-state.json')
        result['repeaters']=read(Path.home()/'.local/share/n810-radio/repeaters.json')
        result['published_services']=read(Path.home()/'.local/share/n810-radio/data-services.json')
        result['radio_profiles']=read(root/'n810-radio/profiles.json')
        result['radio_banks']=read(root/'n810-radio/banks.json')
        result['radio_snapshot']=None
        for path in sorted((root/'n810-radio/backups').glob('*/backup.json'),reverse=True)[:10]:
            data=read(path)
            if data and data.get('complete') and ('restore_bank' not in data or data.get('restored')):
                result['radio_snapshot']=data;break
        result['stations']=[]
        try:
            db=sqlite3.connect((root/'n810-aprs/directory.sqlite3').as_uri()+'?mode=ro',uri=True,timeout=.2)
            db.row_factory=sqlite3.Row
            result['stations']=[dict(r) for r in db.execute('SELECT s.*,p.name,p.buddy,p.notes FROM stations s LEFT JOIN people p ON p.call=s.call ORDER BY s.last DESC LIMIT 500')]
            result['evidence']=[dict(r) for r in db.execute('SELECT * FROM evidence LIMIT 2000')]
            result['via']=[dict(r) for r in db.execute('SELECT * FROM via LIMIT 1000')];db.close()
        except sqlite3.Error:errors.append('heard directory unavailable')
        result['walks']=[]
        try:
            import importlib.util
            spec=importlib.util.spec_from_file_location('web_walk_history',Path.home()/'n810-walk-history.py')
            history=importlib.util.module_from_spec(spec);spec.loader.exec_module(history)
            for outing in history.load(root/'n810-aprs/walks','N0CALL'):
                rows=[dict(type='session',tag=outing['name'],time=outing['start'])]
                rows.extend(dict(type='position',position=p) for p in outing['track'])
                rows.extend(dict(type='submission',probe=p) for p in outing['probes'])
                result['walks'].append(dict(file=outing['name'],files=outing['files'],rows=rows,end=outing['end']))
        except (OSError,ValueError,KeyError,TypeError):errors.append('walk history unavailable')
    else:raise SystemExit('Unsupported read kind')
    print(json.dumps(result,separators=(',',':')))


if __name__=='__main__':main()
