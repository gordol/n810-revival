/* Exact content cache; no hashes, borrowed pointers or GPU lifetime claims. */
#ifndef MBX_RESOURCE_CACHE_H
#define MBX_RESOURCE_CACHE_H
#include <stdint.h>
#include <string.h>
#include "sg_texture_resource.h"
struct mbx_resource_cache {
 unsigned side,format,valid;
 uint64_t hits,rebuilds;
 unsigned char source[32768],packed[32768];
};
static const unsigned char *mbx_resource_cached(struct mbx_resource_cache *c,const void *source,const struct sg_texture_desc *d){
 if(!c||!source||!d||(d->format!=SG_RGB565&&d->format!=SG_RGBA8888)||(d->side!=64&&d->side!=128))return NULL;
 unsigned row=d->side*(d->format==SG_RGB565?2:4),bytes=row*d->side;
 if(bytes>sizeof(c->source)||d->row_bytes<row||d->row_bytes>(UINT32_MAX-row)/(d->side-1)||d->source_bytes<(d->side-1)*d->row_bytes+row)return NULL;
 int same=c->valid&&c->side==d->side&&c->format==d->format;
 for(unsigned y=0;same&&y<d->side;++y)if(memcmp(c->source+y*row,(const unsigned char *)source+y*d->row_bytes,row))same=0;
 if(same){++c->hits;return c->packed;}
 if(sg_texture_pack(c->packed,sizeof(c->packed),source,d))return NULL;
 for(unsigned y=0;y<d->side;++y)memcpy(c->source+y*row,(const unsigned char *)source+y*d->row_bytes,row);
 c->valid=1;c->side=d->side;c->format=d->format;++c->rebuilds;return c->packed;
}
/* Source may be cached immutable data or the destination itself. Never mutate
 * the cached canonical upload: repeated frames must not toggle channel order. */
static inline void mbx_resource_bgra(unsigned char *out,const unsigned char *in,unsigned bytes){
 for(unsigned i=0;i<bytes;i+=4){unsigned char red=in[i],green=in[i+1],blue=in[i+2],alpha=in[i+3];
  out[i]=blue;out[i+1]=green;out[i+2]=red;out[i+3]=alpha;
 }
}
#endif
