/* SPDX-License-Identifier: MIT
 * Per-context scratch retention; fetched and shaded data never alias.
 * Oversized requests remain ordinary allocations. No global shared storage.
 */
#ifndef DRAW_MBX_BUFFERS_H
#define DRAW_MBX_BUFFERS_H
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
struct mbx_vertex_buffers { void *data[2]; size_t bytes[2]; int enabled; };
static void *mbx_vertex_alloc(struct mbx_vertex_buffers *b,unsigned slot,size_t bytes)
{
 if(!b->enabled)b->enabled=getenv("N810_MBX_REUSE_VERTEX_BUFFERS")&&
   !strcmp(getenv("N810_MBX_REUSE_VERTEX_BUFFERS"),"1")?1:-1;
 if(b->enabled<0||bytes>1024*1024)return malloc(bytes);
 if(slot>=2)abort();
 if(bytes>b->bytes[slot]){
  void *p=malloc(bytes);
  if(!p){fprintf(stderr,"MBX vertex scratch allocation failed\n");abort();}
  free(b->data[slot]);b->data[slot]=p;b->bytes[slot]=bytes;
 }
 return b->data[slot];
}
static void mbx_vertex_release(struct mbx_vertex_buffers *b,void *p)
{ if(p!=b->data[0]&&p!=b->data[1])free(p); }
static void mbx_vertex_buffers_destroy(struct mbx_vertex_buffers *b)
{ free(b->data[0]);free(b->data[1]);memset(b,0,sizeof(*b)); }
#endif
