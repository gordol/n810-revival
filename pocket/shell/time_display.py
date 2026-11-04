"""Display-only time zones. Original evidence and scheduling instants stay untouched."""
from datetime import datetime,timezone

ZONE='UTC'
_zone=timezone.utc


def validate_zone(name):
    if not isinstance(name,str) or len(name)>80:raise ValueError('Use an IANA time zone such as UTC or America/Los_Angeles')
    if name=='UTC':return timezone.utc
    from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
    try:return ZoneInfo(name)
    except (ZoneInfoNotFoundError,ValueError) as error:raise ValueError('Unknown IANA time zone: '+name) from error


def configure(name):
    global ZONE,_zone
    if name!=ZONE:_zone=validate_zone(name);ZONE=name


def instant(value):
    try:
        parsed=value if isinstance(value,datetime) else datetime.fromisoformat(value.replace('Z','+00:00'))
        return parsed.astimezone(timezone.utc) if parsed.tzinfo is not None else None
    except (TypeError,ValueError,AttributeError):return None


def epoch(value):
    parsed=instant(value)
    return parsed.timestamp() if parsed is not None else None


def displayed(value):
    parsed=instant(value)
    return parsed.astimezone(_zone) if parsed is not None else None


def clock(value):
    parsed=displayed(value)
    return parsed.strftime('%H:%M:%S') if parsed is not None else '??:??:??'


def day(value):
    parsed=displayed(value)
    return (parsed.strftime('%Y-%m-%d') if parsed is not None else 'Date unknown')+' '+ZONE


def now_at(timestamp):return datetime.fromtimestamp(timestamp,timezone.utc).astimezone(_zone)


def full(value):
    parsed=displayed(value)
    return parsed.strftime('%Y-%m-%d %H:%M:%S %Z') if parsed is not None else 'Date/zone unknown'
