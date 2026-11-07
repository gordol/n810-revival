/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_topology.h"
int mbx_vgp_topology(unsigned primitive, const unsigned *indices,
                     unsigned count, const unsigned *lengths, unsigned runs,
                     unsigned vertices, unsigned short *out,
                     unsigned capacity, unsigned *written)
{
 unsigned r,i,total=0,needed=0,base=0,at=0;
 if(!indices||!lengths||!out||!written||!vertices||vertices>4096||
    count>16384||!runs||runs>4096||
    (primitive!=4&&primitive!=7&&primitive!=8))return -22;
 for(r=0;r<runs;++r){
  unsigned n=lengths[r];
  if(n>count-total)return -22;
  total+=n;
  needed+=primitive==4?n/3*3:primitive==7?n/4*6:n>=4?(n/2-1)*6:0;
 }
 if(total!=count||needed>capacity)return -22;
 for(i=0;i<count;++i)if(indices[i]>=vertices)return -22;
 /* Reject the entire draw before modifying caller storage. Incomplete
  * trailing primitives are ignored, matching Mesa primitive decomposition. */
 for(r=0;r<runs;++r){
  unsigned n=lengths[r];
  if(primitive==4){
   for(i=0;i+2<n;i+=3){
    out[at++]=indices[base+i];out[at++]=indices[base+i+1];out[at++]=indices[base+i+2];
   }
  }else for(i=0;i+3<n;i+=primitive==7?4:2){
   unsigned a=indices[base+i],b=indices[base+i+1],c=indices[base+i+2],d=indices[base+i+3];
   if(primitive==7){out[at++]=a;out[at++]=b;out[at++]=d;out[at++]=b;out[at++]=c;out[at++]=d;}
   else{out[at++]=c;out[at++]=a;out[at++]=d;out[at++]=a;out[at++]=b;out[at++]=d;}
  }
  base+=n;
 }
 *written=at;return 0;
}
