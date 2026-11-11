/* SPDX-License-Identifier: MIT
 * Private rendered-image cache ABI and ownership state. Addresses never cross
 * this interface. The service mutex serializes all state transitions. */
#ifndef MBX_WINDOW_IMAGES_H
#define MBX_WINDOW_IMAGES_H
#define MBX_WINDOW_SLOTS 16U
#define MBX_WINDOW_EDGE 128U
#define MBX_WINDOW_BASE 0x2c0000U
#define MBX_WINDOW_SLOT_BYTES (65536U+4096U)
#define MBX_WINDOW_ADDRESS(slot) (MBX_WINDOW_BASE+4096U+(slot)*MBX_WINDOW_SLOT_BYTES)
#define MBX_WINDOW_IMAGE_BYTES (128U*128U*4U)
struct mbx_window_token { unsigned session,generation,slot; };
struct mbx_window_request { unsigned version,destination; struct mbx_window_token source[2]; };
struct mbx_window_state {
 unsigned session,serial,pending,destination,valid;
 unsigned generation[MBX_WINDOW_SLOTS];
};
static inline int mbx_window_lookup(const struct mbx_window_state *s,struct mbx_window_token t){
 return !s||!s->session||t.session!=s->session||t.slot>=MBX_WINDOW_SLOTS||!t.generation||
  !(s->valid&(1U<<t.slot))||s->generation[t.slot]!=t.generation?-22:0;
}
static inline int mbx_window_begin(struct mbx_window_state *s,const struct mbx_window_request *r,unsigned sources){
 unsigned i;
 if(!s||!r||!s->session||s->pending||r->version!=1||r->destination>=MBX_WINDOW_SLOTS||sources>2||s->serial==~0U)return -22;
 for(i=0;i<2;i++){
  struct mbx_window_token t=r->source[i];
  if(i<sources){if(mbx_window_lookup(s,t)||t.slot==r->destination)return -22;}
  else if(t.session||t.generation||t.slot)return -22;
 }
 if(sources==2&&r->source[0].slot==r->source[1].slot)return -22;
 s->valid&=~(1U<<r->destination);s->destination=r->destination;s->pending=1;return 0;
}
static inline int mbx_window_complete(struct mbx_window_state *s,int success,struct mbx_window_token *out){
 if(!s||!s->pending||!out)return -22;
 *out=(struct mbx_window_token){0};s->pending=0;
 if(!success)return -5;
 s->generation[s->destination]=++s->serial;s->valid|=1U<<s->destination;
 *out=(struct mbx_window_token){s->session,s->serial,s->destination};return 0;
}
static inline void mbx_window_invalidate(struct mbx_window_state *s){if(s){s->valid=s->session=s->pending=0;}}
#endif
