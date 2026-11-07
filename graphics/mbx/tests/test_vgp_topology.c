/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../common/mbx_vgp_topology.h"
/* Exercise the actual pinned Mesa decomposition template as the oracle.
 * Its point/line paths are irrelevant to the accepted triangle-only subset. */
typedef unsigned short ushort;
enum {PIPE_PRIM_POINTS,PIPE_PRIM_LINES,PIPE_PRIM_LINE_LOOP,PIPE_PRIM_LINE_STRIP,
 PIPE_PRIM_TRIANGLES,PIPE_PRIM_TRIANGLE_STRIP,PIPE_PRIM_TRIANGLE_FAN,
 PIPE_PRIM_QUADS,PIPE_PRIM_QUAD_STRIP,PIPE_PRIM_POLYGON,
 PIPE_PRIM_LINES_ADJACENCY,PIPE_PRIM_LINE_STRIP_ADJACENCY,
 PIPE_PRIM_TRIANGLES_ADJACENCY,PIPE_PRIM_TRIANGLE_STRIP_ADJACENCY};
#define DRAW_PIPE_RESET_STIPPLE 1
#define DRAW_PIPE_EDGE_FLAG_0 2
#define DRAW_PIPE_EDGE_FLAG_1 4
#define DRAW_PIPE_EDGE_FLAG_2 8
#define DRAW_PIPE_EDGE_FLAG_ALL 14
#define DRAW_SPLIT_BEFORE 1
#define DRAW_SPLIT_AFTER 2
#define debug_printf(...) ((void)0)
#define FUNC mesa_decompose
#define FUNC_VARS unsigned prim,const unsigned *input,unsigned count,unsigned short *out,unsigned *at
#define LOCAL_VARS const unsigned last_vertex_last=1,quads_flatshade_last=1,prim_flags=0;
#define GET_ELT(i) input[i]
#define POINT(i) assert(0)
#define LINE(f,a,b) assert(0)
#define TRIANGLE(f,a,b,c) do{(void)(f);out[(*at)++]=(a);out[(*at)++]=(b);out[(*at)++]=(c);}while(0)
#include "draw_decompose_tmp.h"
int main(void)
{
 unsigned indices[513],lengths[3],n=0,cases=0;
 unsigned short actual[4096],expected[4096],before[4096];
 for(unsigned i=0;i<513;++i)indices[i]=(i*37+13)%4096;
 for(unsigned p=4;p<=8;++p){
  if(p!=4&&p!=7&&p!=8)continue;
  for(unsigned count=0;count<=513;++count){
   for(unsigned split=0;split<3;++split){
    lengths[0]=split?count/3:count;lengths[1]=split?count/3:0;lengths[2]=count-lengths[0]-lengths[1];
    unsigned want=0,base=0;
    for(unsigned r=0;r<3;++r){mesa_decompose(p,indices+base,lengths[r],expected,&want);base+=lengths[r];}
    memset(actual,0xa5,sizeof(actual));memcpy(before,actual,sizeof(actual));n=999;
    if(want){assert(mbx_vgp_topology(p,indices,count,lengths,3,4096,actual,want-1,&n)<0);assert(n==999&&!memcmp(actual,before,sizeof(actual)));}
    assert(!mbx_vgp_topology(p,indices,count,lengths,3,4096,actual,4096,&n));
    assert(n==want&&!memcmp(actual,expected,want*2));
    assert(!memcmp(actual+n,before+n,sizeof(actual)-n*2));++cases;
   }
  }
 }
 lengths[0]=513;indices[512]=4096;memset(actual,0xa5,sizeof(actual));memcpy(before,actual,sizeof(actual));n=999;
 assert(mbx_vgp_topology(8,indices,513,lengths,1,4096,actual,4096,&n)<0);
 assert(n==999&&!memcmp(actual,before,sizeof(actual)));
 printf("PASS %u cases against pinned Mesa decomposition, including incomplete primitives and independent strip runs\n",cases);
}
