/* SPDX-License-Identifier: MIT */
#include "linear_resource.h"
#include <stdint.h>
#include <string.h>
size_t mbx_linear_size(unsigned w,unsigned h,unsigned *stride){
 if(!w||!h||w>320||h>320||!stride)return 0;
 unsigned pitch=(w+17U)&~15U;*stride=pitch;
 return (size_t)pitch*(h+2U)*4U;
}
int mbx_linear_pack(const struct mbx_linear_source *s,void *dst,size_t capacity){
 unsigned pitch;size_t size;
 if(!s||!s->data||!dst||s->rgba>1||s->opaque>1||s->repeat>1||
    !(size=mbx_linear_size(s->width,s->height,&pitch))||capacity<size)return -1;
 size_t row=(size_t)s->width*4;
 if(s->stride<row||s->bytes<row||(s->height-1)>(s->bytes-row)/s->stride)return -1;
 uintptr_t a=(uintptr_t)s->data,b=(uintptr_t)dst;
 if(a>UINTPTR_MAX-s->bytes||b>UINTPTR_MAX-size||!(a+s->bytes<=b||b+size<=a))return -1;
 unsigned char *out=dst;size_t out_row=(size_t)pitch*4;
 for(unsigned y=0;y<s->height;++y){
  const unsigned char *in=s->data+(size_t)y*s->stride;
  unsigned char *line=out+(size_t)(y+1)*out_row+4;
  if(!s->rgba&&!s->opaque)memcpy(line,in,row);
  else for(unsigned x=0;x<s->width;++x){
   const unsigned char *v=in+4*x;unsigned char *q=line+4*x;
#if defined(__BYTE_ORDER__) && __BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__
   uint32_t pixel;memcpy(&pixel,v,4);
   if(s->rgba)pixel=(pixel&0xff00ff00U)|((pixel&255U)<<16)|((pixel>>16)&255U);
   if(s->opaque)pixel|=0xff000000U;
   memcpy(q,&pixel,4);
#else
   q[0]=v[s->rgba?2:0];q[1]=v[1];q[2]=v[s->rgba?0:2];q[3]=s->opaque?255:v[3];
#endif
  }
  memcpy(line-4,line+(s->repeat?s->width-1:0)*4,4);
  memcpy(line+row,line+(s->repeat?0:s->width-1)*4,4);
  memset(line+row+4,0,(pitch-s->width-2)*4);
 }
 memcpy(out,out+(size_t)(s->repeat?s->height:1)*out_row,out_row);
 memcpy(out+(size_t)(s->height+1)*out_row,out+(size_t)(s->repeat?1:s->height)*out_row,out_row);
 return 0;
}
