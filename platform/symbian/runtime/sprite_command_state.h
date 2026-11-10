// SPDX-License-Identifier: MIT
#pragma once
#include <cstdint>
// One command-list lifetime. Only bitmap/brush, feature and rectangular-clip
// operations preserve this shadow. Every other operation invalidates it.
struct n810_sprite_command_state {
 enum kind {other,bitmap,brush,feature,clip,bitmap_clip};
 uint64_t features[32]{};uint32_t known=0;
 uint64_t clip_a=0,clip_b=0;kind clip_kind=other;
 bool redundant(kind op,uint64_t a=0,uint64_t b=0){
  if(op==bitmap||op==brush)return false;
  if(op==feature){unsigned f=uint32_t(a);if(f>=32){known=0;clip_kind=other;return false;}
   const uint32_t bit=uint32_t(1)<<f;bool same=(known&bit)&&features[f]==a;features[f]=a;known|=bit;return same;}
  if(op==clip||op==bitmap_clip){bool same=clip_kind==op&&clip_a==a&&clip_b==b;clip_kind=op;clip_a=a;clip_b=b;return same;}
  known=0;clip_kind=other;return false;
 }
};
