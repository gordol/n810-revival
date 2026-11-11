/* SPDX-License-Identifier: MIT
 * One session-owned linear texture arena. Tokens name verified contents, never
 * GPU addresses. Canonical frame validation remains mandatory after expansion.
 */
#ifndef MBX_TEXTURE_RESIDENT_H
#define MBX_TEXTURE_RESIDENT_H
#include "mbx_wire_resources.h"
#define MBX_TEXTURE_REF_MAGIC 0x3152544dU
struct mbx_texture_ref { unsigned magic,version,bytes,generation,frame_bytes,data_offset,texture_bytes,session; };
struct mbx_texture_resident {
 unsigned generation,valid,bytes,prefix,session;
 unsigned char descriptors[1040]; /* table + 64 descriptors */
 unsigned char *data;
};
static inline int mbx_texture_resident_eligible(const struct mbx_wire_resources *r){
 if(!r||!r->count||!r->bytes||r->data_offset<80||r->data_offset>1088)return 0;
 unsigned i;
 for(i=0;i<r->count;i++)if(r->item[i].version!=8&&r->item[i].version!=12&&r->item[i].version!=13&&r->item[i].version!=14)return 0;
 return 1;
}
static inline int mbx_texture_resident_matches(const struct mbx_texture_resident *s,const void *frame,const struct mbx_wire_resources *r){
 const unsigned char *p=frame;
 return s&&s->valid&&s->data&&mbx_texture_resident_eligible(r)&&s->bytes==r->bytes&&s->prefix==r->data_offset&&
  !memcmp(s->descriptors,p+48,r->data_offset-48)&&!memcmp(s->data,p+r->data_offset,r->bytes);
}
/* Commit only after the GPU has completed and texture/guard checks passed. */
static inline int mbx_texture_resident_commit(struct mbx_texture_resident *s,const void *frame,const struct mbx_wire_resources *r){
 const unsigned char *p=frame;
 if(!s||!s->data||!mbx_texture_resident_eligible(r)||s->generation==~0U)return -22;
 s->valid=0;memcpy(s->data,p+r->data_offset,r->bytes);memcpy(s->descriptors,p+48,r->data_offset-48);
 s->bytes=r->bytes;s->prefix=r->data_offset;++s->generation;s->valid=1;return 0;
}
static inline int mbx_texture_ref_pack(const struct mbx_texture_resident *s,const void *frame,unsigned bytes,void *output,unsigned capacity,unsigned *written){
 struct mbx_wire_resources r;const unsigned char *p=frame;unsigned char *o=output;
 if(!output||!written||mbx_wire_resources_parse(frame,bytes,&r)||!mbx_texture_resident_matches(s,frame,&r))return -22;
 unsigned n=32+bytes-r.bytes;if(n>capacity)return -22;
 struct mbx_texture_ref h={MBX_TEXTURE_REF_MAGIC,1,n,s->generation,bytes,r.data_offset,r.bytes,s->session};
 memcpy(o,&h,32);memcpy(o+32,p,r.data_offset);memcpy(o+32+r.data_offset,p+r.draw_offset,bytes-r.draw_offset);*written=n;return 0;
}
/* Reuse any subset/reordering of the verified arena. Draw resource indices
 * are remapped to its stable descriptor order; payload and shader data stay
 * byte-identical. No GPU ABI/address change and no texture copy on this path.
 * Validate the complete draw walk before writing output. */
static inline int mbx_texture_ref_pack_subset(const struct mbx_texture_resident *s,const void *frame,unsigned bytes,void *output,unsigned capacity,unsigned *written){
 struct mbx_wire_resources r;unsigned header[12],table[4],map[64],i,j,at,n,draw_bytes,frame_bytes;
 const unsigned char *p=frame;unsigned char *o=output;
 if(!s||!s->valid||!s->data||!frame||!output||!written||s->prefix<80||s->prefix>1088||s->bytes>MBX_WIRE_LINEAR_PAYLOAD||
    mbx_wire_resources_parse(frame,bytes,&r))return -22;
 memcpy(header,p,48);memcpy(table,s->descriptors,16);
 if((header[1]!=9&&header[1]!=10)||header[11]!=5||header[3]>256||!table[0]||table[0]>64||s->prefix!=64+16*table[0]||table[1]!=s->bytes)return -22;
 for(i=0;i<r.count;i++){
  const struct mbx_wire_resource *a=r.item+i;
  if(a->version!=8&&a->version!=12&&a->version!=13&&a->version!=14)return -22;
  for(j=0;j<table[0];j++){
   struct mbx_wire_resource b;memcpy(&b,s->descriptors+16+16*j,16);
   if(b.version==13||b.version==14){
    if(b.offset>=MBX_WINDOW_SLOTS||!b.bytes||!b.reserved)return -22;
    if(a->version==b.version&&a->bytes==b.bytes&&a->offset==b.offset&&a->reserved==b.reserved)break;
   }else{
    if(b.offset>s->bytes||b.bytes>s->bytes-b.offset)return -22;
    if(a->version!=13&&a->version!=14&&a->version==b.version&&a->bytes==b.bytes&&a->reserved==b.reserved&&
       !memcmp(p+r.data_offset+a->offset,s->data+b.offset,a->bytes))break;
   }
  }
  if(j==table[0])return -22;
  map[i]=j;
 }
 at=r.draw_offset;
 for(i=0;i<header[3];i++){
  unsigned size,flags,index;if(bytes-at<64)return -22;
  memcpy(&size,p+at,4);memcpy(&flags,p+at+60,4);index=mbx_resource_index_decode(flags);
  if(size<64||(size&3)||size>bytes-at||((flags&4)?index>=r.count:index!=0))return -22;
  at+=size;
 }
 if(at!=bytes)return -22;
 draw_bytes=bytes-r.draw_offset;
 if(s->prefix+s->bytes>1048576U||draw_bytes>1048576U-s->prefix-s->bytes)return -22;
 frame_bytes=s->prefix+s->bytes+draw_bytes;n=32+s->prefix+draw_bytes;
 if(n>capacity)return -22;
 {unsigned long a=(unsigned long)p,b=(unsigned long)o;if((a>=b&&a-b<n)||(b>=a&&b-a<bytes))return -22;}
 struct mbx_texture_ref h={MBX_TEXTURE_REF_MAGIC,1,n,s->generation,frame_bytes,s->prefix,s->bytes,s->session};
 header[2]=frame_bytes;memcpy(o,&h,32);memcpy(o+32,header,48);memcpy(o+80,s->descriptors,s->prefix-48);
 memcpy(o+32+s->prefix,p+r.draw_offset,draw_bytes);at=32+s->prefix;
 for(i=0;i<header[3];i++){
  unsigned size,flags;memcpy(&size,o+at,4);memcpy(&flags,o+at+60,4);
  if(flags&4){flags=(flags&~mbx_resource_index_flags(63))|mbx_resource_index_flags(map[mbx_resource_index_decode(flags)]);memcpy(o+at+60,&flags,4);}
  at+=size;
 }
 *written=n;return 0;
}
/* In-place expansion: compact draw data moves before cached texture insertion.
 * Every size/token/descriptor condition is checked before mutation. */
static inline int mbx_texture_ref_validate(const struct mbx_texture_resident *s,const void *prefix,unsigned prefix_bytes,unsigned bytes,unsigned capacity){
 const unsigned char *p=prefix;struct mbx_texture_ref h;unsigned frame[12];
 if(!s||!s->valid||!s->data||!prefix||prefix_bytes<80)return -22;
 memcpy(&h,p,32);memcpy(frame,p+32,48);
 if(h.data_offset>1088||prefix_bytes<32+h.data_offset)return -22;
 if(h.magic!=MBX_TEXTURE_REF_MAGIC||h.version!=1||h.session!=s->session||h.bytes!=bytes||h.generation!=s->generation||
    h.frame_bytes>capacity||h.data_offset!=s->prefix||h.texture_bytes!=s->bytes||
    h.data_offset<80||h.data_offset>1088||h.frame_bytes<h.data_offset||h.texture_bytes>h.frame_bytes-h.data_offset||
    bytes!=32+h.frame_bytes-h.texture_bytes||frame[0]!=0x3156474dU||frame[2]!=h.frame_bytes||
    memcmp(p+32+48,s->descriptors,h.data_offset-48))return -22;
 return 0;
}
static inline int mbx_texture_ref_expand(const struct mbx_texture_resident *s,void *buffer,unsigned bytes,unsigned capacity,unsigned *expanded){
 unsigned char *p=buffer;struct mbx_texture_ref h;
 if(!expanded||mbx_texture_ref_validate(s,buffer,bytes,bytes,capacity))return -22;
 memcpy(&h,p,32);
 memmove(p+h.data_offset+h.texture_bytes,p+32+h.data_offset,h.frame_bytes-h.data_offset-h.texture_bytes);
 memmove(p,p+32,h.data_offset);memcpy(p+h.data_offset,s->data,h.texture_bytes);*expanded=h.frame_bytes;return 0;
}
#endif
