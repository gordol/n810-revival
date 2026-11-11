/* SPDX-License-Identifier: MIT. Initial transfer only; output stays on GPU. */
#ifndef MBX_WINDOW_CHANNELS_WIRE_H
#define MBX_WINDOW_CHANNELS_WIRE_H
#include <stdint.h>
#include <string.h>
#include "window_checkpoint.h"
#include "linear_resource.h"
#include "mbx_window_export.h"
/* Exact wire-byte admission, including compact halo/stride and packet headers.
 * Dense storage padding must not make the opt-in path upload more bytes. */
static int mbx_window_channels_upload_prefer(unsigned w,unsigned h,unsigned sw,unsigned sh){
 unsigned pitch;size_t payload=mbx_linear_size(w,h,&pitch);
 if(!payload||w>sw||h>sh||!((sw==128&&sh==128)||(sw==240&&sh==320)))return 0;
 size_t dense=80U+(size_t)sw*sh*8U;
 size_t compact=2U*(MBX_WINDOW_CHECKPOINT_BYTES+payload)+80U;
 return dense<=compact;
}
/* Existing resource9: two dense BGRA planes, selected by the GPU channel
 * combiner. Conversion is initial upload only, never CPU alpha composition. */
static int mbx_window_channels_upload_pack(const struct mbx_linear_source *a,
 const struct mbx_linear_source *b,unsigned mode,void *packet,unsigned capacity,
 unsigned sw,unsigned sh,unsigned *bytes){
 if(!a||!b||!packet||!bytes||mode>2||!a->width||!a->height||
    a->width!=b->width||a->height!=b->height||a->width>sw||a->height>sh||
    !((sw==128&&sh==128)||(sw==240&&sh==320)))return -22;
 unsigned plane=sw*sh*4U,total=80+2*plane;
 if(capacity<total)return -22;
 const struct mbx_linear_source *images[2]={a,b};
 for(unsigned i=0;i<2;i++){
  const struct mbx_linear_source *s=images[i];
  if(!s->data||s->rgba>1||s->opaque||s->repeat||s->stride<s->width*4U||
     s->bytes<s->width*4U||(s->height-1)>(s->bytes-s->width*4U)/s->stride)return -22;
  uintptr_t p=(uintptr_t)packet,q=(uintptr_t)s->data;
  if(p>UINTPTR_MAX-total||q>UINTPTR_MAX-s->bytes||
     !(p+total<=q||q+s->bytes<=p))return -22;
 }
 if(mode==2)for(unsigned y=0;y<b->height;y++)for(unsigned x=0;x<b->width;x++){
  unsigned red=b->data[(size_t)y*b->stride+4*x+(b->rgba?0:2)];if(red&&red!=255)return -95;
 }
 unsigned header[20]={0x3156474dU,10,total,0,sw,sh,0,0,0,0,0x3f800000U,0,1,2*plane,0,0,9,2*plane,0,8};
 unsigned char *out=packet;memcpy(out,header,80);memset(out+80,0,2*plane);
 for(unsigned i=0;i<2;i++)for(unsigned y=0;y<a->height;y++)for(unsigned x=0;x<a->width;x++){
  const struct mbx_linear_source *s=images[i];
  const unsigned char *in=s->data+(size_t)y*s->stride+4*x;
  unsigned char *pixel=out+80+i*plane+(y*sw+x)*4;
  pixel[0]=in[s->rgba?2:0];pixel[1]=in[1];pixel[2]=in[s->rgba?0:2];
  pixel[3]=in[i&&mode?(s->rgba?0:2):3];
 }
 *bytes=total;return 0;
}
/* All admission/threshold checks precede writes. Channel view conversion is
 * part of the initial CPU->GPU transfer, never a readback of resident pixels. */
static int mbx_window_channel_pack(const struct mbx_linear_source *s,unsigned mode,
 void *packet,unsigned capacity,unsigned storage_w,unsigned storage_h,unsigned *bytes){
 unsigned pitch;size_t payload;if(!s||!packet||!bytes||mode>2||
  !(payload=mbx_linear_size(s->width,s->height,&pitch))||payload>capacity||MBX_WINDOW_CHECKPOINT_BYTES>capacity-payload||
  !s->width||!s->height||s->width>storage_w||s->height>storage_h||
  !((storage_w==128&&storage_h==128)||(storage_w==240&&storage_h==320))||
  s->rgba>1||s->opaque>1||s->repeat||!s->data||s->stride<s->width*4U||s->bytes<s->width*4U||
  (s->height-1)>(s->bytes-s->width*4U)/s->stride)return -22;
 if(mode==2)for(unsigned y=0;y<s->height;y++)for(unsigned x=0;x<s->width;x++){
  unsigned r=s->data[(size_t)y*s->stride+4*x+(s->rgba?0:2)];if(r&&r!=255)return -95;
 }
 unsigned seed[MBX_WINDOW_CHECKPOINT_BYTES/4];
 if(mbx_window_checkpoint(seed,sizeof seed,(struct mbx_window_token){1,1,storage_w==240?0U:2U},2,storage_w,storage_h))return -22;
 unsigned char *raw=packet;
 if(mbx_linear_pack(s,raw+80,payload))return -22;
 if(mode)for(unsigned i=0;i<payload;i+=4)raw[80+i+3]=raw[80+i+2];
 struct mbx_vgp_wire_frame f=*(const struct mbx_vgp_wire_frame*)seed;f.bytes=MBX_WINDOW_CHECKPOINT_BYTES+payload;
 unsigned table[4]={1,payload,0,0};struct mbx_wire_resource resource={8,payload,0,(s->width<<16)|s->height};
 memcpy(raw,&f,48);memcpy(raw+48,table,16);memcpy(raw+64,&resource,16);
 memcpy(raw+80+payload,seed+20,356);
 struct mbx_vgp_wire_draw *d=(void*)(raw+80+payload);
 unsigned *v=(unsigned*)(d+1)+18+20;
 float right=-1.0f+2.0f*s->width/storage_w,bottom=1.0f-2.0f*s->height/storage_h;
 float u0=1.0f/2048.0f,v0=u0,u1=(s->width+1.0f)/2048.0f,v1=(s->height+1.0f)/2048.0f;
 memcpy(v+8,&right,4);memcpy(v+24,&right,4);memcpy(v+17,&bottom,4);memcpy(v+25,&bottom,4);
 for(unsigned i=0;i<4;i++){memcpy(v+8*i+4,(i&1)?&u1:&u0,4);memcpy(v+8*i+5,(i&2)?&v1:&v0,4);}
 *bytes=f.bytes;return 0;
}
#endif
