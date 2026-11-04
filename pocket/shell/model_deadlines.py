"""Small per-owner deadlines for the existing single-threaded desktop loop."""
class ModelDeadlines:
    def __init__(self):self.deadlines={}
    def due(self,now):return {owner for owner,deadline in self.deadlines.items() if deadline<=now}
    def arm(self,delays,now,serviced=()):
        # An unrelated owner's refresh must never postpone an existing deadline.
        self.deadlines={owner:now+delay if owner in serviced or owner not in self.deadlines else min(self.deadlines[owner],now+delay)
                        for owner,delay in delays.items() if delay is not None}
    def delay(self,now):return max(0,min(self.deadlines.values())-now) if self.deadlines else None
