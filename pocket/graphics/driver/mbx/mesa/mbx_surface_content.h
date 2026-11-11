/* SPDX-License-Identifier: MIT. Resource lifetime, independent of replay cache. */
#ifndef MBX_SURFACE_CONTENT_H
#define MBX_SURFACE_CONTENT_H
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
struct mbx_surface_content {
 uint64_t generation,completed_generation;
 uint64_t creates,clears,draws,binds,evictions,restores,external_writes;
 unsigned id;
 unsigned completed_timestamp,initialized,complete,external_only;
};
static inline void mbx_content_create(struct mbx_surface_content *s){s->creates=1;}
static inline void mbx_content_clear(struct mbx_surface_content *s){++s->clears;++s->generation;s->initialized=1;s->complete=0;s->external_only=0;}
static inline void mbx_content_draw(struct mbx_surface_content *s){++s->draws;++s->generation;s->complete=0;}
static inline void mbx_content_complete(struct mbx_surface_content *s,unsigned timestamp){s->completed_generation=s->generation;s->completed_timestamp=timestamp;s->complete=s->initialized;}
static inline void mbx_content_external_write(struct mbx_surface_content *s){++s->external_writes;++s->generation;s->initialized=s->complete=0;}
static inline int mbx_content_ready(const struct mbx_surface_content *s,unsigned timestamp){return s->initialized&&s->complete&&s->generation==s->completed_generation&&s->completed_timestamp==timestamp;}
static inline void mbx_content_trace(const struct mbx_surface_content *s,const void *target,const char *event){
 if(!getenv("N810_MBX_SURFACE_DIAGNOSTICS"))return;
 fprintf(stderr,"MBX_SURFACE event=%s target=%p id=%u generation=%llu completed=%llu timestamp=%u initialized=%u valid=%u creates=%llu clears=%llu draws=%llu binds=%llu evictions=%llu restores=%llu external_writes=%llu\n",event,target,s->id,(unsigned long long)s->generation,(unsigned long long)s->completed_generation,s->completed_timestamp,s->initialized,s->complete,(unsigned long long)s->creates,(unsigned long long)s->clears,(unsigned long long)s->draws,(unsigned long long)s->binds,(unsigned long long)s->evictions,(unsigned long long)s->restores,(unsigned long long)s->external_writes);
}
#endif
