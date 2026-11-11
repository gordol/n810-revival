/* SPDX-License-Identifier: GPL-3.0-or-later */
#pragma once
#include <cstdint>
namespace eka2l1::epoc::glyph_clip {
// Coordinates are native, unscaled target pixels. Unknown/invalid geometry
// keeps the draw. Two-pixel padding conservatively retains boundary glyphs.
// This is command rejection, never rasterization or text-layout alteration.
template<class Rect, class Rectangles>
bool may_intersect(const Rect &r, const Rectangles &clips) {
 if (r.size.x <= 0 || r.size.y <= 0) return true;
 const int64_t x0=int64_t(r.top.x)-2, y0=int64_t(r.top.y)-2;
 const int64_t x1=int64_t(r.top.x)+r.size.x+2, y1=int64_t(r.top.y)+r.size.y+2;
 for (const auto &c : clips) {
  if (c.size.x < 0 || c.size.y < 0) return true;
  if (!c.size.x || !c.size.y) continue;
  if (x0<int64_t(c.top.x)+c.size.x && x1>c.top.x &&
      y0<int64_t(c.top.y)+c.size.y && y1>c.top.y) return true;
 }
 return false;
}
}
