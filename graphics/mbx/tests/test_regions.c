/* SPDX-License-Identifier: MIT */
#include "../common/mbx_regions.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
 unsigned opb[16]={0},p[64]={0},r[32]={0},saved_p[64],saved_r[32],x,y;
 unsigned seen=0;
 for(y=0;y<4;++y)for(x=0;x<4;++x){unsigned n=mbx_morton(x,y);assert(n<16);assert(!(seen&(1U<<n)));seen|=1U<<n;}
 assert(seen==65535U && mbx_morton(1,0)==1 && mbx_morton(0,1)==2 && mbx_morton(2,0)==4);
 opb[0]=0x10000U/4+26;opb[3]=0x3f800000U|(0x10000U/4+63);
 assert(!mbx_finish_regions(2,2,opb,16,0x10000,p,64,26,r,32));
 assert(p[26]==0xf0000000U && p[63]==0xf0000000U);
 assert(r[0]==0 && r[2]==0x02000000U && r[4]==0x02000000U && r[6]==0);
 memcpy(saved_p,p,sizeof(p));memcpy(saved_r,r,sizeof(r));
 /* Invalid late cursor must not partially update earlier regions/parameters. */
 opb[0]=0;opb[3]=0x10000U/4+64;
 assert(mbx_finish_regions(2,2,opb,16,0x10000,p,64,26,r,32)==-22);
 assert(!memcmp(saved_p,p,sizeof(p)) && !memcmp(saved_r,r,sizeof(r)));
 opb[3]=0x10000U/4+25;
 assert(mbx_finish_regions(2,2,opb,16,0x10000,p,64,26,r,32)==-22);
 assert(mbx_finish_regions(2,2,opb,3,0x10000,p,64,26,r,32)==-22);
 assert(mbx_finish_regions(33,1,opb,16,0x10000,p,64,26,r,32)==-22);
 puts("MBX regions: Morton slots, empty flags, parameter termination, pool boundaries and atomic rejection PASS");
}
