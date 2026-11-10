/* SPDX-License-Identifier: MIT */
#ifndef MBX_TEXTURE_CACHE_H
#define MBX_TEXTURE_CACHE_H
#include <stdint.h>
#include <string.h>
/* Content-owned snapshot: resource addresses never establish cache validity. */
struct mbx_texture_cache {
 unsigned char linear[8192],packed[8192];
 uint64_t hits,rebuilds;
 unsigned valid;
};
static unsigned mbx_texture_spread(unsigned n){unsigned r=0;for(unsigned i=0;i<6;++i)r|=((n>>i)&1U)<<(2*i);return r;}
static void mbx_texture_pack(unsigned char *dst,const unsigned char *src,unsigned stride)
{
 for(unsigned y=0;y<64;++y)for(unsigned x=0;x<64;++x){
  unsigned address=mbx_texture_spread(y)|(mbx_texture_spread(x)<<1);
  memcpy(dst+2*address,src+y*stride+2*x,2);
 }
}
static const unsigned char *mbx_texture_cached(struct mbx_texture_cache *c,const unsigned char *src,unsigned stride)
{
 unsigned y;
 if(c->valid){
  for(y=0;y<64;++y)if(memcmp(c->linear+y*128,src+y*stride,128))break;
  if(y==64){++c->hits;return c->packed;}
 }
 for(y=0;y<64;++y)memcpy(c->linear+y*128,src+y*stride,128);
 mbx_texture_pack(c->packed,c->linear,128);c->valid=1;++c->rebuilds;return c->packed;
}
#endif
