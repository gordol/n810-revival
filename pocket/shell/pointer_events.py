"""Tuple-compatible pointer source timing and coalesced movement bounds."""
from collections import namedtuple


class SourceStamp(namedtuple('SourceStamp','ns stream kind batch',defaults=('source',None,))):
    __slots__=()
    ns:int
    stream:str
    kind:str
    batch:int | None
    def __post_init__(self):
        if type(self.ns) is not int or self.ns < 0 or not self.stream:
            raise ValueError('invalid pointer source timestamp')
        if self.kind not in ('source', 'ingress') or (self.kind == 'ingress' and
                (type(self.batch) is not int or self.batch < 0)):
            raise ValueError('invalid pointer timestamp provenance')

    def __new__(cls,ns,stream,kind='source',batch=None):
        self=super().__new__(cls,ns,stream,kind,batch)
        self.__post_init__()
        return self


def evdev_stamp(seconds, microseconds, stream):
    if seconds < 0 or not 0 <= microseconds < 1000000:
        return None
    return SourceStamp(seconds*1000000000+microseconds*1000, stream)


class TouchReport(tuple):
    def __new__(cls, x, y, pressed, *, stamp=None):
        value = super().__new__(cls, (x, y, pressed))
        value.stamp = stamp
        return value


class PointerEvent(tuple):
    def __new__(cls, values, *, stamp=None, bounds=None, pixel=None):
        if len(values) != 5 or values[0] != 'mouse':
            raise ValueError('expected existing five-field mouse tuple')
        value = super().__new__(cls, values)
        value.stamp = stamp
        value.bounds = bounds or (value[2], value[3], value[2], value[3])
        value.pixel = pixel
        return value

    def at(self, x, y):
        """Translate coordinates and movement bounds into a window's space."""
        dx, dy = x-self[2], y-self[3]
        left, top, right, bottom = self.bounds
        return type(self)((self[0], self[1], x, y, self[4]), stamp=self.stamp,
                          bounds=(left+dx, top+dy, right+dx, bottom+dy),pixel=self.pixel)


def coalesce_motion(previous, latest):
    """Keep latest motion plus the full excursion, without merging contact edges."""
    a_time, b_time = getattr(previous, 'stamp', None), getattr(latest, 'stamp', None)
    if (previous[1] != 32 or latest[1] != 32 or previous[4] or latest[4]
            or (a_time is None) != (b_time is None)
            or a_time is not None and (a_time.stream != b_time.stream
                or a_time.kind != b_time.kind or a_time.ns > b_time.ns)):
        return None
    a = getattr(previous, 'bounds', (previous[2], previous[3], previous[2], previous[3]))
    b = getattr(latest, 'bounds', (latest[2], latest[3], latest[2], latest[3]))
    return PointerEvent(latest, stamp=b_time,pixel=getattr(latest,'pixel',None),
                        bounds=(min(a[0], b[0]), min(a[1], b[1]),
                                max(a[2], b[2]), max(a[3], b[3])))


def deliver_pointer(form, event, x, y, width):
    """Opt-in metadata delivery; existing forms keep their positional pointer API."""
    handler = getattr(form, 'pointer_event', None)
    if callable(handler):
        typed = event if isinstance(event, PointerEvent) else PointerEvent(event)
        return handler(typed.at(x, y), width)
    pointer = getattr(form, 'pointer', None)
    return pointer(x, y, width, event[1], event[4]) if callable(pointer) else False


def prepare_gestures(host, panel, launcher, event=None, *, manager_mode=False):
    """Clear pending pairs on context/input changes; never cancel map drag ownership."""
    for name, form in host.app_forms.items():
        reset = getattr(form, 'reset_double_tap', None)
        if not callable(reset):
            continue
        window = host.window(name)
        context = (host.desktop, host.focus, host.origin, window.rect,
                   window.opened, window.visible, window.rolled, manager_mode,
                   host.overview, host.screensaver, bool(host.help_lines),
                   bool(getattr(host, 'settings_lines', ())), launcher.active)
        invalidate = context != getattr(form, '_gesture_dispatch_context', None)
        if event is not None:
            if event[0] != 'mouse':
                invalidate = True
            else:
                _, button, x, y, released = event
                if button & 64:
                    invalidate = True
                elif button in (0, 1, 2) and not released:
                    sx, sy = x-host.origin[0], y-host.origin[1]
                    topmost = next((w for w in reversed(host.windows)
                                    if host.shown(w) and w.x <= sx < w.x+w.w
                                    and w.y <= sy < w.y+w.rect[3]), None)
                    invalidate = invalidate or not (topmost is window and
                        not panel.at(x, y) and window.x < sx < window.x+window.w-1
                        and window.y < sy < window.y+window.h-1)
        if invalidate:
            reset()
        form._gesture_dispatch_context = context
