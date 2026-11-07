/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../common/mbx_vgp_draw.h"
#include "../experiments/vgp-20261104/common/mbx_gears_fixture.h"
int main(void){
 unsigned short indices[6]={0,1,2,3,4,5};
 struct mbx_vgp_draw d={.program=vgp_gears_program,.uniforms=vgp_gears_constants,.immediates=vgp_gears_constants+96*4,
 .vertices=vgp_gears_vertices,.indices=indices,.instructions=19,.uniform_count=10,.immediate_count=1,.input_count=2,
 .vertex_count=6,.triangle_count=2,.viewport={0x41800000,0x41800000,0x41800000,0xc1800000,0x3f000000,0x3f000000}};
 struct mbx_command c[1024],before[1024];unsigned n=777;
 memset(c,0xa5,sizeof(c));memcpy(before,c,sizeof(c));
 assert(mbx_vgp_draw_encode(&d,c,166,&n)<0&&n==777&&!memcmp(c,before,sizeof(c)));
 indices[5]=6;assert(mbx_vgp_draw_encode(&d,c,1024,&n)<0&&n==777&&!memcmp(c,before,sizeof(c)));indices[5]=5;
 assert(!mbx_vgp_draw_encode(&d,c,1024,&n)&&n==167);
 assert(!memcmp(c+n,before+n,sizeof(c)-n*sizeof(*c)));
 assert(c[0].value==0x90000012&&c[39].value==0x8000ffff&&c[42].value==0x01001200);
 assert(c[56].value==0xa0000009&&c[97].value==0xa0600060);
 for(unsigned t=0;t<2;++t){unsigned a=109+t*29;assert(c[a+3].value==0x34);for(unsigned j=0;j<21;++j)assert(c[a+7+j].value==vgp_gears_vertices[t*24+(j/7)*8+j%7]);}
 assert(!mbx_vgp_frame_begin(c,1024,&n)&&n==59);assert(!mbx_vgp_frame_end(c,1,&n)&&n==1);
 puts("PASS raw Mesa draw: bounded indices, exact shader/vertex payload, compact uniforms, no CPU transform");
}
