# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Mac-only native-density text; bounded fallback preserves complex scene order.

The ordinary desktop already resolves translucent cells into one semantic glyph
and color. Direct pixel apps instead replace a rectangle. Support that image
plus its own semantic labels only when no higher window/launcher/outline must
replay translucent pixels over the text. Unsupported scenes keep complete old
rendering; never suppress their glyphs and hope an overlay reconstructs them.
"""
import ctypes as C
import os
import sys

def supported(host,apps,*,raw_capture=False):
 if raw_capture:return False
 if not apps:return True
 if os.environ.get('POCKET_GPU_COMPOSE')=='1' or host.launcher_lines or host.drag:return False
 names={app.name for app in apps};seen=False
 for window in host.windows:
  if not host.shown(window):continue
  if seen:return False
  if window.name in names:seen=True
 return len(apps)==1

class Text:
 def __init__(self,display):
  self.display=display;self.lib=display.lib
  self.lib.pocket_native_text_stage.argtypes=[C.c_void_p,C.c_size_t]
  self.lib.pocket_native_text_clear.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_int,C.c_int,C.c_uint,C.c_uint]
  self.lib.pocket_native_text_marks.argtypes=[C.c_void_p,C.c_size_t,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_int,C.c_int,C.c_uint,C.c_uint]
 def stage(self,renderer,apps,rectangles):
  data=renderer.text_cells();cols,rows=renderer.size
  for x,y,w,h in rectangles:
   if self.lib.pocket_native_text_clear(data,len(data),cols,rows,x,y,w,h):raise ValueError('Native text image clipping rejected')
  for app in apps:
   marks=getattr(app,'presentation_marks',lambda:None)()
   if marks:
    items,x,y,w,h=marks
    if self.lib.pocket_native_text_marks(data,len(data),cols,rows,items,len(items),x,y,w,h):raise ValueError('Native map text rejected')
  if self.lib.pocket_native_text_stage(data,len(data)):raise ValueError('Native presentation text rejected')
 def clear(self):
  if self.lib.pocket_native_text_stage(None,0):raise ValueError('Native presentation reset rejected')

def create(display,font_mode):
 if sys.platform!='darwin' or font_mode!='smooth' or display is None:return None
 return Text(display) if hasattr(display.lib,'pocket_native_text_stage') else None
