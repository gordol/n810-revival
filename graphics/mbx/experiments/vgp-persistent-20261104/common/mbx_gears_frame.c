/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_isa.c"
#include "mbx_vgp_draw.c"
#include "mbx_vgp_topology.c"
#include "mbx_gears_frame_fixture.h"
#include "mbx_vgp_transform.h"
static int mbx_encode_gears_frame(struct mbx_command *commands,unsigned capacity,unsigned *written,unsigned clear_only)
{
 unsigned at=0,n,i;int error;
 static unsigned short indices[768];
 if(!commands||!written||capacity<23831)return -22;
 error=mbx_vgp_frame_begin(commands,capacity,&n);if(error)return error;at+=n;
 {
  unsigned program[16];
  static const unsigned uniform[20]={0x3f800000,0,0,0,0,0x3f800000,0,0,
     0,0,0x3f800000,0,0,0,0,0x3f800000,0,0,0,0x3f800000};
  static const unsigned vertices[16]={0xbf800000,0xbf800000,0x3f800000,0x3f800000,
     0x3f800000,0xbf800000,0x3f800000,0x3f800000,
     0xbf800000,0x3f800000,0x3f800000,0x3f800000,
     0x3f800000,0x3f800000,0x3f800000,0x3f800000};
  static const unsigned short clear_indices[6]={0,1,2,1,3,2};
  struct mbx_vgp_draw clear={.program=program,.uniforms=uniform,.vertices=vertices,.indices=clear_indices,
    .instructions=8,.uniform_count=5,.input_count=1,.vertex_count=4,.triangle_count=2,.depth_always=1,
    .viewport={0x43480000,0x43480000,0x43480000,0xc3480000,0x3f000000,0x3f000000}};
  if(mbx_vgp_transform(0,4,112,program,16)!=8)return -22;
  error=mbx_vgp_draw_encode(&clear,commands+at,capacity-at,&n);if(error)return error;at+=n;
 }
 for(i=0;!clear_only&&i<sizeof(gears_draws)/sizeof(gears_draws[0]);++i){
  const struct mbx_gears_draw_fixture *f=gears_draws+i;
  struct mbx_vgp_draw draw=f->draw;
  error=mbx_vgp_topology(f->primitive,f->indices,f->count,f->lengths,f->runs,
                        draw.vertex_count,indices,768,&n);
  if(error)return error;
  if(!n)continue;
  draw.cull_mode=1; /* Verified front-CCW/back-cull with negative Y viewport. */
  draw.indices=indices;draw.triangle_count=n/3;
  error=mbx_vgp_draw_encode(&draw,commands+at,capacity-at,&n);if(error)return error;at+=n;
 }
 error=mbx_vgp_frame_end(commands+at,capacity-at,&n);if(error)return error;at+=n;
 if(at!=(clear_only?162U:23831U))return -22;
 *written=at;return 0;
}
