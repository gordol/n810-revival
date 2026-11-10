/* SPDX-License-Identifier: MIT */
#include "channel_wire.h"
#include <stdint.h>
#include <string.h>
static int overlap(const void *a,unsigned an,const void *b,unsigned bn){
 uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;return x<=y?y-x<an:x-y<bn;
}
int mbx_pack_channel_region(unsigned width,unsigned height,unsigned mask,
 const void *a,unsigned a_bytes,const void *b,unsigned b_bytes,
 void *out,unsigned capacity,unsigned *written)
{
 unsigned size,header[20];
 if(width<16||width>320||height<16||height>192||(width&15)||(height&15)||mask>15||!a||!b||!out||!written)return -22;
 size=width*height*4U;
 if(a_bytes<size||b_bytes<size||capacity<80+size*2||overlap(a,size,out,80+size*2)||overlap(b,size,out,80+size*2))return -22;
 memset(header,0,sizeof(header));header[0]=0x3156474dU;header[1]=10;header[2]=80+size*2;
 header[4]=width;header[5]=height;header[10]=0x3f800000U;header[12]=1;header[13]=size*2;
 header[16]=9;header[17]=size*2;header[19]=mask;
 memcpy(out,header,80);memcpy((unsigned char*)out+80,a,size);memcpy((unsigned char*)out+80+size,b,size);
 *written=80+size*2;return 0;
}
