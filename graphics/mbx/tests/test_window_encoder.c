/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_wire.h"
#include "mbx_vgp_transform.h"
#include "mbx_vgp_isa.h"
#include "mbx_wire_resources.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned wire[8192];
static struct mbx_command commands[65536];
static unsigned make_frame(unsigned texture)
{
 memset(wire,0,sizeof wire);
 struct mbx_vgp_wire_frame *f=(void *)wire;
 *f=(struct mbx_vgp_wire_frame){.magic=MBX_VGP_WIRE_MAGIC,.version=texture?3:2,.draws=1,.width=400,.height=400,.clear_color={0,0,0,0x3f800000},.clear_depth=0x3f800000,.clear_buffers=5};
 unsigned offset=48+(texture?8192:0);
 if(texture)for(unsigned i=48;i<offset;i++)((unsigned char *)wire)[i]=(unsigned char)i;
 struct mbx_vgp_wire_draw *d=(void *)((unsigned char *)wire+offset);
 *d=(struct mbx_vgp_wire_draw){.bytes=384,.instructions=texture?9:8,.uniforms=5,.inputs=1,.vertices=4,.triangles=2,.viewport={0x43480000,0x43480000,0x43480000,0xc3480000,0x3f000000,0x3f000000},.reserved=texture?4:0};
 unsigned *p=(void *)(d+1);assert(mbx_vgp_transform(0,4,112,p,16)==8);p+=16;
 if(texture){struct mbx_vgp_source src={1,0,0xe4,0};assert(!mbx_vgp_encode(1,3,15,&src,1,p));p+=2;}
 for(unsigned i=0;i<20;i++)p[i]=(i==0||i==5||i==10||i==15||i>=16)?0x3f800000:0;p+=20;
 unsigned vertices[16]={0xbf800000,0xbf800000,0,0x3f800000,0x3f800000,0xbf800000,0,0x3f800000,0xbf800000,0x3f800000,0,0x3f800000,0x3f800000,0x3f800000,0,0x3f800000};
 memcpy(p,vertices,sizeof vertices);p+=16;
 unsigned short indices[6]={0,1,2,1,3,2};memcpy(p,indices,sizeof indices);
 d->bytes=64+8*d->instructions+80+64+12;f->bytes=offset+d->bytes;return f->bytes;
}

int main(void){
 for(unsigned slot=0;slot<16;slot++){
  make_frame(1);struct mbx_vgp_wire_frame *f=(void *)wire;
  unsigned drawbytes=f->bytes-8240;
  memmove((unsigned char *)wire+64,(unsigned char *)wire+8240,drawbytes);
  memset((unsigned char *)wire+48,0,16);f->version=9;f->bytes=64+drawbytes;
  unsigned index,count;struct mbx_window_token token={17,19,slot};
  assert(!mbx_wire_resource_append_window(wire,sizeof wire,token,&index));assert(index==0);
  assert(!mbx_vgp_wire_encode(wire,f->bytes,commands,65536,&count));
  unsigned address=0x0e000000U|((128U>>4)<<18)|(MBX_WINDOW_ADDRESS(slot)>>7),matches=0;
  for(unsigned i=0;i<count;i++)if(commands[i].value==address)matches++;
  assert(matches==1);
 }
 puts("window sampler: all 16 validated slots encode the expected native32 address and pitch");
}
