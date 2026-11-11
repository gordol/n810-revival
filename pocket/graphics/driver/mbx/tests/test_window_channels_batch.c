/* SPDX-License-Identifier: MIT. Exact initial transfer; no GPU execution. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../mesa/window_channels_batch.h"
#include "channel_request.h"
static unsigned char inputs[2][1024*(4096+32)],packet[131152],expected[131072],saved[131152];
static struct mbx_command commands[65536];
int main(void){
 const unsigned stride=4096+32;
 for(unsigned y=0;y<1024;y++)for(unsigned x=0;x<1024;x++)for(unsigned k=0;k<2;k++){
  unsigned char *p=inputs[k]+y*stride+4*x;
  p[0]=k?((x+y)&1?255:0):(x*13+y)%256;p[1]=(y*17+x)%256;
  p[2]=k?((x+y)&1?0:255):(x*3+y*5)%256;p[3]=(x*7+y*11)%256;
 }
 struct mbx_window_upload_item items[64];memset(expected,0,sizeof expected);
 for(unsigned i=0;i<64;i++){
  unsigned w=1+i%16,h=2+i%15,sx=(i*13)%1000,sy=(i*17)%1000;
  items[i]=(struct mbx_window_upload_item){
   {inputs[0]+sy*stride+4*sx,(h-1)*stride+w*4,stride,w,h,i&1,0,0},
   {inputs[1]+sy*stride+4*sx,(h-1)*stride+w*4,stride,w,h,(i>>1)&1,0,0},
   (i%8)*16,(i/8)*16,i%3};
  for(unsigned k=0;k<2;k++)for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
   const struct mbx_linear_source *s=k?&items[i].mask:&items[i].source;
   const unsigned char *in=s->data+y*stride+4*x;
   unsigned char *out=expected+k*65536+((items[i].dy+y)*128+items[i].dx+x)*4;
   out[0]=in[s->rgba?2:0];out[1]=in[1];out[2]=in[s->rgba?0:2];out[3]=in[k&&items[i].mode?(s->rgba?0:2):3];
  }
 }
 unsigned bytes=0,count;
 assert(!mbx_window_channels_batch_pack(items,64,packet,sizeof packet,&bytes)&&bytes==sizeof packet);
 assert(!memcmp(packet+80,expected,sizeof expected));
 struct mbx_wire_resources resources;assert(!mbx_wire_resources_parse(packet,bytes,&resources));
 assert(!mbx_window_channel_upload_validate((void*)packet,&resources,8));
 assert(!mbx_vgp_wire_encode(packet,bytes,commands,65536,&count));
 memcpy(saved,packet,sizeof saved);
 for(unsigned mutation=0;mutation<9;mutation++){
  struct mbx_window_upload_item original=items[63];unsigned written=37;
  if(mutation==0)items[63].dx=items[0].dx,items[63].dy=items[0].dy;
  if(mutation==1)items[63].dx=~0U;
  if(mutation==2)items[63].source.height=0;
  if(mutation==3)items[63].mode=3;
  if(mutation==4)items[63].mask.width++;
  if(mutation==5)items[63].mask.stride=1;
  if(mutation==6)items[63].mask.bytes=1;
  if(mutation==7)items[63].source.data=packet;
  if(mutation==8)items[63].mask.rgba=2;
  assert(mbx_window_channels_batch_pack(items,64,packet,sizeof packet,&written)==-22);
  assert(written==37&&!memcmp(packet,saved,sizeof saved));items[63]=original;
 }
 unsigned written=37;
 assert(mbx_window_channels_batch_pack(items,0,packet,sizeof packet,&written)==-22);
 assert(mbx_window_channels_batch_pack(items,65,packet,sizeof packet,&written)==-22);
 assert(mbx_window_channels_batch_pack(items,64,packet,sizeof packet-1,&written)==-22);
 struct mbx_window_upload_item *last=items+63;last->mode=2;
 unsigned char *red=(unsigned char*)last->mask.data+(last->mask.rgba?0:2);unsigned char previous=*red;*red=127;
 assert(mbx_window_channels_batch_pack(items,64,packet,sizeof packet,&written)==-95);
 assert(written==37&&!memcmp(packet,saved,sizeof saved));*red=previous;
 struct mbx_window_upload_item corner={
  {inputs[0]+1023*stride+1023*4,4,stride,1,1,1,0,0},
  {inputs[1]+1023*stride+1023*4,4,stride,1,1,1,0,0},127,127,2};
 assert(!mbx_window_channels_batch_pack(&corner,1,packet,sizeof packet,&bytes));
 assert(packet[80+65536+65535]==corner.mask.data[0]);
 puts("atlas batch:64 disjoint mixed-format/mode crops, both exact planes and zero gaps; shared encoder/kernel admission; late invalid/binary/overflow/alias/capacity rejection before writes; far-corner1x1 passed (no GPU execution)");
}
