"""Bounded current contacts, stable handles and one workspace selection."""
from datetime import datetime, timezone
from collections import namedtuple

Change = namedtuple('Change', 'list details status')


class ContactRef:
    __slots__ = ('value',)
    def __init__(self, value): self.value = value


class Model:
    def __init__(self):
        self.contacts = {}; self.order = (); self.selected = None
        self.source = 'waiting for source'; self.fetched = None; self.captured = ''; self.error = None
        self.revision = 0
    @property
    def selection(self): return self.contacts.get(self.selected)
    def apply(self, snapshot):
        if snapshot is None: return Change(False, False, False)
        old_detail = self.selection.value if self.selection else None
        old_list = tuple((c, self.contacts[c].value.name, self.contacts[c].value.last, self.contacts[c].value.packets) for c in self.order)
        old_status = (self.source, self.captured, self.error)
        if snapshot.rows is not None:
            retained = {}
            for row in snapshot.rows:
                ref = self.contacts.get(row.call)
                if ref is None: ref = ContactRef(row)
                elif ref.value != row: ref.value = row
                retained[row.call] = ref
            self.contacts = retained; self.order = tuple(row.call for row in snapshot.rows)
            if self.selected not in retained: self.selected = self.order[0] if self.order else None
            self.source, self.captured = snapshot.source, snapshot.captured
        self.error, self.fetched = snapshot.error, snapshot.fetched
        new_list = tuple((c, self.contacts[c].value.name, self.contacts[c].value.last, self.contacts[c].value.packets) for c in self.order)
        detail = self.selection.value if self.selection else None
        change = Change(old_list != new_list, old_detail != detail, old_status != (self.source, self.captured, self.error))
        if any(change): self.revision += 1
        return change
    def select(self, call):
        if call not in self.contacts or call == self.selected: return False
        self.selected = call; return True
    def step(self, delta):
        if not self.order: return False
        index = self.order.index(self.selected) if self.selected in self.order else 0
        return self.select(self.order[max(0, min(len(self.order)-1, index+delta))])


def age(stamp, now):
    if not stamp or stamp.startswith('legacy '): return 'unknown date'
    try:
        dt = datetime.fromisoformat(stamp.replace('Z', '+00:00'))
        if dt.tzinfo is None: return 'unknown timezone'
        seconds = now - dt.timestamp()
        if seconds < -60: return 'future timestamp / check clock'
        seconds = max(0, int(seconds))
        return str(seconds//86400)+'d ago' if seconds >= 86400 else str(seconds//3600)+'h ago' if seconds >= 3600 else str(seconds//60)+'m ago' if seconds >= 60 else str(seconds)+'s ago'
    except (ValueError, OverflowError): return 'unknown date'
