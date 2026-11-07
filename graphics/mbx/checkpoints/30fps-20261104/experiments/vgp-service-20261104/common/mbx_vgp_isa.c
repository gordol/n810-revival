/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_isa.h"
int mbx_vgp_encode(unsigned op,unsigned dst,unsigned mask,
 const struct mbx_vgp_source *s,unsigned count,unsigned words[2])
{
 unsigned arity,a,b,i,constant=128,input=16;
 switch(op){case 1:case 5:case 6:arity=1;break;
 case 2:case 4:case 7:case 8:case 9:case 10:case 11:case 12:arity=2;break;
 case 3:arity=3;break;default:return -22;}
 if(!words||!s||count!=arity||!mask||mask>15||!(dst==0||dst==1||dst==3||dst==4||dst==7||(dst>=16&&dst<=29)))return -22;
 a=op;b=(dst<<26)|(mask<<22);
 for(i=0;i<count;++i){
  unsigned bank=s[i].bank,index=s[i].index;
  if(bank>2||s[i].swizzle>255||s[i].negative>1||index>(bank==0?15:bank==1?127:13))return -22;
  if(bank==0){if(input!=16&&input!=index)return -22;input=index;}
  if(bank==1){if(constant!=128&&constant!=index)return -22;constant=index;b|=(index>>4)<<12;}
  a|=s[i].swizzle<<(8+8*i);a|=s[i].negative<<(5+i);
  b|=(index&15)<<(4*i);b|=bank<<(16+2*i);
 }
 words[0]=a;words[1]=b;return 0;
}
