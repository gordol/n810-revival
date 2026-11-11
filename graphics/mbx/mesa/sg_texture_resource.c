/* SPDX-License-Identifier: MIT */
#include "sg_texture_resource.h"
#include <string.h>
#include <stdint.h>
static int side_log(uint32_t side){
 if(side<8||side>SG_TEXTURE_MAX_SIDE||(side&(side-1)))return -1;
 int n=0;while(side>1){side>>=1;++n;}return n;
}
int sg_texture_dimension_word(uint32_t side,uint32_t *word){
 int n=side_log(side);if(n<0||!word)return -1;
 /* N95 dimension construction independently pinned at804b0240..804b0250.
  * These fields do not establish format support or physical acceptance. */
 *word=((uint32_t)(n-3)<<24)|((uint32_t)(n-3)<<20);return 0;
}
static unsigned spread(unsigned v){
 v=(v|(v<<8))&0x00ff00ffu;v=(v|(v<<4))&0x0f0f0f0fu;
 v=(v|(v<<2))&0x33333333u;return (v|(v<<1))&0x55555555u;
}
int sg_texture_pack(void *dst,size_t capacity,const void *src,const struct sg_texture_desc *d){
 if(!dst||!src||!d||side_log(d->side)<0)return -1;
 unsigned bpp=d->format==SG_RGB565?2:d->format==SG_RGBA8888?4:0;
 if(!bpp)return -1;
 size_t row=(size_t)d->side*bpp,bytes=row*d->side;
 if(d->row_bytes<row||d->source_bytes<row||(size_t)(d->side-1)>(d->source_bytes-row)/d->row_bytes||capacity<bytes)return -1;
 uintptr_t a=(uintptr_t)dst,b=(uintptr_t)src;
 if(a>UINTPTR_MAX-bytes||b>UINTPTR_MAX-d->source_bytes||!(a+bytes<=b||b+d->source_bytes<=a))return -1;
 unsigned char *out=dst;const unsigned char *in=src;
 for(unsigned y=0;y<d->side;++y)for(unsigned x=0;x<d->side;++x){
  size_t at=(spread(y)|(spread(x)<<1))*bpp;
  memcpy(out+at,in+(size_t)y*d->row_bytes+(size_t)x*bpp,bpp);
 }
 return 0;
}
int sg_texture_verified(const struct sg_texture_desc *d){
 /* Do not advertise larger/RGBA resources merely because packing works. */
 return d&&d->side==64&&d->format==SG_RGB565&&d->row_bytes>=128&&
  d->source_bytes>=128&&63u<=(d->source_bytes-128)/d->row_bytes;
}
