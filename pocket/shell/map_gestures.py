"""Isolated map bridge for Viewer review. Does not replace a production map class."""
from double_tap import DoubleTap


def map_candidate(base, *, policy):
    class StationMap(base):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not hasattr(self, '_pan_dragged'):
                raise ValueError('Map bridge requires the reviewed permanent drag/slop latch')
            self.double_tap = DoubleTap(**policy)
            self._session_changed=lambda:None

        def bind_session(self,callback):
            self._session_changed=callback

        def session_state(self):
            return dict(double_tap_interval_ms=self.double_tap.interval_ns//1_000_000)

        def restore_session(self,state):
            value=state.get('double_tap_interval_ms',600) if isinstance(state,dict) else 600
            if type(value) is not int or not 250<=value<=1000:value=600
            self.double_tap.interval_ns=value*1_000_000
            self.double_tap.reset()

        def set_double_tap_interval(self,value):
            if type(value) is not int or not 250<=value<=1000:raise ValueError('Double-tap interval must be 250 to 1000 milliseconds')
            if value*1_000_000==self.double_tap.interval_ns:return
            self.double_tap.interval_ns=value*1_000_000;self.double_tap.reset();self._session_changed()

        def double_tap_row(self):
            from controls import Slider
            return Slider('Double-tap interval',lambda:self.double_tap.interval_ns//1_000_000,
                lambda value:self.set_double_tap_interval(round(value)),250,1000,50,lambda value:f'{value} ms').row()

        def reset_double_tap(self):
            self.double_tap.reset()

        def cancel_pointer(self):
            self.reset_double_tap()
            return super().cancel_pointer()

        def key(self, key):
            self.reset_double_tap()
            return super().key(key)

        def pointer_event(self, event, width):
            _, button, x, y, released = event
            context = (self._image_view or (self.center, self.span), width, self.height,
                       id(self._image), self.filter_open)
            empty = (not self.filter_open and 0 <= x < width
                     and 2 <= y < self.height-1 and not self.entities_at(x, y))
            zoom = self.double_tap.feed(event, empty=empty, context=context)
            # Movement coalesced out-and-back still invalidates map click selection.
            if self._pan_drag is not None:
                px, py = self._pan_drag[:2]
                left, top, right, bottom = event.bounds
                if (self.double_tap.dragged
                        or max(abs(left-px), abs(right-px)) > policy['slop'][0]
                        or max(abs(top-py), abs(bottom-py)) > policy['slop'][1]):
                    self._pan_dragged = True
            handled = super().pointer(x, y, width, button, released)
            if zoom:
                return self.zoom_at_pointer(x, y, width)
            return handled
    return StationMap
