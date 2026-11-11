/* SPDX-License-Identifier: MIT
 * Pure ownership bookkeeping for a private three-image GPU reuse candidate.
 * No hardware addresses, allocation, MMIO or DMA operations are performed.
 * Caller holds the exclusive service mutex and supplies a non-reused session.
 */
#ifndef MBX_SURFACE_SLOTS_H
#define MBX_SURFACE_SLOTS_H
struct mbx_surface_token { unsigned session, generation, slot; };
struct mbx_surface_slot { unsigned generation, width, height, valid; };
struct mbx_surface_slots {
 unsigned session, serial, pending, destination, source;
 struct mbx_surface_slot slot[3];
};
static int mbx_surface_slots_open(struct mbx_surface_slots *s,unsigned session) {
 if(!s||!session)return -22;
 *s=(struct mbx_surface_slots){.session=session};return 0;
}
static int mbx_surface_slots_lookup(const struct mbx_surface_slots *s,
 const struct mbx_surface_token *t,unsigned width,unsigned height) {
 if(!s||!t||s->pending||!s->session||t->session!=s->session||t->slot>=3||!t->generation)return -22;
 const struct mbx_surface_slot *p=&s->slot[t->slot];
 return p->valid&&p->generation==t->generation&&p->width==width&&p->height==height?0:-22;
}
/* Validate everything before invalidating the destination. First operation is
 * a clear; subsequent operations may sample only a completed other image.
 * A render failure invalidates the destination; it never publishes a token.
 */
static int mbx_surface_slots_begin(struct mbx_surface_slots *s,unsigned destination,
 unsigned width,unsigned height,const struct mbx_surface_token *source) {
 if(!s||!s->session||s->pending||destination>=3||width!=240||height!=320)return -22;
 if(s->serial==~0U)return -75;
 if(source&&(source->slot==destination||mbx_surface_slots_lookup(s,source,width,height)))return -22;
 s->slot[destination].valid=0;
 s->slot[destination].width=width;s->slot[destination].height=height;
 s->destination=destination;s->source=source?source->slot:3;s->pending=1;return 0;
}
static int mbx_surface_slots_complete(struct mbx_surface_slots *s,int success,
 struct mbx_surface_token *out) {
 if(!s||!s->pending||!out)return -22;
 *out=(struct mbx_surface_token){0};
 struct mbx_surface_slot *p=&s->slot[s->destination];
 s->pending=0;
 if(!success){p->valid=0;return -5;}
 p->generation=++s->serial;p->valid=1;
 *out=(struct mbx_surface_token){s->session,p->generation,s->destination};return 0;
}
/* Retained hardware fault or session teardown invalidates every reference. */
static void mbx_surface_slots_invalidate(struct mbx_surface_slots *s) {
 if(s){s->session=0;s->pending=0;s->slot[0].valid=s->slot[1].valid=s->slot[2].valid=0;}
}
#endif
