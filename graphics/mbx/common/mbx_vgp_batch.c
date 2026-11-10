/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_batch.h"
#include "mbx_gears_fixture.h"
#include "mbx_vgp_isa.c"
#include "mbx_vgp_draw.c"
int mbx_encode_vgp_batch(const struct mbx_vgp_position *positions,unsigned triangles,
 const unsigned matrix[16],const unsigned rgba[4],struct mbx_command *commands,
 unsigned capacity,unsigned *written)
{
 static const unsigned short indices[6]={0,1,2,3,4,5};
 struct mbx_vgp_draw d={.program=vgp_gears_program,.uniforms=vgp_gears_constants,
  .immediates=vgp_gears_constants+96*4,.vertices=(const unsigned *)positions,.indices=indices,
  .instructions=19,.uniform_count=10,.immediate_count=1,.input_count=2,
  .vertex_count=6,.triangle_count=2,.viewport={0x41000000,0x42800000,0x41000000,0xc2800000,0x3f000000,0x3f000000}};
 unsigned at=0,n;int error;
 (void)matrix;(void)rgba;
 if(triangles!=2||capacity<227||!written)return -22;
 error=mbx_vgp_frame_begin(commands,capacity,&n);if(error)return error;at+=n;
 error=mbx_vgp_draw_encode(&d,commands+at,capacity-at,&n);if(error)return error;at+=n;
 error=mbx_vgp_frame_end(commands+at,capacity-at,&n);if(error)return error;at+=n;
 *written=at;return 0;
}
