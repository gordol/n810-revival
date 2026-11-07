/* SPDX-License-Identifier: MIT */
#include "../common/mbx_vgp_batch.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
int main(void)
{
 struct mbx_vgp_position v[3*MBX_MAX_BATCH_TRIANGLES]={0};
 struct mbx_command commands[115+20*MBX_MAX_BATCH_TRIANGLES],saved[115+20*MBX_MAX_BATCH_TRIANGLES];
 unsigned matrix[16]={0},color[4]={0,0x3f800000,0,0x3f800000},written=1234;
 for(unsigned i=0;i<4;++i)matrix[i*5]=0x3f800000;
 for(unsigned i=0;i<3*MBX_MAX_BATCH_TRIANGLES;++i)v[i].xyzw[3]=0x3f800000;
 memset(commands,0xa5,sizeof(commands));memcpy(saved,commands,sizeof(commands));
 assert(mbx_encode_vgp_batch(v,1,matrix,color,commands,134,&written)<0);
 assert(written==1234&&!memcmp(commands,saved,sizeof(commands)));
 v[767].xyzw[0]=0x7fc00001;
 assert(mbx_encode_vgp_batch(v,256,matrix,color,commands,5235,&written)<0);
 assert(written==1234&&!memcmp(commands,saved,sizeof(commands)));v[767].xyzw[0]=0;
 for(unsigned n=1;n<=256;++n){
  assert(!mbx_encode_vgp_batch(v,n,matrix,color,commands,5235,&written));
  assert(written==115+20*n);
  assert(commands[2].value==0x90000007&&commands[19].value==0x8000ffff);
  for(unsigned i=0;i<16;++i)assert(commands[20+i].value==(i==2?0x01000700U:0xf0000000U));
  assert(commands[36].value==0xa0000003&&commands[53].value==0xa00f000f&&commands[58].value==0xa0100011);
  for(unsigned i=0;i<n;++i){unsigned at=114+20*i;assert(commands[at+6].value==0x70020004&&commands[at+3].value==4&&commands[at+1].value==0x22200200);
   for(unsigned j=0;j<12;++j)assert(commands[at+7+j].value==v[i*3+j/4].xyzw[j%4]);
   assert(commands[at+19].destination==MBX_POLYGON_CONTROL&&commands[at+19].value==1);}
  assert(commands[written-1].value==0xf0000000);
 }
 puts("PASS original VGP batches1..256: one program/matrix upload, packed untouched vertices, bounded atomic rejection. Matrix/color/render verified separately on physical N810.");
}
