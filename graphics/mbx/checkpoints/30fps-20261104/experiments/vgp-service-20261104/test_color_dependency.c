#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "common/mbx_vgp_isa.c"
#include "common/mbx_vgp_draw.c"
static void instruction(unsigned *p,unsigned op,unsigned dst,unsigned mask,
                        unsigned bank,unsigned index,unsigned swizzle)
{
 struct mbx_vgp_source s[3]={{bank,index,swizzle,0},{1,0,228,0},{1,0,228,0}};
 unsigned ns=op==3?3:(op==1||op==5||op==6)?1:2;
 assert(!mbx_vgp_encode(op,dst,mask,s,ns,p));
}
int main(void)
{
 unsigned p[12],op,lane,cases=0;struct mbx_vgp_draw d={.program=p};
 for(op=1;op<=12;++op){
  d.instructions=1;instruction(p,op,1,15,1,0,228);assert(uniform_color(&d));++cases;
  instruction(p,op,1,15,0,0,228);assert(!uniform_color(&d));++cases;
  for(lane=0;lane<4;++lane){
   /* Start with a uniform temp, replace one lane with input, then read it.
    * Dot and scalar op lane semantics must not hide an input dependency. */
   d.instructions=3;instruction(p,1,16,15,1,0,228);
   instruction(p+2,1,16,1U<<lane,0,0,228);
   instruction(p+4,op,1,15,2,0,228);
   assert(uniform_color(&d)==((op==5||op==6)?lane!=0:op==7?lane==3:0));++cases;
   instruction(p+4,op,1,15,2,0,lane*85);
   assert(!uniform_color(&d));++cases;
  }
 }
 /* Unwritten color/temp lanes are never declared constant. */
 d.instructions=1;instruction(p,1,1,7,1,0,228);assert(!uniform_color(&d));++cases;
 instruction(p,1,1,15,2,0,228);assert(!uniform_color(&d));++cases;
 /* Destination aliases a source; evaluate all lanes before writeback. */
 d.instructions=4;instruction(p,1,16,15,1,0,228);
 instruction(p+2,1,16,1,0,0,228);
 instruction(p+4,1,16,15,2,0,225); /* swap x/y */
 instruction(p+6,1,1,15,2,0,85); /* broadcast y, previously varying x */
 assert(!uniform_color(&d));++cases;
 instruction(p+6,1,1,15,2,0,0);assert(uniform_color(&d));++cases;
 printf("PASS %u color dependency cases across all supported opcodes, lanes, swizzles and aliasing\n",cases);
}
