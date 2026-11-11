/* SPDX-License-Identifier: MIT */
#ifndef MBX_TEMPLATE_UPDATE_H
#define MBX_TEMPLATE_UPDATE_H
#ifndef MBX_VGP_WIRE_H
#include "mbx_vgp_wire.h"
#endif
#include "mbx_wire_resources.h"
/* Compare canonical complete frames, including immutable resource contents.
 * Return 1 for a bounded dynamic update, 0 for full replacement. The caller
 * retains the snapshot only after successful driver upload/identity query.
 * No hashes, pointer identity, or inferred GPU addresses establish equality. */
static inline int mbx_template_update(const void *snapshot,unsigned old_bytes,
 const void *frame,unsigned bytes,unsigned generation,void *output,unsigned capacity,unsigned *written)
{
 const unsigned char *old=snapshot,*raw=frame;
 struct mbx_wire_resources resources,prior;
 unsigned at,total=32,i;
 const struct mbx_vgp_wire_frame *f=frame;
 if(!old||!raw||!output||!written||!generation||bytes!=old_bytes||bytes<48||
    bytes>MBX_VGP_WIRE_MAX_BYTES||((unsigned long)raw&3)||((unsigned long)old&3)||
    ((unsigned long)output&3)||mbx_wire_resources_parse(raw,bytes,&resources)||
    mbx_wire_resources_parse(old,bytes,&prior)||f->draws>MBX_VGP_WIRE_MAX_DRAWS||
    resources.draw_offset!=prior.draw_offset||memcmp(raw,old,resources.draw_offset))return 0;
 at=resources.draw_offset;
 for(i=0;i<f->draws;++i){
  if(bytes-at<64)return 0;
  const struct mbx_vgp_wire_draw *d=(const void *)(raw+at),*p=(const void *)(old+at);
  unsigned uniforms=4*d->uniforms,offset=64+8*d->instructions,tail=offset+4*uniforms,j;
  if(!d->instructions||d->instructions>128||d->uniforms>83||d->bytes<tail||d->bytes>bytes-at||
     memcmp(d,p,36)||d->reserved!=p->reserved||memcmp(raw+at+64,old+at+64,offset-64)||
     memcmp(raw+at+tail,old+at+tail,d->bytes-tail))return 0;
  const unsigned *u=(const void *)(raw+at+offset);
  for(j=0;j<6;++j)if((d->viewport[j]&0x7f800000U)==0x7f800000U)return 0;
  for(j=0;j<uniforms;++j)if((u[j]&0x7f800000U)==0x7f800000U)return 0;
  if(d->reserved&128U){
   if(uniforms<4||memcmp(u+uniforms-4,old+at+tail-16,16))return 0;
  }
  if(total>MBX_VGP_UPDATE_MAX_BYTES-24-4*uniforms)return 0;
  total+=24+4*uniforms;at+=d->bytes;
 }
 if(at!=bytes||total>capacity)return 0;
 struct mbx_vgp_wire_update *h=output;
 *h=(struct mbx_vgp_wire_update){.magic=MBX_VGP_UPDATE_MAGIC,.version=1,
  .bytes=total,.draws=f->draws,.generation=generation};
 unsigned char *dst=(void *)(h+1);at=resources.draw_offset;
 for(i=0;i<f->draws;++i){
  const struct mbx_vgp_wire_draw *d=(const void *)(raw+at);
  memcpy(dst,d->viewport,24);dst+=24;
  memcpy(dst,raw+at+64+8*d->instructions,16*d->uniforms);dst+=16*d->uniforms;at+=d->bytes;
 }
 *written=total;return 1;
}
#endif
