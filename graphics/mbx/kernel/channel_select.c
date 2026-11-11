/* SPDX-License-Identifier: MIT */
#include "channel_select.h"
#include "mbx_vgp_transform.h"
#include "mbx_vgp_isa.h"
/* The raw/pretransformed selector produced no TA parameter records in the
 * current context. Deliver both texture coordinates through the known VGP
 * transform path instead. Fixed driver-owned64x64 source views, never user VAs. */
/* Exact IEEE754 encoding of a small positive integer times 2^-shift.
 * Kernel code performs no floating-point operations. */
static unsigned scaled(unsigned value,unsigned shift)
{
 unsigned top=0,v=value;
 while(v>>=1)++top;
 return ((127U+top-shift)<<23)|((value<<(23-top))&0x7fffffU);
}
int mbx_channel_select_region(unsigned width,unsigned height,unsigned mask, struct mbx_command *out,
                         unsigned capacity, unsigned *written)
{
 unsigned at=0,i,j,program[20],color=0xe0000000U;
 struct mbx_vgp_source uv={0,3,0xe4,0};
 unsigned vertices[4][8]={
  {0xbf800000U,0xbf800000U,0,0x3f800000U,0,0,0,0x3f800000U},
  {0x3f800000U,0xbf800000U,0,0x3f800000U,0x3d000000U,0,0,0x3f800000U},
  {0xbf800000U,0x3f800000U,0,0x3f800000U,0,0x3d000000U,0,0x3f800000U},
  {0x3f800000U,0x3f800000U,0,0x3f800000U,0x3d000000U,0x3d000000U,0,0x3f800000U}
 };
 if(mask>15||!out||!written||capacity<MBX_CHANNEL_SELECT_COMMANDS||
    width<16||height<16||width>320||(height>192&&!(width==240&&height==320))||(width&15)||(height&15)||
    width*height*8U>778240U)return -22;
 vertices[1][4]=vertices[3][4]=scaled(width,11);
 vertices[2][5]=vertices[3][5]=scaled(height,11);
 if(mbx_vgp_transform(0,4,112,program,16)!=8 ||
    mbx_vgp_encode(1,3,15,&uv,1,program+16) ||
    mbx_vgp_encode(1,4,15,&uv,1,program+18))return -22;
 if(mask&1)color|=0x7c00;
 if(mask&2)color|=0x3e0;
 if(mask&4)color|=0x1f;
 if(mask&8)color|=0x1f8000;
#define FIFO(v) (out[at++]=(struct mbx_command){MBX_FIFO,(v)})
 FIFO(0x90000009U);for(i=0;i<20;++i)FIFO(program[i]);
 FIFO(0x8000ffffU);for(i=0;i<16;++i)FIFO(i==2?0x01000900U:0xf0000000U);
 FIFO(0xa0000004U);
 for(i=0;i<16;++i)FIFO(i%5==0?0x3f800000U:0);
 for(i=0;i<4;++i)FIFO(mask&(1U<<i)?0x3f800000U:0);
 FIFO(0x10000080U);
 FIFO(scaled(width,1));FIFO(scaled(width,1));
 FIFO(scaled(height,1));FIFO(scaled(height,1));
 FIFO(0x3f000000U);FIFO(0x3f000000U);
 FIFO(0x1000006fU);FIFO(0x22250e80U);FIFO(color);
 FIFO(0xa8818000U);FIFO(0x0e000000U|((width>>4)<<18)|(0x201000U>>7));FIFO(0xd6887610U);
 FIFO(0xa8818000U);FIFO(0x0e000000U|((width>>4)<<18)|((0x201000U+width*height*4U)>>7));FIFO(0x9ac45b88U);
 FIFO(0x4004U);FIFO(0);
 FIFO(0x40000000U);FIFO(0x70023004U);
 for(i=0;i<4;++i)for(j=0;j<8;++j)FIFO(vertices[i][j]);
 out[at++]=(struct mbx_command){MBX_POLYGON_CONTROL,1};
#undef FIFO
 *written=at;return 0;
}

int mbx_channel_select64(unsigned mask,struct mbx_command *out,unsigned capacity,unsigned *written)
{return mbx_channel_select_region(64,64,mask,out,capacity,written);}
