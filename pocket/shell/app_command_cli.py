"""CLI adapter for explicitly declared app commands and owner-supplied contexts.

No app discovery imports, context grants, windows, services or worker clones are
created here. Hosts pass their registrations and existing execution context.
"""
import argparse
from functools import partial
import re
import sys

MAX_OUTPUT = 1024 * 1024


def text_value(argument, text):
    if argument.kind == 'int':
        if len(text) > 32 or not re.fullmatch(r'[+-]?[0-9]+', text):
            raise argparse.ArgumentTypeError('Expected decimal integer text')
        result = int(text)
        if argument.minimum is not None and result < argument.minimum or argument.maximum is not None and result > argument.maximum:
            raise argparse.ArgumentTypeError('Integer is outside the declared bounds')
        return result
    if not 1 <= len(text) <= 1024 or not text.isprintable():
        raise argparse.ArgumentTypeError('Expected 1–1024 printable characters')
    if argument.kind == 'call':
        text = text.upper()
        if not re.fullmatch(r'[A-Z0-9]{1,12}(?:-(?:[0-9]|1[0-5]))?', text):
            raise argparse.ArgumentTypeError('Invalid callsign or SSID')
    return text


def topic_note(command, lookup=None):
    topic = command.manual_topic
    if topic is None:
        return ''
    if lookup is None:
        try:
            from on_device_manual.content import lookup_topic
        except ImportError:
            return 'Related manual topic: ' + topic + ' (manual not installed)'
        lookup = lookup_topic
    try:
        page = lookup(topic)
    except (OSError, ValueError):
        return 'Manual lookup unavailable: ' + topic
    return ('Related manual topic: ' if page is not None else 'Manual topic unavailable: ') + topic


def command_rows(entries):
    return [dict(app=entry.id, command=command.name, description=command.help,
                 capability=command.capability, effect=command.effect,
                 manual_topic=command.manual_topic,
                 arguments=[dict(name=a.name, kind=a.kind, help=a.help,
                                 required=a.required, default=a.default,
                                 minimum=a.minimum, maximum=a.maximum)
                            for a in command.arguments])
            for entry in entries for command in getattr(entry, 'commands', ())]


def complete(entries, words):
    if not words:
        return [entry.id for entry in entries if getattr(entry, 'commands', ())]
    entry = next((entry for entry in entries if entry.id == words[0]), None)
    if entry is None:
        return []
    commands = getattr(entry, 'commands', ())
    if len(words) == 1:
        return [c.name for c in commands]
    return ['--' + a.name for c in commands if c.name == words[1] for a in c.arguments]


class StreamParser(argparse.ArgumentParser):
    """Route argparse help and diagnostics through the adapter's streams."""
    def __init__(self, *args, cli_stdout=None, cli_stderr=None, **kwargs):
        self.cli_stdout = cli_stdout
        self.cli_stderr = cli_stderr
        super().__init__(*args, **kwargs)

    def _print_message(self, message, file=None):
        if not message:
            return
        if file is sys.stderr:
            (sys.stderr if self.cli_stderr is None else self.cli_stderr).write(message)
        elif self.cli_stdout is None:
            sys.stdout.write(message)
        else:
            self.cli_stdout.write(message.encode('utf-8'))


def check_options(entry, command):
    seen = {'-h', '--help'}
    for argument in command.arguments:
        flags = {'--' + argument.name}
        if argument.kind == 'bool':
            flags.add('--no-' + argument.name)
        conflict = seen.intersection(flags)
        if conflict:
            raise ValueError('CLI declaration conflict for ' + entry.id + '.' + command.name + ': ' + ', '.join(sorted(conflict)))
        seen.update(flags)


def build_parser(entries, lookup=None, stdout=None, stderr=None):
    parser_class = partial(StreamParser, cli_stdout=stdout, cli_stderr=stderr)
    root = parser_class(description=__doc__, allow_abbrev=False)
    root.add_argument('--format', choices=('text', 'msgpack'), default='text')
    discovery = root.add_mutually_exclusive_group()
    discovery.add_argument('--list-apps', action='store_true', help='List supplied registrations and CLI support.')
    discovery.add_argument('--list-commands', action='store_true', help='List declared commands only.')
    discovery.add_argument('--complete', nargs='*', metavar='WORD', help='Generate declaration-based completion candidates.')
    apps = root.add_subparsers(dest='app', parser_class=parser_class)
    for entry in entries:
        group = apps.add_parser(entry.id, description=entry.description)
        declared = getattr(entry, 'commands', ())
        if not declared:
            group.set_defaults(unsupported=entry.id)
            continue
        children = group.add_subparsers(dest='command', required=True, parser_class=parser_class)
        for command in declared:
            check_options(entry, command)
            parser = children.add_parser(command.name, help=command.help,
                                         description=command.help, epilog=topic_note(command, lookup) or None)
            parser.set_defaults(operation=command)
            for argument in command.arguments:
                options = dict(help=argument.help, default=argparse.SUPPRESS, dest='value_' + argument.name)
                if argument.kind == 'bool':
                    options.update(action=argparse.BooleanOptionalAction, required=argument.required)
                else:
                    options.update(required=argument.required,
                                   type=lambda value, a=argument: text_value(a, value))
                parser.add_argument('--' + argument.name, **options)
    return root


def validate_result(value, depth=0, budget=None):
    if budget is None:
        budget = [20000, 0]
    budget[0] -= 1
    if depth > 12 or budget[0] < 0:
        raise ValueError('Result exceeds nesting or item limits')
    if value is None or type(value) is bool:
        return
    if type(value) is int and -(1 << 63) <= value < (1 << 63):
        return
    if type(value) is float:
        import math
        if math.isfinite(value):
            return
    if isinstance(value, (str, bytes)):
        budget[1] += len(value.encode('utf-8') if isinstance(value, str) else value)
        if budget[1] > MAX_OUTPUT:
            raise ValueError('Result exceeds output limit')
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            validate_result(item, depth + 1, budget)
        return
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        for key, item in value.items():
            validate_result(key, depth + 1, budget)
            validate_result(item, depth + 1, budget)
        return
    raise ValueError('Unsupported result value')


def printable(value):
    return ''.join(c if c.isprintable() else repr(c)[1:-1] for c in str(value))


def text_lines(value, indent=''):
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(item, (list, tuple, dict)):
                yield indent + printable(key) + ':'
                yield from text_lines(item, indent + '  ')
            else:
                yield indent + printable(key) + ': ' + printable(item)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            if index:
                yield ''
            yield from text_lines(item, indent)
    else:
        yield indent + printable(value)


def encode_result(value, format, pack=None):
    validate_result(value)
    if format == 'msgpack':
        if pack is None:
            from runtime_codec import pack as packb
            pack = packb
        encoded = pack(value)
    else:
        encoded = ('\n'.join(text_lines(value)) + '\n').encode('utf-8')
    if not isinstance(encoded, bytes) or len(encoded) > MAX_OUTPUT:
        raise ValueError('Invalid or oversized encoded result')
    return encoded


def run(entries, context, argv=None, stdout=None, stderr=None, lookup=None, pack=None):
    """Use the actual owner's context. Live handlers execute in that owner process.

    Execution deadlines/cancellation belong to the existing service API, not a
    cloned thread/process. This adapter only bounds input and returned output.
    """
    entries = tuple(entries)
    stderr = sys.stderr if stderr is None else stderr
    try:
        parser = build_parser(entries, lookup, stdout=stdout, stderr=stderr)
        args = parser.parse_args(argv)
        if args.app is not None and (args.list_apps or args.list_commands or args.complete is not None):
            parser.error('Discovery flags cannot be combined with an app operation')
        if args.list_apps:
            result = [dict(app=e.id, title=e.title,
                           cli='declared subset' if getattr(e, 'commands', ()) else 'unsupported: no declared commands')
                      for e in entries]
        elif args.list_commands:
            result = command_rows(entries)
        elif args.complete is not None:
            result = complete(entries, args.complete)
        elif args.app is None:
            parser.error('Choose an app operation or a discovery flag')
        elif hasattr(args, 'unsupported'):
            raise ValueError('App has no declared CLI commands: ' + args.unsupported)
        else:
            from app_command import dispatch
            values = {a.name: getattr(args, 'value_' + a.name) for a in args.operation.arguments if hasattr(args, 'value_' + a.name)}
            result = dispatch(args.operation, values, context)
        output = sys.stdout.buffer if stdout is None else stdout
        output.write(encode_result(result, args.format, pack))
        return 0
    except SystemExit as error:
        return int(error.code)
    except KeyboardInterrupt:
        stderr.write('Command cancelled.\n')
        return 130
    except (ValueError, TypeError, PermissionError, OSError, ImportError, argparse.ArgumentError) as error:
        stderr.write('Error: ' + printable(error) + '\n')
        return 1


if __name__ == '__main__':
    # A process without an owner has no registrations or granted capabilities.
    raise SystemExit(run((), None))
