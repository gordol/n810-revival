/* SPDX-License-Identifier: MIT */
#include "../common/mbx_packets.h"
#include <assert.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
static struct mbx_vertex vertices[MBX_MAX_BATCH_TRIANGLES*3];
static struct mbx_command commands[MBX_MAX_BATCH_COMMANDS+2],before[MBX_MAX_BATCH_COMMANDS+2];
int main(void)
{
 unsigned i,n,written=0xdeadbeefU;
 for(i=0;i<MBX_MAX_BATCH_TRIANGLES*3;++i)
  vertices[i]=(struct mbx_vertex){0,0,0x3f800000U,0xff00ff00U};
 for(n=1;n<=MBX_MAX_BATCH_TRIANGLES;++n){
  unsigned ends=0,controls=0;
  memset(commands,0xa5,sizeof(commands));
  assert(!mbx_encode_triangle_batch(32,32,vertices,n,commands+1,20*n+3,&written));
  assert(written==20*n+3);
  assert(commands[1].destination==MBX_FIFO && commands[1].value==0x10000010U);
  assert(commands[2].destination==MBX_FIFO && commands[2].value==0);
  for(i=1;i<=written;++i){
   if(commands[i].destination==MBX_POLYGON_CONTROL){assert(i>2 && (i-2)%20==0);assert(commands[i].value==1);++controls;}
   else {assert(commands[i].destination==MBX_FIFO);if(commands[i].value==0xf0000000U)++ends;}
  }
  assert(controls==n && ends==1);
  assert(commands[written].value==0xf0000000U);
  assert(commands[0].value==0xa5a5a5a5U && commands[written+1].value==0xa5a5a5a5U);
 }
 memcpy(before,commands,sizeof(commands));written=0xdeadbeefU;
 /* Last-vertex invalidity must not publish a partial batch or a length. */
 vertices[MBX_MAX_BATCH_TRIANGLES*3-1].z=0x7fc00000U;
 assert(mbx_encode_triangle_batch(32,32,vertices,256,commands+1,5123,&written)==-22);
 assert(!memcmp(before,commands,sizeof(commands)) && written==0xdeadbeefU);
 for(i=0;i<3;++i){unsigned invalid[]={0,257,UINT_MAX};
  assert(mbx_encode_triangle_batch(32,32,vertices,invalid[i],commands+1,UINT_MAX,&written)==-22);
 }
 assert(mbx_encode_triangle_batch(32,32,vertices,1,commands+1,20,&written)==-22);
 assert(!memcmp(before,commands,sizeof(commands)) && written==0xdeadbeefU);
 puts("MBX batches: 1..256 triangles, one frame end, polygon sidebands, bounds and atomic rejection PASS");
}
