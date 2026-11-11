/* SPDX-License-Identifier: MIT */
#ifndef MBX_SURFACE_LEASE_H
#define MBX_SURFACE_LEASE_H
#include "mbx_owned_surface.h"
struct mbx_surface_lease { struct mbx_owned_surface image; unsigned held; };
static int mbx_lease_matches(const struct mbx_surface_lease *s,const struct mbx_owned_surface *p){
 const struct mbx_owned_surface *q=&s->image;
 return s->held&&p->version==1&&p->session==q->session&&p->generation==q->generation&&
 p->slot==q->slot&&p->format==q->format&&p->width==q->width&&p->height==q->height&&
 p->stride==q->stride&&p->bytes==q->bytes&&p->flags==MBX_SURFACE_COMPLETE&&!p->reserved[0]&&!p->reserved[1];
}
static int mbx_lease_sink_valid(const struct mbx_surface_lease *s,const struct mbx_surface_sink *p){
 if(!mbx_lease_matches(s,&p->surface)||!p->address||!p->width||!p->height||p->reverse_rows>1||p->reserved[0]||p->reserved[1])return 0;
 if(p->x>=s->image.width||p->y>=s->image.height||p->width>s->image.width-p->x||p->height>s->image.height-p->y)return 0;
 if(p->width>0x7fffffffU||p->stride<p->width*2U)return 0;
 __u64 end=(__u64)(p->height-1)*p->stride+(__u64)p->width*2;
 return end<=p->capacity&&p->address<=~(__u64)0-end;
}
#endif
