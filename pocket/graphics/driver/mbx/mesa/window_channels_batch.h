/* SPDX-License-Identifier: MIT. Initial upload packing, no CPU composition. */
#ifndef MBX_WINDOW_CHANNELS_BATCH_H
#define MBX_WINDOW_CHANNELS_BATCH_H
#include "window_channels_wire.h"
struct mbx_window_upload_item {struct mbx_linear_source source,mask;unsigned dx,dy,mode;};
static int mbx_window_channels_batch_pack(const struct mbx_window_upload_item *items,
 unsigned count,void *packet,unsigned capacity,unsigned *bytes){
 const unsigned plane=128U*128U*4U,total=80U+2U*plane;
 if(!items||!count||count>MBX_WINDOW_CHANNEL_BATCH_MAX||!packet||!bytes||capacity<total)return -22;
 uintptr_t dst=(uintptr_t)packet,list=(uintptr_t)items;
 size_t list_bytes=count*sizeof(*items);
 if(dst>UINTPTR_MAX-total||list>UINTPTR_MAX-list_bytes||
    !(dst+total<=list||list+list_bytes<=dst))return -22;
 for(unsigned i=0;i<count;i++){
  const struct mbx_window_upload_item *item=items+i;
  unsigned w=item->source.width,h=item->source.height;
  if(!w||!h||w>128||h>128||item->mask.width!=w||item->mask.height!=h||
     item->dx>128-w||item->dy>128-h||item->mode>2)return -22;
  for(unsigned j=0;j<i;j++)if(item->dx<items[j].dx+items[j].source.width&&
     items[j].dx<item->dx+w&&item->dy<items[j].dy+items[j].source.height&&
     items[j].dy<item->dy+h)return -22;
  const struct mbx_linear_source *images[2]={&item->source,&item->mask};
  for(unsigned j=0;j<2;j++){
   const struct mbx_linear_source *s=images[j];uintptr_t src=(uintptr_t)s->data;
   if(!s->data||s->rgba>1||s->opaque||s->repeat||s->stride<w*4U||s->bytes<w*4U||
      (h-1)>(s->bytes-w*4U)/s->stride||src>UINTPTR_MAX-s->bytes||
      !(dst+total<=src||src+s->bytes<=dst))return -22;
  }
  if(item->mode==2)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
   const struct mbx_linear_source *s=&item->mask;
   unsigned red=s->data[(size_t)y*s->stride+4*x+(s->rgba?0:2)];if(red&&red!=255)return -95;
  }
 }
 /* Every descriptor, binary-mask sample and overlap is checked before writes. */
 unsigned header[20]={0x3156474dU,10,total,0,128,128,0,0,0,0,0x3f800000U,0,1,2*plane,0,0,9,2*plane,0,8};
 unsigned char *out=packet;memcpy(out,header,80);memset(out+80,0,2*plane);
 for(unsigned i=0;i<count;i++)for(unsigned j=0;j<2;j++){
  const struct mbx_window_upload_item *item=items+i;
  const struct mbx_linear_source *s=j?&item->mask:&item->source;
  for(unsigned y=0;y<s->height;y++)for(unsigned x=0;x<s->width;x++){
   const unsigned char *in=s->data+(size_t)y*s->stride+4*x;
   unsigned char *pixel=out+80+j*plane+((item->dy+y)*128+item->dx+x)*4;
   pixel[0]=in[s->rgba?2:0];pixel[1]=in[1];pixel[2]=in[s->rgba?0:2];
   pixel[3]=in[j&&item->mode?(s->rgba?0:2):3];
  }
 }
 *bytes=total;return 0;
}
#endif
