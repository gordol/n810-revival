#!/usr/bin/env python3
"""Pair one explicitly selected Classic hub with BlueZ. PIN is never logged."""
import argparse
import getpass
import re
import sys
import dbus
import dbus.service
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('address')
    parser.add_argument('--pin-stdin', action='store_true', help='read PIN from a private pipe instead of terminal')
    args = parser.parse_args()
    if not re.fullmatch(r'(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}', args.address):
        parser.error('expected a Bluetooth MAC address')
    pin = sys.stdin.readline().strip() if args.pin_stdin else getpass.getpass('Hub Classic pairing PIN: ')
    if not 4 <= len(pin) <= 16 or not pin.isascii() or not pin.isdecimal():
        parser.error('PIN must be 4–16 ASCII digits')
    DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()
    manager = dbus.Interface(bus.get_object('org.bluez', '/'), 'org.freedesktop.DBus.ObjectManager')
    adapters = [p for p, v in manager.GetManagedObjects().items() if 'org.bluez.Adapter1' in v]
    if len(adapters) != 1:
        raise RuntimeError('expected exactly one Bluetooth adapter')
    target = str(adapters[0]) + '/dev_' + args.address.upper().replace(':', '_')
    agent_path = '/org/pocket/htit_agent'
    loop = GLib.MainLoop()
    outcome = []

    class Rejected(dbus.DBusException):
        _dbus_error_name = 'org.bluez.Error.Rejected'

    class Agent(dbus.service.Object):
        def check(self, device):
            if str(device) != target:
                raise Rejected('unselected device')

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='s')
        def RequestPinCode(self, device):
            self.check(device)
            return pin

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='u')
        def RequestPasskey(self, device):
            self.check(device)
            if len(pin) != 6:
                raise Rejected('unexpected SSP passkey request')
            return dbus.UInt32(int(pin))

        @dbus.service.method('org.bluez.Agent1', in_signature='ou', out_signature='')
        def RequestConfirmation(self, device, passkey):
            raise Rejected('numeric confirmation is not enabled')

        @dbus.service.method('org.bluez.Agent1', in_signature='o', out_signature='')
        def RequestAuthorization(self, device):
            self.check(device)

        @dbus.service.method('org.bluez.Agent1', in_signature='os', out_signature='')
        def AuthorizeService(self, device, uuid):
            self.check(device)
            if str(uuid) != '00001101-0000-1000-8000-00805f9b34fb':
                raise Rejected('not the serial service')

        @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
        def Cancel(self):
            pass

        @dbus.service.method('org.bluez.Agent1', in_signature='', out_signature='')
        def Release(self):
            pass

    agent = Agent(bus, agent_path)
    am = dbus.Interface(bus.get_object('org.bluez', '/org/bluez'), 'org.bluez.AgentManager1')
    adapter = dbus.Interface(bus.get_object('org.bluez', adapters[0]), 'org.bluez.Adapter1')
    am.RegisterAgent(agent_path, 'KeyboardOnly')
    started_scan = False
    pairing = False

    def done(error=None):
        outcome.append(error)
        loop.quit()

    def poll():
        nonlocal pairing
        objects = manager.GetManagedObjects()
        device = objects.get(target, {}).get('org.bluez.Device1')
        if device is not None and not pairing:
            if device.get('Paired'):
                done()
            else:
                pairing = True
                dbus.Interface(bus.get_object('org.bluez', target), 'org.bluez.Device1').Pair(
                    reply_handler=lambda: done(), error_handler=done, timeout=25)
        return not outcome

    try:
        objects = manager.GetManagedObjects()
        if not objects[adapters[0]]['org.bluez.Adapter1'].get('Discovering'):
            adapter.StartDiscovery()
            started_scan = True
        GLib.timeout_add(250, poll)
        GLib.timeout_add_seconds(30, lambda: (done(RuntimeError('pairing timed out')), False)[1])
        loop.run()
        if outcome and outcome[0] is not None:
            raise RuntimeError(str(outcome[0]))
        print('Paired with ' + args.address.upper())
    finally:
        if started_scan:
            adapter.StopDiscovery()
        am.UnregisterAgent(agent_path)
        agent.remove_from_connection()


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print('pairing: ' + str(exc), file=sys.stderr)
        sys.exit(1)
