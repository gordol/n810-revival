/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_transform.h"
/* Numeric ISA fields recovered independently in the offline codec and checked
 * against the normal N95 geometry path. Unused operands are canonical zero.
 * The observed N95 clip-output selector is 7; do not substitute Lite selector5.
 */
static void unary(unsigned *p,unsigned destination,unsigned mask,unsigned bank,
                  unsigned source,unsigned swizzle)
{
 p[0]=1U|(swizzle<<8);
 p[1]=(destination<<26)|(mask<<22)|(bank<<16)|(source&15U);
 if(bank==1)p[1]|=(source>>4)<<12;
}
static void dot(unsigned *p,unsigned destination,unsigned mask,unsigned bank,
                unsigned source,unsigned constant)
{
 p[0]=8U|(0xe4U<<8)|(0xe4U<<16);
 p[1]=(destination<<26)|(mask<<22)|(bank<<16)|(1U<<18)|
       source|((constant&15U)<<4)|((constant>>4)<<12);
}
int mbx_vgp_transform(unsigned matrix_first,unsigned color,unsigned clip_first,
                      unsigned *words,unsigned capacity)
{
 unsigned i,temporary[MBX_VGP_TRANSFORM_WORDS];
 if(!words||capacity<MBX_VGP_TRANSFORM_WORDS||matrix_first>124||color>127||clip_first>126)return -22;
 /* Independent matrix rows fill r3. Publishing and clip calculations consume
  * that vector after all four rows, following the observed dependency order. */
 for(i=0;i<4;++i)dot(temporary+2*i,19,1U<<i,0,0,matrix_first+i);
 unary(temporary+8,1,15,1,color,0xc6); /* API RGBA to observed diffuse B,G,R,A */
 unary(temporary+10,0,15,2,3,0xe4);
 dot(temporary+12,7,1,2,3,clip_first);
 dot(temporary+14,7,2,2,3,clip_first+1);
 for(i=0;i<MBX_VGP_TRANSFORM_WORDS;++i)words[i]=temporary[i];
 return MBX_VGP_TRANSFORM_INSTRUCTIONS;
}
