# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Named common actions with validated user overrides; no I/O during key routing."""
import json
import os
from pathlib import Path
import tempfile
from app_commands import SCOPES as APP_COMMANDS

# Action ID -> (canonical event, opinionated default key names).
NAVIGATION = {
    'focus.next': ('\t', ['tab']), 'focus.previous': ('backtab', ['shift-tab']),
    'select.up': ('up', ['up']), 'select.down': ('down', ['down']),
    'select.left': ('left', ['left']), 'select.right': ('right', ['right']),
    'activate': ('\r', ['enter', 'ctrl-j']), 'back': ('\x1b', ['escape']),
    'tab.previous': ('[', ['[']), 'tab.next': (']', [']']),
    'page.previous': ('pageup', ['pageup']), 'page.next': ('pagedown', ['pagedown']),
    'select.first': ('home', ['home']), 'select.last': ('end', ['end']),
}
SCOPES = {
    'navigation': NAVIGATION,
    'global': {
        'windows.commands': ('window-commands', ['ctrl-]']),
        'windows.select': ('window-select', []),
        'desktop.menu': ('wm-menu', ['f13','alt-m']),
        'windows.switch': ('wm-next', ['f14','alt-tab']),
        'windows.maximize': ('wm-maximize', ['f15','alt-enter']),
        'desktop.overview': ('wm-windows', ['alt-o']),
        'view.zoom_in': ('+', ['f16']),
        'view.zoom_out': ('-', ['f17']),
        'windows.next': ('f6', ['f6']), 'windows.previous': ('shift-f6', ['shift-f6']),
    },
    'windows': {name: NAVIGATION[name] for name in (
        'focus.next', 'focus.previous', 'select.up', 'select.down',
        'select.left', 'select.right', 'activate', 'back')},
}
SCOPES.update({scope: {name: (command.event, list(command.keys))
                       for name, command in commands.items()}
               for scope, commands in APP_COMMANDS.items()})
ALIASES = {'tab': '\t', 'shift-tab': 'backtab', 'enter': '\r', 'escape': '\x1b',
           'space': ' ', 'backspace': 'backspace'}
FUNCTIONS = frozenset(('up','down','left','right','home','end','pageup','pagedown',
                       'alt-m','alt-tab','alt-enter','alt-o','f5','f6','f13','f14','f15','f16','f17','shift-f6','context-menu','help'))
UNBOUND = 'unbound-shortcut'


def key_event(name):
    if not isinstance(name, str) or not name or len(name) > 32:
        raise ValueError('A key must be a character or a name such as ctrl-n')
    if len(name) == 1 and name.isprintable():
        return name
    name = name.lower()
    if name in ALIASES:
        return ALIASES[name]
    if name in FUNCTIONS:
        return name
    if name.startswith('ctrl-') and len(name) == 6 and '@' <= name[-1].upper() <= '_':
        return chr(ord(name[-1].upper()) & 31)
    raise ValueError('Unsupported key: '+name)


def default_path():
    return Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'current-world/keys.json'


DEFAULT_EVENTS = {scope:frozenset(key_event(name) for _, names in actions.values() for name in names)
                  for scope, actions in SCOPES.items()}


def compile_bindings(document):
    if not isinstance(document, dict) or set(document)-{'version','bindings','double_escape'}:
        raise ValueError('Unknown shortcut configuration fields')
    if type(document.get('version')) is not int or document['version'] != 1:
        raise ValueError('Expected shortcut config version 1')
    if type(document.get('double_escape', False)) is not bool:
        raise ValueError('double_escape must be true or false')
    overrides = document.get('bindings', {})
    if not isinstance(overrides, dict) or set(overrides)-set(SCOPES):
        raise ValueError('Unknown shortcut scope')
    compiled = {}
    for scope, actions in SCOPES.items():
        custom = overrides.get(scope, {})
        if not isinstance(custom, dict) or set(custom)-set(actions):
            raise ValueError('Unknown action in '+scope)
        lookup = {}
        for action, (canonical, defaults) in actions.items():
            names = custom.get(action, defaults)
            if not isinstance(names, list) or len(names) > 8:
                raise ValueError(scope+'.'+action+' expects up to eight key names')
            for name in names:
                event = key_event(name)
                if event in lookup:
                    raise ValueError('Conflicting '+scope+' key: '+name)
                lookup[event] = canonical
        compiled[scope] = lookup
    conflict = set(compiled['global']) & set(compiled['navigation'])
    if conflict:
        raise ValueError('Global and navigation shortcuts conflict; unbind one action first')
    reserved = (set(compiled['global']) | set(compiled['navigation']) |
                DEFAULT_EVENTS['global'] | DEFAULT_EVENTS['navigation'])
    for scope, actions in APP_COMMANDS.items():
        custom = overrides.get(scope, {})
        for action, command in actions.items():
            for name in custom.get(action, command.keys):
                event = key_event(name)
                if event not in reserved:
                    continue
                if action in custom:
                    raise ValueError('Application shortcuts conflict with global/navigation keys in '+scope)
                # Existing navigation overrides predate app scopes. Preserve them
                # and hide shadowed default app hints rather than rejecting them.
                compiled[scope].pop(event, None)
    return compiled


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate shortcut field: '+key)
        result[key] = value
    return result


class Bindings:
    """One cached config publication, changed only by explicit reload/save."""
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else default_path()
        self.document = {'version': 1}
        self.compiled = compile_bindings(self.document)
        self.error = ''
        self.reload()

    def reload(self):
        try:
            if self.path.exists():
                with self.path.open('rb') as source:
                    raw = source.read(65537)
                if len(raw) > 65536:
                    raise ValueError('Shortcut config exceeds 64 KiB')
                document = json.loads(raw, object_pairs_hook=unique_object)
            else:
                document = {'version': 1}
            compiled = compile_bindings(document)
        except (OSError, ValueError, TypeError) as error:
            self.error = str(error)
            return False
        self.document, self.compiled, self.error = document, compiled, ''
        return True

    @property
    def double_escape(self):
        return self.document.get('double_escape', False)

    def set_double_escape(self, enabled):
        document = dict(self.document, double_escape=bool(enabled))
        compiled = compile_bindings(document)
        temporary = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, delete=False) as source:
                temporary = Path(source.name)
                json.dump(document, source, indent=2)
                source.write('\n')
            temporary.replace(self.path)
        except OSError as error:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self.error = str(error)
            return False
        self.document, self.compiled, self.error = document, compiled, ''
        return True

    def resolve(self, scope, key):
        lookup = self.compiled[scope]
        if key in lookup:
            return lookup[key]
        return UNBOUND if key in DEFAULT_EVENTS[scope] else key

    def global_key(self, key, legacy_prefix):
        custom = self.document.get('bindings', {}).get('global', {})
        if 'windows.commands' not in custom:
            if key == legacy_prefix:
                return 'window-commands'
            if key == '\x1d':
                return key  # Preserve a customized legacy prefix preference.
        return self.resolve('global', key)

    def label(self, scope, action):
        defaults = SCOPES[scope][action][1]
        keys = self.document.get('bindings', {}).get(scope, {}).get(action, defaults)
        if scope in APP_COMMANDS:
            canonical = SCOPES[scope][action][0]
            keys = [name for name in keys if self.compiled[scope].get(key_event(name)) == canonical]
        return keys[0] if keys else 'unbound'


_current = None

def current():
    global _current
    if _current is None:
        _current = Bindings()
    return _current
