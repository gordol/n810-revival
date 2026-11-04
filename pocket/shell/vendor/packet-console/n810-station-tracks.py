"""Bounded received-position tracks and display-local callsign following; no I/O."""
import collections
import datetime
import math
import re

class Tracks:
    def __init__(self,max_stations=16,max_points=64,stale_after=300):
        if not 1<=max_stations<=64 or not 2<=max_points<=256 or not 0<stale_after<=86400:raise ValueError('Invalid track bounds')
        self.max_stations=max_stations;self.max_points=max_points;self.stale_after=stale_after
        self.history=collections.OrderedDict();self.call=None;self.paused=False

    def add(self,call,lat,lon,stamp=None,observed_at=None):
        if not isinstance(call,str) or not re.fullmatch(r'[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?',call):return False
        try:lat,lon=float(lat),float(lon)
        except (ValueError,TypeError):return False
        if not(math.isfinite(lat) and math.isfinite(lon) and -90<=lat<=90 and -180<=lon<=180):return False
        if observed_at is not None and (not isinstance(observed_at,(int,float)) or not math.isfinite(observed_at)):return False
        points=self.history.setdefault(call,collections.deque(maxlen=self.max_points));self.history.move_to_end(call)
        point=dict(lat=lat,lon=lon,time=stamp,observed_at=observed_at)
        def full_time(value):
            try:
                parsed=datetime.datetime.fromisoformat(value)
                return parsed.timestamp() if parsed.tzinfo is not None else None
            except (TypeError,ValueError):return None
        previous=full_time(points[-1]['time']) if points else None
        current=full_time(stamp)
        if previous is not None and current is not None and current<previous:return False
        # Repeated stationary reports refresh liveness without fabricating movement.
        if points and (points[-1]['lat'],points[-1]['lon'])==(lat,lon):
            if observed_at is not None or points[-1]['observed_at'] is None:points[-1]=point
        else:points.append(point)
        while len(self.history)>self.max_stations:
            victim=next((key for key in self.history if key!=self.call),next(iter(self.history)))
            del self.history[victim]
        return True

    def follow(self,call):
        if not isinstance(call,str) or not re.fullmatch(r'[A-Z0-9]{1,6}(?:-(?:[0-9]|1[0-5]))?',call):raise ValueError('Invalid callsign')
        self.call=call;self.paused=False

    def stop(self):self.call=None;self.paused=False
    def pause(self):
        if self.call:self.paused=True
    def resume(self):self.paused=False
    def points(self,call=None):return tuple(dict(p) for p in self.history.get(call or self.call,()))
    def freshness(self,now,call=None):
        points=self.history.get(call or self.call)
        if not points:return 'position unknown'
        observed=points[-1]['observed_at']
        if observed is None or now<observed:return 'age unknown'
        return 'stale' if now-observed>self.stale_after else 'fresh'
    def camera_position(self):
        points=self.history.get(self.call)
        if not points or self.paused:return None
        return points[-1]['lat'],points[-1]['lon']
