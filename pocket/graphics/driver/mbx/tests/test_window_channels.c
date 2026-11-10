/* SPDX-License-Identifier: MIT. Transfer + command tests, not GPU pixels. */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../mesa/window_channels_wire.h"
static unsigned char source[1024*(1024*4+32)],packet[1048576];
static struct mbx_command commands[65536];
int main(void){
 const unsigned dims[][2]={{1,1},{7,11},{63,127},{128,128},{240,320}};
 for(unsigned size=0;size<5;size++)for(unsigned rgba=0;rgba<2;rgba++)for(unsigned mode=0;mode<3;mode++){
  unsigned w=dims[size][0],h=dims[size][1],sw=size==4?240:128,sh=size==4?320:128,pitch,bytes=0,count;
  for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
   unsigned char *p=source+4*(y*w+x);p[0]=(x*7+y)%256;p[1]=(y*9+x)%256;p[2]=(x*3+y*5)%256;p[3]=(x+y*3)%256;
   if(mode==2)p[rgba?0:2]=((x+y)&1)?255:0;
  }
  struct mbx_linear_source s={source,w*h*4,w*4,w,h,rgba,0,0};
  assert(!mbx_window_channel_pack(&s,mode,packet,sizeof packet,sw,sh,&bytes));
  struct mbx_vgp_wire_frame *f=(void*)packet;assert(f->width==sw&&f->height==sh&&f->draws==1&&f->clear_buffers==5);
  struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(packet,bytes,&r)&&r.count==1&&r.item[0].version==8);
  assert(!mbx_vgp_wire_encode(packet,bytes,commands,65536,&count));
  mbx_linear_size(w,h,&pitch);
  for(unsigned y=0;y<h;y++)for(unsigned x=0;x<w;x++){
   const unsigned char *in=source+4*(y*w+x),*out=packet+80+4*((y+1)*pitch+x+1);
   assert(out[0]==in[rgba?2:0]&&out[1]==in[1]&&out[2]==in[rgba?0:2]&&out[3]==in[mode?(rgba?0:2):3]);
  }
  /* Transparent padding and the addressing halo are transferred normally.
   * Exact GPU sample/merge acceptance remains a physical test boundary. */
  unsigned char before[64];memset(packet,0xa5,sizeof before);memcpy(before,packet,sizeof before);source[rgba?0:2]=127;
  assert(mbx_window_channel_pack(&s,2,packet,sizeof packet,sw,sh,&bytes)==-95&&!memcmp(packet,before,sizeof before));
 }
 /* Nonzero origins and padded full-image stride. Values outside the selected
  * rectangle are deliberately nonbinary: a region packs/checks only itself. */
 const unsigned stride=1024*4+32;memset(source,127,sizeof source);
 const struct mbx_window_rect regions[]={{0,0,128,128},{896,896,128,128},{1023,1023,1,1},{13,457,7,11}};
 for(unsigned i=0;i<4;i++){
  const struct mbx_window_rect *r=regions+i;
  for(unsigned y=0;y<r->height;y++)for(unsigned x=0;x<r->width;x++)source[(r->y+y)*stride+4*(r->x+x)]=((x+y)&1)?255:0;
  struct mbx_linear_source s={source+r->y*stride+r->x*4,(r->height-1)*stride+r->width*4,stride,r->width,r->height,1,0,0};unsigned bytes,pitch;
  assert(!mbx_window_channel_pack(&s,2,packet,sizeof packet,128,128,&bytes));mbx_linear_size(r->width,r->height,&pitch);
  for(unsigned y=0;y<r->height;y++)for(unsigned x=0;x<r->width;x++)assert(packet[80+4*((y+1)*pitch+x+1)+3]==s.data[y*stride+4*x]);
 }
 puts("window channels:30 small/native format/mode cases; exact initial RGB/alpha/red transfer, binary-mask rejection before writes, shared GPU encoder admission passed (no GPU execution)");
}
