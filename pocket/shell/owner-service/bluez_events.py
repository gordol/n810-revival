"""BlueZ system-bus events bridged into the feed owner's selector."""
import collections
import socket
import threading


class BlueZ:
    def __init__(self):
        self.reader, self.writer = socket.socketpair()
        self.reader.setblocking(False)
        self.writer.setblocking(False)
        self.messages = collections.deque()
        self.lock = threading.Lock()
        self.context = self.loop = self.bus = None
        self.closed = False
        self.thread = threading.Thread(target=self.run, name='bluez-events', daemon=True)
        self.thread.start()

    def emit(self, value):
        with self.lock:
            if self.closed:
                return
            if value['kind']=='controller':
                self.messages=collections.deque(m for m in self.messages if m['kind']!='controller')
            self.messages.append(value)
            try:
                self.writer.send(b'!')
            except BlockingIOError:
                pass

    def drain(self):
        with self.lock:
            try:
                while self.reader.recv(4096):
                    pass
            except BlockingIOError:
                pass
            result = list(self.messages)
            self.messages.clear()
            return result

    def run(self):
        try:
            import dbus
            from dbus.mainloop.glib import DBusGMainLoop
            from gi.repository import GLib
            self.GLib = GLib
            self.context = GLib.MainContext.default()
            self.loop = GLib.MainLoop(context=self.context)
            self.bus = dbus.SystemBus(private=True, mainloop=DBusGMainLoop())
            self.objects = {}
            self.adapter = None

            def publish():
                adapters = [p for p, v in self.objects.items() if 'org.bluez.Adapter1' in v]
                self.adapter = adapters[0] if len(adapters) == 1 else None
                props = self.objects.get(self.adapter, {}).get('org.bluez.Adapter1', {})
                devices = []
                for path, interfaces in self.objects.items():
                    item = interfaces.get('org.bluez.Device1')
                    if item and item.get('Adapter') == self.adapter and item.get('Connected'):
                        devices.append({'path': str(path), 'address': str(item.get('Address', '')),
                                        'name': ''.join(c for c in str(item.get('Alias', item.get('Name', ''))) if c.isprintable())[:96],
                                        'connected': True})
                self.emit({'kind': 'controller', 'state': {
                    'available': self.adapter is not None,
                    'powered': bool(props['Powered']) if 'Powered' in props else None,
                    'devices': sorted(devices, key=lambda x: x['address'])[:32],
                    'error': None if self.adapter else 'expected exactly one BlueZ adapter'}})

            def failed(error):
                self.objects = {}
                self.adapter = None
                self.emit({'kind': 'controller', 'state': {'available': False, 'powered': None,
                           'devices': [], 'error': str(error)}})

            def loaded(objects):
                self.objects = objects
                publish()

            def refresh():
                proxy = self.bus.get_object('org.bluez', '/', introspect=False)
                proxy.GetManagedObjects(dbus_interface='org.freedesktop.DBus.ObjectManager',
                                        reply_handler=loaded, error_handler=failed, timeout=5)

            def properties(interface, changed, invalidated, path=None):
                if interface not in ('org.bluez.Adapter1', 'org.bluez.Device1'):
                    return
                current = self.objects.setdefault(path, {}).setdefault(interface, {})
                current.update(changed)
                for name in invalidated:
                    current.pop(name, None)
                publish()

            def added(path, interfaces):
                self.objects.setdefault(path, {}).update(interfaces)
                publish()

            def removed(path, interfaces):
                current = self.objects.get(path, {})
                for interface in interfaces:
                    current.pop(interface, None)
                if not current:
                    self.objects.pop(path, None)
                publish()

            def owner(name, previous, current):
                if name == 'org.bluez':
                    if current:
                        refresh()
                    else:
                        failed('BlueZ service unavailable')

            self.bus.add_signal_receiver(properties, signal_name='PropertiesChanged',
                dbus_interface='org.freedesktop.DBus.Properties', bus_name='org.bluez', path_keyword='path')
            self.bus.add_signal_receiver(added, signal_name='InterfacesAdded',
                dbus_interface='org.freedesktop.DBus.ObjectManager', bus_name='org.bluez')
            self.bus.add_signal_receiver(removed, signal_name='InterfacesRemoved',
                dbus_interface='org.freedesktop.DBus.ObjectManager', bus_name='org.bluez')
            self.bus.add_signal_receiver(owner, signal_name='NameOwnerChanged',
                dbus_interface='org.freedesktop.DBus', bus_name='org.freedesktop.DBus', arg0='org.bluez')
            refresh()
            if not self.closed:
                self.loop.run()
        except Exception as error:
            self.emit({'kind': 'controller', 'state': {'available': False, 'powered': None,
                       'devices': [], 'error': str(error)}})
        finally:
            if self.bus is not None:
                self.bus.close()

    def set_power(self, enabled, token):
        if self.context is None or self.loop is None or not self.thread.is_alive():
            self.emit({'kind': 'reply', 'token': token, 'ok': False, 'error': 'BlueZ events unavailable'})
            return

        def apply(*_):
            try:
                import dbus
                if self.adapter is None:
                    raise ValueError('BlueZ adapter unavailable')
                proxy = self.bus.get_object('org.bluez', self.adapter, introspect=False)
                proxy.Set('org.bluez.Adapter1', 'Powered', dbus.Boolean(enabled, variant_level=1),
                          dbus_interface='org.freedesktop.DBus.Properties', timeout=5,
                          reply_handler=lambda: self.emit({'kind': 'reply', 'token': token, 'ok': True}),
                          error_handler=lambda e: self.emit({'kind': 'reply', 'token': token, 'ok': False,
                                                            'error': str(e)}))
            except Exception as error:
                self.emit({'kind': 'reply', 'token': token, 'ok': False, 'error': str(error)})
            return False
        self.GLib.idle_add(apply)

    def close(self):
        self.closed = True
        if self.loop is not None:
            self.GLib.idle_add(self.loop.quit)
        self.thread.join(timeout=1)
        with self.lock:
            self.reader.close()
            self.writer.close()
