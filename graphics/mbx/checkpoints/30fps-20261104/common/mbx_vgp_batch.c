/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_batch.h"
#include "mbx_vgp_transform.h"
static int mbx_vgp_finite(unsigned v){return (v&0x7f800000U)!=0x7f800000U;}
int mbx_encode_vgp_batch(const struct mbx_vgp_position *positions,unsigned triangles,
 const unsigned matrix[16],const unsigned rgba[4],struct mbx_command *commands,
 unsigned capacity,unsigned *written)
{
 unsigned program[16],i,j,k,at=0,needed;
 if(!positions||!matrix||!rgba||!commands||!written||!triangles||triangles>MBX_MAX_BATCH_TRIANGLES)return -22;
 needed=MBX_VGP_BATCH_FIXED_COMMANDS+MBX_VGP_BATCH_TRIANGLE_COMMANDS*triangles;
 if(capacity<needed)return -22;
 for(i=0;i<16;++i)if(!mbx_vgp_finite(matrix[i]))return -22;
 for(i=0;i<4;++i)if(!mbx_vgp_finite(rgba[i]))return -22;
 for(i=0;i<triangles*3;++i)for(j=0;j<4;++j)if(!mbx_vgp_finite(positions[i].xyzw[j]))return -22;
 if(mbx_vgp_transform(0,15,16,program,16)!=8)return -22;
#define EMIT(value) do{commands[at++]=(struct mbx_command){MBX_FIFO,(value)};}while(0)
 EMIT(0x10000010U);EMIT(0);
 EMIT(0x90000007U);for(i=0;i<16;++i)EMIT(program[i]);
 EMIT(0x8000ffffU);
 /* Stage2 is the normal position stage. The high field is observed on the
  * unlit matrix path, not inferred from the special pass-through descriptor.
  * Physical dispatch and surrounding context remain acceptance requirements. */
 for(i=0;i<16;++i)EMIT(i==2?0x01000700U:0xf0000000U);
 EMIT(0xa0000003U);for(i=0;i<16;++i)EMIT(matrix[i]);
 EMIT(0xa00f000fU);for(i=0;i<4;++i)EMIT(rgba[i]);
 EMIT(0xa0100011U);
 EMIT(0);EMIT(0);EMIT(0x3f800000U);EMIT(0x3f800000U);
 EMIT(0);EMIT(0);EMIT(0xbf800000U);EMIT(0x3f800000U);
 /* The normal context startup unconditionally supplies shared TA packing
  * constants (reference 804b3f34..804b3fa4). Keep the already verified
  * pass-through values for this isolated dispatch experiment. */
 EMIT(0xa0530054U);
 EMIT(0);EMIT(0);EMIT(0x3f800000U);EMIT(0);
 EMIT(0x40e00000U);EMIT(0x3f808084U);EMIT(0x40e00000U);EMIT(0x40e00000U);
 EMIT(0xa0660066U);for(i=0;i<4;++i)EMIT(0x00800000U);
 EMIT(0xa0a600a8U);for(i=0;i<12;++i)EMIT(i%5U==0?0x3f800000U:0);
 EMIT(0xa0a900abU);for(i=0;i<12;++i)EMIT(i%5U==0?0x40e00000U:0);
 /* State bit7 uploads the six viewport scalars, in offset/scale pairs.
  * Normal clip-space geometry requires these even without a viewport shader.
  * 804b62a0..b4 emits ctx394..3a8; 804aab54..c8 defines XY and
  * 804aadd4..ec defines Z. Offscreen viewport is exactly32x32. */
 EMIT(0x10000080U);
 EMIT(0x41800000U);EMIT(0x41800000U);
 EMIT(0x41800000U);EMIT(0xc1800000U);
 EMIT(0x3f000000U);EMIT(0x3f000000U);
 for(i=0;i<triangles;++i){
  EMIT(0x10000063U);EMIT(0x22200200U);EMIT(0xe0000000U);
  /* ctx118 uses component counts per input nibble (804b2bf8..2c00).
   * Four floats are streamed, so position declares4, not special helper3. */
  EMIT(4);EMIT(0);EMIT(0x40000000U);EMIT(0x70020004U);
  for(j=0;j<3;++j)for(k=0;k<4;++k)EMIT(positions[i*3+j].xyzw[k]);
  commands[at++]=(struct mbx_command){MBX_POLYGON_CONTROL,1};
 }
 EMIT(0xf0000000U);
#undef EMIT
 *written=at;return 0;
}
