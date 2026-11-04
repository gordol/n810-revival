"""Optional app operation declarations; no UI, service startup or codec imports."""
from collections import namedtuple
from collections.abc import Mapping
import re

_NAME=re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
_TOPIC=re.compile(r'[a-z][a-z0-9.-]{0,79}\Z')
_CALL=re.compile(r'[A-Z0-9]{1,12}(?:-(?:[0-9]|1[0-5]))?\Z')

class Argument(namedtuple('Argument','name kind help required default minimum maximum',defaults=(False,None,None,None,))):
    __slots__=()
    name:str
    kind:str
    help:str
    required:bool
    default:object
    minimum:object
    maximum:object

class Command(namedtuple('Command','name help handler arguments capability effect manual_topic',defaults=((),'','read',None,))):
    __slots__=()
    name:str
    help:str
    handler:object
    arguments:tuple
    capability:str
    effect:str
    manual_topic:object


def _text(value,label,maximum):
    if not isinstance(value,str) or not 1<=len(value)<=maximum or not value.isprintable():
        raise ValueError('Invalid command '+label)
    return value


def _record(value,cls):
    if type(value) is cls:return value
    if not isinstance(value,dict) or set(value)-set(cls._fields):
        raise ValueError('Invalid '+cls.__name__+' declaration')
    try:return cls(**value)
    except TypeError as error:raise ValueError('Incomplete '+cls.__name__+' declaration') from error


def _value(argument,value):
    if argument.kind=='int':
        if type(value) is not int or not -(1<<63)<=value<(1<<63):
            raise ValueError('Expected signed integer for '+argument.name)
        if argument.minimum is not None and value<argument.minimum or argument.maximum is not None and value>argument.maximum:
            raise ValueError('Argument outside declared range: '+argument.name)
    elif argument.kind=='bool':
        if type(value) is not bool:raise ValueError('Expected boolean for '+argument.name)
    else:
        _text(value,'argument '+argument.name,1024)
        if argument.kind=='call' and not _CALL.fullmatch(value):
            raise ValueError('Invalid callsign or SSID: '+argument.name)
    return value


def _argument(value):
    value=_record(value,Argument)
    if not isinstance(value.name,str) or not _NAME.fullmatch(value.name):raise ValueError('Invalid argument name')
    if value.kind not in ('int','bool','str','path','call'):raise ValueError('Unsupported argument kind')
    _text(value.help,'argument help',500)
    if type(value.required) is not bool:raise ValueError('Argument required must be boolean')
    if value.required and value.default is not None:raise ValueError('Required argument cannot have a default')
    if value.kind!='int' and (value.minimum is not None or value.maximum is not None):
        raise ValueError('Only integer arguments have numeric bounds')
    for bound in (value.minimum,value.maximum):
        if bound is not None and (type(bound) is not int or not -(1<<63)<=bound<(1<<63)):
            raise ValueError('Argument bounds must be signed integers')
    if value.minimum is not None and value.maximum is not None and value.minimum>value.maximum:
        raise ValueError('Reversed argument bounds')
    if value.default is not None:_value(value,value.default)
    return value


def normalize_commands(records):
    """Validate only explicitly supplied metadata, without invoking handlers."""
    if not isinstance(records,(tuple,list)) or len(records)>32:raise ValueError('Invalid command list')
    result=[]
    for record in records:
        value=_record(record,Command)
        if not isinstance(value.name,str) or not _NAME.fullmatch(value.name):raise ValueError('Invalid command name')
        _text(value.help,'help',500)
        if not callable(value.handler):raise ValueError('Command handler must be callable')
        if not isinstance(value.capability,str) or not _NAME.fullmatch(value.capability):
            raise ValueError('Command requires an explicit capability')
        if value.effect!='read':raise ValueError('Unsupported command effect')
        if value.manual_topic is not None and (not isinstance(value.manual_topic,str) or not _TOPIC.fullmatch(value.manual_topic)):
            raise ValueError('Invalid manual topic reference')
        if not isinstance(value.arguments,(tuple,list)) or len(value.arguments)>32:raise ValueError('Invalid argument list')
        arguments=tuple(_argument(item) for item in value.arguments)
        if len({item.name for item in arguments})!=len(arguments):raise ValueError('Duplicate argument name')
        result.append(Command(value.name,value.help,value.handler,arguments,value.capability,value.effect,value.manual_topic))
    if len({item.name for item in result})!=len(result):raise ValueError('Duplicate command name')
    return tuple(result)


def dispatch(command,values,context):
    """Invoke a read operation using an explicit caller-owned capability context.

    This module grants nothing and acquires no services. The caller supplies
    its existing services and policy; live owners must remain in their process.
    """
    command=normalize_commands((command,))[0]
    capabilities=getattr(context,'capabilities',None)
    if not isinstance(capabilities,(set,frozenset)) or any(not isinstance(item,str) for item in capabilities):
        raise PermissionError('An explicit capability context is required')
    if command.capability not in capabilities:raise PermissionError('Command is not authorized for this context')
    if not isinstance(getattr(context,'services',None),Mapping):raise ValueError('Explicit existing service context required')
    if not isinstance(values,Mapping):raise ValueError('Command arguments must be a mapping')
    names={argument.name for argument in command.arguments}
    if set(values)-names:raise ValueError('Unknown command argument')
    validated={}
    for argument in command.arguments:
        if argument.name in values:validated[argument.name]=_value(argument,values[argument.name])
        elif argument.required:raise ValueError('Missing required argument: '+argument.name)
        else:validated[argument.name]=argument.default
    return command.handler(context,validated)
