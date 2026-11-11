/* SPDX-License-Identifier: MIT */
#include "separate_blend.h"
#include "draw/mbx_vgp_wire.h"
#include "mbx_wire_resources.h"
#include <stdint.h>
#include <string.h>
static int overlap(const void *a,const void *b,unsigned size){
 uintptr_t x=(uintptr_t)a,y=(uintptr_t)b;
 return x<=y?y-x<size:x-y<size;
}
int mbx_split_separate_blend(const void *source,unsigned bytes,
 void *rgb,void *alpha,unsigned capacity,unsigned *separate_draws)
{
 struct mbx_vgp_wire_frame f;struct mbx_wire_resources resources;
 unsigned offsets[MBX_VGP_WIRE_MAX_DRAWS],flags[MBX_VGP_WIRE_MAX_DRAWS],at,count=0;
 if(!source||!separate_draws||bytes<64||bytes>MBX_VGP_WIRE_MAX_BYTES||
    ((rgb==0)!=(alpha==0))||(rgb&&(capacity<bytes||overlap(source,rgb,bytes)||overlap(source,alpha,bytes)||overlap(rgb,alpha,bytes))))return -22;
 memcpy(&f,source,sizeof(f));
 if(f.magic!=MBX_VGP_WIRE_MAGIC||f.version!=10||f.bytes!=bytes||(f.clear_buffers!=5&&f.clear_buffers!=0)||f.draws>MBX_VGP_WIRE_MAX_DRAWS||
    f.width<16||f.width>400||f.height<16||f.height>400||(f.width&15)||((f.height&15)&&!(f.width==240&&f.height==241))||
    (uint64_t)f.width*f.height*4>320000||mbx_wire_resources_parse(source,bytes,&resources))return -22;
 at=resources.draw_offset;
 for(unsigned i=0;i<f.draws;++i){
  struct mbx_vgp_wire_draw d;
  if(at>bytes||bytes-at<sizeof(d))return -22;
  memcpy(&d,(const unsigned char*)source+at,sizeof(d));
  uint64_t payload=64ULL+8ULL*d.instructions+16ULL*(d.uniforms+(uint64_t)d.immediates+(uint64_t)d.inputs*d.vertices)+((6ULL*d.triangles+3)&~3ULL);
  if(!d.instructions||d.instructions>128||d.uniforms>83||d.immediates>6||d.inputs<1||d.inputs>3||
     !d.vertices||d.vertices>4096||!d.triangles||d.triangles>256||d.bytes!=payload||d.bytes>bytes-at||
     d.reserved&~262143U||!(d.reserved&64U))return -22;
  unsigned annotations=d.reserved&(MBX_ALPHA_ADDITIVE_ANNOTATION|MBX_ALPHA_OVER_ANNOTATION|MBX_ALPHA_COPY_ANNOTATION);
  if(annotations){
   if(annotations&(annotations-1U))return -22;
   if(annotations==MBX_ALPHA_COPY_ANNOTATION){if(!(d.reserved&MBX_PREMULTIPLY_COPY_FLAG)||(d.reserved&15U))return -22;}
   else if((d.reserved&3U)!=1U||(d.reserved&MBX_PREMULTIPLY_COPY_FLAG))return -22;
   ++count;
  }
  if((d.reserved&MBX_PREMULTIPLY_COPY_FLAG)&&(!(d.reserved&64U)||(d.reserved&15U)))return -22;
  offsets[i]=at;flags[i]=d.reserved;at+=d.bytes;
 }
 if(at!=bytes||(count&&f.width>320))return -22;
 if(!rgb){*separate_draws=count;return 0;}
 /* Every check precedes output writes. Other draw state/resources are exact. */
 memcpy(rgb,source,bytes);memcpy(alpha,source,bytes);
 for(unsigned i=0;i<f.draws;++i){
  unsigned r=flags[i]&~(MBX_ALPHA_ADDITIVE_ANNOTATION|MBX_ALPHA_OVER_ANNOTATION|MBX_ALPHA_COPY_ANNOTATION);
  unsigned a=(flags[i]&MBX_ALPHA_COPY_ANNOTATION)?(r&~MBX_PREMULTIPLY_COPY_FLAG):(flags[i]&MBX_ALPHA_ADDITIVE_ANNOTATION)?((r&~3U)|3U):(flags[i]&MBX_ALPHA_OVER_ANNOTATION)?((r&~3U)|2U):r;
  memcpy((unsigned char*)rgb+offsets[i]+60,&r,4);
  memcpy((unsigned char*)alpha+offsets[i]+60,&a,4);
 }
 *separate_draws=count;return 0;
}
