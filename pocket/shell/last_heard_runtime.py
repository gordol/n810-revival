"""Lazy desktop registration over existing cached receive and station facts."""


def descriptor(factory):
    return dict(id='last-heard',title='Last heard',factory=factory,
                preferred_size=(58,20),minimum_size=(25,12),
                category='Stations & Maps',
                description='Retained receptions and selected station; no radio commands.',
                help=(('Last heard',('L shows the last identifiable retained APRS reception.',
                                     'S shows the independently selected station.',
                                     'Own position must come from an explicit location fix.',
                                     'Reported addresses do not prove the physical radio route.')),))


class SnapshotCache:
    """Adapt only changed owner revisions; rendering reads a retained DTO."""
    def __init__(self,catalog=None,context=None,reference=None):
        from last_heard_model import Snapshot
        self.catalog=catalog;self.context=context;self.reference=reference
        self.snapshot=Snapshot();self.key=None;self.rebuilds=0

    def update(self):
        from last_heard_aprs import adapt
        from last_heard_model import Position
        receive=self.catalog.feed_view() if self.catalog is not None else {}
        fix=self.reference() if self.reference is not None else None
        if fix is not None and not isinstance(fix,Position):
            raise TypeError('Last heard reference must be an explicit Position or None')
        key=(getattr(self.catalog,'records_revision',None),
             receive.get('source'),receive.get('connection'),
             getattr(self.context,'map_revision',None),
             getattr(self.context,'revision',None),fix)
        if key==self.key:return False
        self.snapshot=adapt(receive,getattr(self.context,'map_catalog',None),
                            getattr(self.context,'detail',None),reference=fix)
        self.key=key;self.rebuilds+=1
        return True

    def __call__(self):return self.snapshot

    def close(self):
        # Borrowed providers remain owned by the desktop, never by this window.
        from last_heard_model import Snapshot
        self.catalog=None;self.context=None;self.reference=None
        self.snapshot=Snapshot();self.key=None


class LastHeardApp:
    dispose_on_close=True
    def __init__(self,source,visible=lambda:True):
        from last_heard_view import LastHeard
        self.source=source;self.visible=visible;self.active=False;self.closed=False
        self.view=LastHeard(source)
    def open(self):
        if not self.closed:self.active=True
    def set_active(self,opened):self.active=bool(opened) and not self.closed
    def poll(self):
        if self.active and self.visible():self.source.update()
    def poll_interval(self):return None
    def on_close(self):self.active=False
    def close(self):
        if self.closed:return
        self.closed=True;self.active=False;self.source.close()
    @property
    def stats(self):return dict(snapshot_rebuilds=self.source.rebuilds)
