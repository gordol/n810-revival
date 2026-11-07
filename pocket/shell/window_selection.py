# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Window-focus mode at the current desktop scale; no overview transition."""
import math


def directional_name(rectangles, selected, direction):
    """Choose a nearby window center in the requested half-plane."""
    if not rectangles:
        return None
    if selected not in rectangles:
        return next(iter(rectangles))
    x, y, width, height = rectangles[selected]
    origin = x+width/2, y+height/2
    dx, dy = {'left':(-1,0), 'right':(1,0), 'up':(0,-1), 'down':(0,1)}[direction]
    candidates = []
    for name, (x, y, width, height) in rectangles.items():
        if name == selected:
            continue
        x, y = x+width/2-origin[0], y+height/2-origin[1]
        forward, sideways = x*dx+y*dy, abs(x*dy-y*dx)
        if forward > 0:
            candidates.append((forward+2*sideways, math.hypot(x,y), name))
    return min(candidates)[2] if candidates else selected


class WindowSelection:
    def __init__(self, host, bindings):
        self.host, self.bindings = host, bindings
        self.active = False
        self.last_escape = None
        self.original_focus = None

    def windows(self):
        return [self.host.window(name) for name in self.host.focus_order
                if self.host.shown(self.host.window(name))]

    def reset_sequence(self):
        self.last_escape = None

    def double_escape(self, key, now, allowed=True):
        previous = self.last_escape
        self.last_escape = now if key == '\x1b' and allowed else None
        if not self.bindings.double_escape or not allowed or key != '\x1b':
            return False
        if previous is not None and 0 <= now-previous <= .4:
            self.enter()
            return True
        return False

    def enter(self):
        self.reset_sequence()
        self.original_focus = self.host.focus
        if self.host.overview:
            self.host.toggle_overview()
        self.active = True
        label = self.bindings.label
        self.host.window_selection_hint = ('Select window · '+label('windows','focus.next')+'/'+
            label('windows','focus.previous')+' cycle · arrows choose direction · '+
            label('windows','activate')+' accept · '+label('windows','back')+' cancel')
        self.host.invalidate((0,0,self.host.width,self.host.height))

    def finish(self,cancel=False):
        self.active = False
        self.reset_sequence()
        self.host.window_selection_hint = None
        if cancel and any(w.name==self.original_focus for w in self.windows()):
            self.host.select(self.original_focus)
        self.host.invalidate((0,0,self.host.width,self.host.height))

    def key(self, key):
        """Return a selected window name on acceptance; consume other keys locally."""
        key = self.bindings.resolve('windows', key)
        if key in ('\t','backtab'):
            self.host.cycle_focus(key == 'backtab')
        elif key in ('left','right','up','down'):
            rectangles = {w.name:w.rect for w in self.windows()}
            selected=directional_name(rectangles,self.host.focus,key)
            if selected:self.host.select(selected)
        elif key in ('\r','\n'):
            selected = self.host.focus
            self.finish()
            return selected
        elif key == '\x1b':
            self.finish(cancel=True)
        return None

    def pointer(self, button, x, y, released):
        self.reset_sequence()
        if button != 0 or released:
            return None
        for window in reversed(self.host.windows):
            if not self.host.shown(window):continue
            left, top, width, height = window.rect
            if left <= x < left+width and top <= y < top+height:
                selected = window.name
                self.finish()
                return selected
        return None
