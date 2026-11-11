/* SPDX-License-Identifier: MIT. Bounded retained images; no user addresses. */
#ifndef MBX_WINDOW_IMAGES_H
#define MBX_WINDOW_IMAGES_H
#define MBX_WINDOW_SLOTS 16U
#define MBX_WINDOW_EDGE 128U
#define MBX_WINDOW_BASE 0x2c0000U
#define MBX_WINDOW_SLOT_BYTES (65536U+4096U)
#define MBX_WINDOW_ADDRESS(slot) (MBX_WINDOW_BASE+4096U+(slot)*MBX_WINDOW_SLOT_BYTES)
#define MBX_WINDOW_IMAGE_BYTES (128U*128U*4U)
#define MBX_WINDOW_NATIVE_WIDTH 240U
#define MBX_WINDOW_NATIVE_HEIGHT 320U
#define MBX_WINDOW_NATIVE_IMAGE_BYTES (240U*320U*4U)
#define MBX_WINDOW_LEGACY_BYTES (4096U+16U*MBX_WINDOW_SLOT_BYTES)
#define MBX_WINDOW_NATIVE_BYTES (4096U+4U*(MBX_WINDOW_NATIVE_IMAGE_BYTES+4096U)+12U*MBX_WINDOW_SLOT_BYTES)
#define MBX_WINDOW_CLIENT_MASK 0x3fffU
#define MBX_WINDOW_NATIVE_MASK 0xc003U
static inline unsigned mbx_window_capacity(unsigned layout,unsigned slot){
 if(slot>=16||(layout!=1&&layout!=2))return 0;
 return layout==2&&(MBX_WINDOW_NATIVE_MASK&(1U<<slot))?MBX_WINDOW_NATIVE_IMAGE_BYTES:MBX_WINDOW_IMAGE_BYTES;
}
static inline unsigned mbx_window_offset(unsigned layout,unsigned slot){
 if(layout==1)return 4096U+slot*MBX_WINDOW_SLOT_BYTES;
 unsigned large=slot<2?slot:slot<15?2U:3U;
 return 4096U+large*(MBX_WINDOW_NATIVE_IMAGE_BYTES+4096U)+(slot-large)*MBX_WINDOW_SLOT_BYTES;
}
static inline unsigned mbx_window_address(unsigned layout,unsigned slot){return MBX_WINDOW_BASE+mbx_window_offset(layout,slot);}
static inline unsigned mbx_window_width(unsigned layout,unsigned slot){return mbx_window_capacity(layout,slot)==MBX_WINDOW_NATIVE_IMAGE_BYTES?240U:128U;}
static inline unsigned mbx_window_height(unsigned layout,unsigned slot){return mbx_window_capacity(layout,slot)==MBX_WINDOW_NATIVE_IMAGE_BYTES?320U:128U;}
static inline int mbx_window_shape(unsigned layout,unsigned slot,unsigned width,unsigned height){
 if(!mbx_window_capacity(layout,slot))return 0;
 if(width==mbx_window_width(layout,slot)&&height==mbx_window_height(layout,slot))return 1;
 return layout==2&&slot>=14&&width==128&&height==128;
}
struct mbx_window_token { unsigned session,generation,slot; };
struct mbx_window_request { unsigned version,destination; struct mbx_window_token source[2]; };
struct mbx_window_layout {unsigned version,slots,client_mask,native_mask,width,height,stride,arena_bytes;};
#ifdef __cplusplus
static_assert(sizeof(struct mbx_window_layout)==32,"window layout ABI");
#else
_Static_assert(sizeof(struct mbx_window_layout)==32,"window layout ABI");
#endif
static inline int mbx_window_layout_valid(const struct mbx_window_layout *p){
 if(!p||(p->version!=1&&p->version!=2)||p->slots!=16||p->client_mask!=MBX_WINDOW_CLIENT_MASK)return 0;
 return p->native_mask==(p->version==2?3U:0U)&&p->width==(p->version==2?240U:0U)&&p->height==(p->version==2?320U:0U)&&p->stride==(p->version==2?960U:0U)&&p->arena_bytes==(p->version==2?MBX_WINDOW_NATIVE_BYTES:MBX_WINDOW_LEGACY_BYTES);
}
struct mbx_window_state {
 unsigned session,serial,pending,destination,valid,layout,pending_width,pending_height;
 unsigned generation[MBX_WINDOW_SLOTS],width[MBX_WINDOW_SLOTS],height[MBX_WINDOW_SLOTS];
};
static inline int mbx_window_lookup(const struct mbx_window_state *s,struct mbx_window_token t){
 return !s||!s->session||t.session!=s->session||t.slot>=16||!t.generation||
  !(s->valid&(1U<<t.slot))||s->generation[t.slot]!=t.generation?-22:0;
}
static inline int mbx_window_begin_sized(struct mbx_window_state *s,const struct mbx_window_request *r,unsigned sources,unsigned width,unsigned height){
 unsigned i,layout=s&&s->layout?s->layout:1;
 if(!s||!r||!s->session||s->pending||r->version!=layout||!mbx_window_shape(layout,r->destination,width,height)||sources>2||s->serial==~0U)return -22;
 for(i=0;i<2;i++){
  struct mbx_window_token t=r->source[i];
  if(i<sources){if(mbx_window_lookup(s,t)||t.slot==r->destination||s->width[t.slot]!=width||s->height[t.slot]!=height)return -22;}
  else if(t.session||t.generation||t.slot)return -22;
 }
 if(sources==2&&r->source[0].slot==r->source[1].slot)return -22;
 s->valid&=~(1U<<r->destination);s->destination=r->destination;s->pending=1;s->pending_width=width;s->pending_height=height;return 0;
}
static inline int mbx_window_begin(struct mbx_window_state *s,const struct mbx_window_request *r,unsigned sources){return mbx_window_begin_sized(s,r,sources,128,128);}
static inline int mbx_window_complete(struct mbx_window_state *s,int success,struct mbx_window_token *out){
 if(!s||!s->pending||!out)return -22;
 *out=(struct mbx_window_token){0,0,0};s->pending=0;
 if(!success)return -5;
 s->width[s->destination]=s->pending_width;s->height[s->destination]=s->pending_height;
 s->generation[s->destination]=++s->serial;s->valid|=1U<<s->destination;
 *out=(struct mbx_window_token){s->session,s->serial,s->destination};return 0;
}
static inline void mbx_window_invalidate(struct mbx_window_state *s){if(s){s->valid=s->session=s->pending=0;}}
#endif
