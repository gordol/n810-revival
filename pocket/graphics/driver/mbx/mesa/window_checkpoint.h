/* SPDX-License-Identifier: MIT */
#ifndef MBX_WINDOW_CHECKPOINT_H
#define MBX_WINDOW_CHECKPOINT_H
#include "draw/mbx_vgp_wire.h"
#include "draw/mbx_vgp_isa.h"
#include "mbx_wire_resources.h"
static inline int mbx_checkpoint_enabled(const char *value)
{return value&&!strcmp(value,"1");}
/* One full replacement quad samples completed window storage. Both channel
 * replays finish before the final merge replaces that source; no CPU pixels. */
#define MBX_WINDOW_CHECKPOINT_BYTES 436U
static int mbx_window_checkpoint(void *wire,unsigned capacity,
 struct mbx_window_token token,unsigned layout,unsigned width,unsigned height)
{
 unsigned image[MBX_WINDOW_CHECKPOINT_BYTES/4]={0};
 if(!wire||capacity<sizeof image||!token.session||!token.generation||token.slot>=14||
    !mbx_window_shape(layout,token.slot,width,height))return -22;
 struct mbx_vgp_wire_frame *f=(void*)image;
 *f=(struct mbx_vgp_wire_frame){.magic=MBX_VGP_WIRE_MAGIC,.version=10,
  .bytes=sizeof image,.draws=1,.width=width,.height=height,
  .clear_depth=0x3f800000U,.clear_buffers=5};
 image[12]=1;
 struct mbx_wire_resource resource={layout==2?14U:13U,token.generation,token.slot,token.session};
 memcpy(image+16,&resource,sizeof resource);
 struct mbx_vgp_wire_draw *d=(void*)(image+20);
 unsigned halfw=width==240?0x42f00000U:0x42800000U;
 unsigned halfh=height==320?0x43200000U:0x42800000U;
 *d=(struct mbx_vgp_wire_draw){.bytes=356,.instructions=9,.uniforms=5,
  .inputs=2,.vertices=4,.triangles=2,.reserved=4|8|64,
  .viewport={halfw,halfw,halfh,halfh|0x80000000U,0x3f000000U,0x3f000000U}};
 unsigned *p=(void*)(d+1);
 /* mbx_vgp_transform(0,4,112): fixed identity-position/color export,
  * checked word-for-word against the shared compiler in the local test. */
 static const unsigned transform[16]={
  0x00e4e408U,0x4c440000U,0x00e4e408U,0x4c840010U,
  0x00e4e408U,0x4d040020U,0x00e4e408U,0x4e040030U,
  0x0000c601U,0x07c10004U,0x0000e401U,0x03c20003U,
  0x00e4e408U,0x1c467003U,0x00e4e408U,0x1c867013U};
 memcpy(p,transform,sizeof transform);
 struct mbx_vgp_source uv={0,3,0xe4,0};
 if(mbx_vgp_encode(1,3,15,&uv,1,p+16))return -22;
 p+=18;for(unsigned i=0;i<20;i++)p[i]=(i==0||i==5||i==10||i==15||i>=16)?0x3f800000U:0;
 p+=20;
 unsigned u=width==240?0x3df00000U:0x3d800000U;
 unsigned v=height==320?0x3e200000U:0x3d800000U;
 unsigned vertices[32]={
  0xbf800000U,0x3f800000U,0,0x3f800000U, 0,0,0,0x3f800000U,
  0x3f800000U,0x3f800000U,0,0x3f800000U, u,0,0,0x3f800000U,
  0xbf800000U,0xbf800000U,0,0x3f800000U, 0,v,0,0x3f800000U,
  0x3f800000U,0xbf800000U,0,0x3f800000U, u,v,0,0x3f800000U};
 memcpy(p,vertices,sizeof vertices);p+=32;
 unsigned short indices[6]={0,1,2,1,3,2};memcpy(p,indices,sizeof indices);
 memcpy(wire,image,sizeof image);return 0;
}
#endif
