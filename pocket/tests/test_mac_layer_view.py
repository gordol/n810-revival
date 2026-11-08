# SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
# SPDX-License-Identifier: GPL-2.0-or-later
"""Borrowed pixel-layer view required by the default Metal compositor."""
import ctypes as C
from pathlib import Path
import unittest
LIBRARY=Path(__file__).resolve().parents[1]/'build/graphics/renderer.so'

@unittest.skipUnless(LIBRARY.is_file(),'build graphical frontend first')
class LayerView(unittest.TestCase):
 def test_bounds_borrowed_identity_and_owner_lifetime(self):
  lib=C.CDLL(str(LIBRARY))
  lib.pocket_pixel_layer_new.argtypes=[C.c_uint,C.c_uint];lib.pocket_pixel_layer_new.restype=C.c_void_p
  lib.pocket_pixel_layer_free.argtypes=[C.c_void_p]
  view=lib.pocket_mac_layer_view;view.argtypes=[C.c_void_p,C.c_void_p,C.c_void_p,C.c_void_p]
  handle=lib.pocket_pixel_layer_new(2,3);self.assertTrue(handle)
  try:
   width,height=C.c_uint(123),C.c_uint(456);pixels=C.POINTER(C.c_uint32)()
   self.assertEqual(view(None,C.byref(width),C.byref(height),C.byref(pixels)),-1)
   self.assertEqual((width.value,height.value),(123,456));self.assertFalse(pixels)
   self.assertEqual(view(handle,None,C.byref(height),C.byref(pixels)),-1)
   self.assertEqual(view(handle,C.byref(width),C.byref(height),C.byref(pixels)),0)
   self.assertEqual((width.value,height.value),(16,48))
   pointer=C.addressof(pixels.contents);self.assertEqual(list(pixels[:16*48]),[0]*(16*48))
   other=C.POINTER(C.c_uint32)()
   self.assertEqual(view(handle,C.byref(width),C.byref(height),C.byref(other)),0)
   self.assertEqual(C.addressof(other.contents),pointer)
  finally:lib.pocket_pixel_layer_free(handle)
  # Release the borrowed Python views when their explicit owner is freed.
  pixels=None;other=None

if __name__=='__main__':unittest.main()
