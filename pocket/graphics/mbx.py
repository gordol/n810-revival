# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""GPU cell rasterizer. The active MBX service belongs to the display owner."""
import ctypes as C
from array import array
from cells import style
from font_supplement import load as load_font
from paint import foreground,background
class Renderer:
 def __init__(self,host,font,library,require_gpu=True,font_mode="console",**unused):
  self.host=host;self.font=load_font(font,font_mode);self.pixels=bytearray(768000);self.lib=C.CDLL(str(library));self.bulk_batches=0;self.cells_drawn=0
  if not (0<host.width<=512 and 0<host.height<=256 and (self.font.width,self.font.height)==(8,16)):raise ValueError('MBX frontend requires unchanged800x480/8x16layout')
  self.lib.pocket_mbx_open.argtypes=[C.c_int];self.lib.pocket_mbx_open.restype=C.c_void_p
  self.lib.pocket_mbx_error.restype=C.c_char_p
  if hasattr(self.lib,'pocket_mac_renderer'):self.lib.pocket_mac_renderer.restype=C.c_char_p
  self.lib.pocket_mbx_stage.argtypes=[C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
  self.lib.pocket_mbx_render.argtypes=[C.c_void_p,C.c_void_p]
  self.lib.pocket_mbx_jobs.argtypes=[C.c_void_p];self.lib.pocket_mbx_jobs.restype=C.c_uint
  self.lib.pocket_mbx_close.argtypes=[C.c_void_p]
  self.handle=self.lib.pocket_mbx_open(int(require_gpu))
  if not self.handle:raise RuntimeError(self.lib.pocket_mbx_error().decode())
  self.renderer_name=self.lib.pocket_mac_renderer().decode() if hasattr(self.lib,'pocket_mac_renderer') else 'Nokia MBX GPU transform'
  self.font.add_desktop_glyphs()
  coverage=getattr(self.font,'coverage',{})
  ordered_coverage=sorted(coverage)
  self.coverage_codes=(C.c_uint32*len(coverage))(*(ord(ch) for ch in ordered_coverage))
  self.coverage_bits=C.create_string_buffer(b''.join(coverage[ch] for ch in ordered_coverage))
  if coverage:
   self.lib.pocket_mbx_font_coverage.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_uint]
   if self.lib.pocket_mbx_font_coverage(self.handle,self.coverage_codes,self.coverage_bits,len(coverage)):raise ValueError('Native font coverage rejected')
  ordered=sorted(self.font.mapping)
  self.font_codes=(C.c_uint32*len(ordered))(*(ord(ch) for ch in ordered))
  self.font_bits=C.create_string_buffer(b''.join(self.font.glyph(ch) for ch in ordered))
  self.lib.pocket_mbx_stage_batch.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t,C.c_void_p,C.c_void_p,C.c_uint,C.c_void_p,C.c_uint,C.c_uint]
  self.lib.pocket_mbx_stage_region.argtypes=self.lib.pocket_mbx_stage_batch.argtypes+[C.c_uint]*4
  self.lib.pocket_mbx_text.argtypes=[C.c_void_p,C.c_uint,C.c_uint,C.c_void_p,C.c_uint,C.c_void_p,C.c_void_p,C.c_uint,C.c_uint,C.c_uint]
  self.lib.pocket_mbx_blank.argtypes=[C.c_void_p]
  self.lib.pocket_mbx_resize.argtypes=[C.c_void_p,C.c_uint,C.c_uint]
  self.size=(100,30)
  self.resize(max(100,host.width),max(30,host.height))
  self.lib.pocket_mbx_blank(self.handle)
  self.previous_observer=host.observe_composition;host.observe_composition=True;host.invalidate((0,0,100,30))
 def resize(self,cols,rows):
  if self.lib.pocket_mbx_resize(self.handle,cols,rows):raise ValueError("Native desktop resize rejected")
  self.size=(cols,rows);self.pixels=bytearray(cols*8*rows*16*2)
  self.lib.pocket_mbx_blank(self.handle)
 def flush(self,budget=2048):
  h=self.host
  if not (0<h.width<=512 and 0<h.height<=256):raise ValueError('Recreate GPU renderer after resize')
  _,changed,computed=h.flush(budget,serialize=False)
  return self.consume_composed(changed,computed)
 def consume_composed(self,changed,computed):
  # Accept a model-owned native composition batch without flushing it twice.
  h=self.host;palette=h._ansi_colors();drawn=0
  shade=round((10 if h.tinted else 18)*(1-h.overview_opacity)+24*h.overview_opacity)
  try:
   native=h._native
   if native is None or h.front is not native.front or not hasattr(native.lib,'export_cells'):
    raise RuntimeError('MBX GUI requires native batched cell export; Python per-cell fallback refused')
   descriptors=[]
   for color in range(len(palette)):
    fallback=f'2;{shade};{shade};{shade}' if color in (15,16) else '5;232' if color==14 else '2;10;10;10' if color>=4 and h.tinted else '5;233'
    descriptors.append(style(foreground(color,palette),background(color,fallback)))
   if any(bold or underline for _,_,bold,underline in descriptors):
    raise ValueError('Native GPU batch does not yet support styled palette glyphs')
   indices=h.composed_indices
   if not isinstance(indices,memoryview):indices=memoryview(array('I',indices))
   records=native.lib.export_cells(native.front.pointer,indices)
   packed=(C.c_uint32*len(descriptors))(*(fg|(bg<<16) for fg,bg,_,_ in descriptors))
   fallback=style('38;2;0;0;0','2;10;10;10' if h.tinted else '5;233')[1]
   self.layer_palette=packed;self.layer_fallback=fallback;self.layer_key=tuple(packed)
   drawn=self.lib.pocket_mbx_stage_region(self.handle,C.c_char_p(records),len(records),self.font_codes,self.font_bits,len(self.font_codes),packed,len(packed),fallback,h.width,h.height,*getattr(h,"origin",(0,0)))
   if drawn<0:
    import struct
    missing=sorted({ch for _,ch,_ in struct.iter_unpack('<IIQ',records) if ch not in self.font_codes})
    raise ValueError('Native MBX batch rejected; missing glyphs='+str(missing)+' region='+str((h.width,h.height,getattr(h,'origin',(0,0)))))
  except Exception:
   h.invalidate((0,0,100,30));raise
  self.cells_drawn+=drawn;self.bulk_batches+=1
  return changed,computed,drawn
 def finish(self):
  buffer=(C.c_ubyte*len(self.pixels)).from_buffer(self.pixels)
  if self.lib.pocket_mbx_render(self.handle,buffer):raise RuntimeError(self.lib.pocket_mbx_error().decode())
 def close(self):
  if self.handle:self.lib.pocket_mbx_close(self.handle);self.handle=None
  self.host.observe_composition=self.previous_observer
