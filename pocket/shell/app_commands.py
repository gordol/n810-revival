# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Named application commands. Keys are presentation; canonical events stay internal.

The native wrapper resolves user bindings only after local editors/search and
shared navigation have handled their input. Pointer and focused Enter activation
use canonical events directly, so remapping or unbinding cannot disable buttons.
"""
from collections import namedtuple

Command = namedtuple('Command', 'event title keys')
CONNECTIONS = {
    'open.system': Command('i', 'System', ('i',)),
    'open.feed': Command('f', 'Radio Feed', ('f',)),
    'open.reticulum': Command('r', 'Reticulum', ('r',)),
    'open.messages': Command('m', 'Messages', ('m',)),
    'owner.device': Command('v', 'Device', ('v',)),
    'owner.reticulum': Command('o', 'Reticulum', ('o',)),
    'owner.meshcore': Command('b', 'MeshCore', ('b',)),
    'owner.next': Command('t', 'Next owner', ('t',)),
    'attach.local': Command('l', 'This device', ('l',)),
    'attach.remote': Command('c', 'Connect SSH / verified peer', ('c',)),
    'attach.peer': Command('p', 'Connect peer / direct peer setup', ('p',)),
    'attach.socket': Command('s', 'Socket folder', ('s',)),
    'detach': Command('d', 'Disconnect', ('d',)),
    'address.edit': Command('e', 'Address', ('e',)),
    'open.rnode': Command('h', 'RNode connections', ('h',)),
}
SCOPES = {'connections': CONNECTIONS}


def label(scope, event):
    """Display a command's actual binding; an unbound action remains clickable."""
    from keybindings import current
    action = next(name for name, command in SCOPES[scope].items() if command.event == event)
    value = current().label(scope, action)
    return value.upper() if len(value) == 1 else value


def button(scope, event, title):
    key = label(scope, event)
    return '[' + (key + ' ' if key != 'unbound' else '') + title + ']'
