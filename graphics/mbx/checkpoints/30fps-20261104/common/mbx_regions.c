/* SPDX-License-Identifier: MIT */
#include "mbx_regions.h"
static unsigned spread(unsigned n)
{
 n&=0xffffU;n=(n|(n<<8))&0x00ff00ffU;
 n=(n|(n<<4))&0x0f0f0f0fU;n=(n|(n<<2))&0x33333333U;
 return (n|(n<<1))&0x55555555U;
}
unsigned mbx_morton(unsigned x,unsigned y){return spread(x)|(spread(y)<<1);}
/* Original Nokia list finalizer: 801bdb68..801bdc54. The OPB slot is a
 * word-address cursor with bits29:23 stripped, not a byte pointer. Empty
 * regions get bit25; nonempty lists receive an f0000000 terminator.
 * Unlike that reference, require all cursor writes to stay inside one owned
 * pool, outside its immutable background object. Validate before any writes. */
int mbx_finish_regions(unsigned tiles_x,unsigned tiles_y,
                       const unsigned *opb,unsigned opb_words,
                       unsigned parameter_va,unsigned *parameters,unsigned parameter_words,
                       unsigned immutable_words,unsigned *regions,unsigned region_words)
{
 unsigned x,y,pass;
 if(!opb || !parameters || !regions || !tiles_x || !tiles_y ||
    tiles_x>32 || tiles_y>32 || region_words<tiles_x*tiles_y*2U ||
    parameter_va%4U || immutable_words>parameter_words ||
    parameter_words>(0xffffffffU-parameter_va)/4U)return -22;
 for(pass=0;pass<2;++pass){
  for(y=0;y<tiles_y;++y)for(x=0;x<tiles_x;++x){
   unsigned slot=mbx_morton(x,y),cursor,offset,region=2U*(y*tiles_x+x);
   if(slot>=opb_words)return -22;
   cursor=opb[slot];
   if(!cursor){if(pass)regions[region]|=0x02000000U;continue;}
   cursor&=~0x3f800000U;
   /* Check the word address before multiplying; never wrap a hostile cursor. */
   if(cursor>0x3fffffffU || cursor<parameter_va/4U)return -22;
   offset=cursor-parameter_va/4U;
   if(offset<immutable_words || offset>=parameter_words)return -22;
   if(pass)parameters[offset]=0xf0000000U;
  }
 }
 return 0;
}
