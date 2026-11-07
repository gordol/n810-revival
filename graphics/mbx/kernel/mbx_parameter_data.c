/* SPDX-License-Identifier: MIT */
#include "mbx_parameter_data.h"
int mbx_background_parameter(unsigned *w,unsigned n)
{
 unsigned i;
 if(!w||n<MBX_BACKGROUND_WORDS)return -22;
 for(i=0;i<MBX_BACKGROUND_WORDS;++i)w[i]=0;
 w[0]=0xe0000000U;w[1]=0xa8800000U;w[2]=0x0e000000U;
 w[3]=0xd6887610U;w[4]=0x22220e80U;
 for(i=11;i<=16;++i)w[i]=0x3f800000U;
 return 0;
}
int mbx_tile_headers(unsigned *w,unsigned capacity,unsigned tx,unsigned ty,unsigned gx,unsigned gy)
{
 unsigned nx,ny,group_words,x,y,i,j,index;
 if(!w||!tx||!ty||!gx||!gy||tx>256||ty>256||gx>256||gy>256)return -22;
 nx=(tx+gx-1)/gx;ny=(ty+gy-1)/gy;
 if(nx>256/gx||ny>256/gy)return -22;
 group_words=gx*gy*2U;
 if(nx*ny*group_words>capacity)return -22;
 for(i=0;i<nx*ny*group_words;++i)w[i]=0;
 for(y=0;y<ny;++y)for(x=0;x<nx;++x){
  index=(y*nx+x)*group_words;
  j=0x22000000U|(x*gx)|((y*gy)<<8);
  for(i=0;i<gx*gy;++i)w[index+2*i]=j;
 }
 return 0;
}
int mbx_render_list32(unsigned *words,unsigned capacity)
{
 unsigned i;if(!words||capacity<8)return -22;
 for(i=0;i<8;++i)words[i]=0;
 words[0]=0xe2000000U;
 return 0;
}
int mbx_background32(unsigned *words,unsigned capacity)
{
 int error=mbx_background_parameter(words,capacity);
 if(error)return error;
 /* Original0x801ba8ec derives padded4x4tile extent64x64 pixels.
  * 0x801ba974 patches template+1c,+28,+54,+64 with converted
  * fixed16 values. Doubled extent128 and extent/1024=1/16. */
 words[7]=0x43000000U;words[10]=0x43000000U;
 words[21]=0x3d800000U;words[25]=0x3d800000U;
 return 0;
}
