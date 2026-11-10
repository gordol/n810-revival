/* SPDX-License-Identifier: MIT. Initial transfer only; output stays on GPU. */
#ifndef MBX_WINDOW_CHANNELS_WIRE_H
#define MBX_WINDOW_CHANNELS_WIRE_H
#include "window_checkpoint.h"
#include "linear_resource.h"
#include "mbx_window_export.h"
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
