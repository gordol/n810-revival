/* SPDX-License-Identifier: MIT */
#ifndef MBX_LINEAR_CACHE_H
#define MBX_LINEAR_CACHE_H
#include <stddef.h>
#include <stdint.h>
#include <string.h>
struct pipe_resource;
struct mbx_linear_entry {struct pipe_resource *resource;unsigned char *upload;size_t capacity;unsigned timestamp,flags,crop[4];uint64_t used,wire_epoch;unsigned wire_index;};
static inline int mbx_linear_wire_matches(const struct mbx_linear_entry *e,uint64_t epoch){return epoch&&e->wire_epoch==epoch;}
static inline int mbx_linear_matches(const struct mbx_linear_entry *e,const struct pipe_resource *resource,unsigned timestamp,unsigned flags,const unsigned crop[4]){
 return e->resource==resource&&e->timestamp==timestamp&&e->flags==flags&&!memcmp(e->crop,crop,4*sizeof(*crop));
}
static inline struct mbx_linear_entry *mbx_linear_choose(struct mbx_linear_entry entries[5],const struct pipe_resource *resource,unsigned timestamp,unsigned flags,const unsigned crop[4],size_t bytes){
 struct mbx_linear_entry *entry=entries+(bytes>131072?4:0);
 if(bytes<=131072)for(unsigned i=0;i<4;i++){
  struct mbx_linear_entry *e=entries+i;
  if(mbx_linear_matches(e,resource,timestamp,flags,crop))return e;
  if(e->used<entry->used)entry=e;
 }
 return entry;
}
#endif
