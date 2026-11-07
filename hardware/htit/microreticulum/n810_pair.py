"""Pair only the specified HTIT Classic Bluetooth device, then exit."""
import sys,getpass
import dbus,dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib
DBusGMainLoop(set_as_default=True)
pairing_pin=getpass.getpass('HTIT Bluetooth PIN: ').strip()
if not pairing_pin.isdigit() or not 4<=len(pairing_pin)<=16:raise SystemExit('PIN must contain 4 to 16 digits')
target=sys.argv[1].upper();device_path='/org/bluez/hci0/dev_'+target.replace(':','_')
bus=dbus.SystemBus();loop=GLib.MainLoop();state={'ok':False,'started':False,'ticks':0}
class Agent(dbus.service.Object):
    @dbus.service.method('org.bluez.Agent1',in_signature='',out_signature='')
    def Release(self):pass
    @dbus.service.method('org.bluez.Agent1',in_signature='o',out_signature='s')
    def RequestPinCode(self,device):
        if str(device)!=device_path:raise dbus.exceptions.DBusException('Unexpected device',name='org.bluez.Error.Rejected')
        print('Providing private legacy PIN to the requested HTIT only',flush=True)
        return pairing_pin
    @dbus.service.method('org.bluez.Agent1',in_signature='ou',out_signature='')
    def RequestConfirmation(self,device,passkey):
        if str(device)!=device_path:raise dbus.exceptions.DBusException('Unexpected device',name='org.bluez.Error.Rejected')
        print('Confirming SSP for the requested HTIT only',flush=True)
    @dbus.service.method('org.bluez.Agent1',in_signature='os',out_signature='')
    def AuthorizeService(self,device,uuid):
        if str(device)!=device_path:raise dbus.exceptions.DBusException('Unexpected device',name='org.bluez.Error.Rejected')
    @dbus.service.method('org.bluez.Agent1',in_signature='',out_signature='')
    def Cancel(self):pass
agent=Agent(bus,'/pocket_htit_test_agent');manager=dbus.Interface(bus.get_object('org.bluez','/org/bluez'),'org.bluez.AgentManager1')
manager.RegisterAgent('/pocket_htit_test_agent','DisplayYesNo')
print('Agent ready; waiting 15 seconds for the HTIT pairing window',flush=True)
adapter=dbus.Interface(bus.get_object('org.bluez','/org/bluez/hci0'),'org.bluez.Adapter1')
objects=dbus.Interface(bus.get_object('org.bluez','/'),'org.freedesktop.DBus.ObjectManager')
def success():
    state['ok']=True;print('Paired',target,flush=True);loop.quit()
def failure(error):
    if error.get_dbus_name()=='org.bluez.Error.AlreadyExists':success()
    else:print('Pair failed:',error,flush=True);loop.quit()
def tick():
    state['ticks']+=1
    if state['ticks']>55:print('Pairing timed out',flush=True);loop.quit();return False
    if state['ticks']<15 or state['started']:return True
    found=objects.GetManagedObjects()
    if device_path in found:
        state['started']=True
        if found[device_path].get('org.bluez.Device1',{}).get('Paired'):success();return False
        print('Pairing target HTIT',flush=True)
        dbus.Interface(bus.get_object('org.bluez',device_path),'org.bluez.Device1').Pair(reply_handler=success,error_handler=failure,timeout=45)
    return True
try:
    adapter.StartDiscovery();GLib.timeout_add_seconds(1,tick);loop.run()
finally:
    try:adapter.StopDiscovery()
    except dbus.DBusException:pass
    manager.UnregisterAgent('/pocket_htit_test_agent')
sys.exit(0 if state['ok'] else 1)
