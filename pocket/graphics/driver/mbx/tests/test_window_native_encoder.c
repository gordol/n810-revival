/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_wire.h"
#include "mbx_vgp_transform.h"
#include "mbx_vgp_isa.h"
#include "mbx_wire_resources.h"
#include "mbx_texture_resident.h"
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
 for(unsigned slot=0;slot<14;slot++){
  make_frame(1);struct mbx_vgp_wire_frame *f=(void *)wire;unsigned drawbytes=f->bytes-8240;
  memmove((unsigned char *)wire+64,(unsigned char *)wire+8240,drawbytes);
  memset((unsigned char *)wire+48,0,16);f->version=9;f->bytes=64+drawbytes;
  unsigned index,count;struct mbx_window_token token={17,19,slot};
  assert(!mbx_wire_resource_append_window_layout(wire,sizeof wire,token,2,&index));assert(index==0);
  assert(!mbx_vgp_wire_encode(wire,f->bytes,commands,65536,&count));
  unsigned width=slot<2?240:128,address=0x0e000000U|((width>>4)<<18)|(mbx_window_address(2,slot)>>7),matches=0;
  for(unsigned i=0;i<count;i++)if(commands[i].value==address){
   assert((((commands[i].value>>18)&63U)*16U)==width);
   assert(((commands[i].value&0x3ffffU)<<7)==mbx_window_address(2,slot));matches++;
  }
  assert(matches==1);
  struct mbx_wire_resource *r=(void*)((unsigned char*)wire+64);r->offset=14;
  assert(mbx_vgp_wire_encode(wire,f->bytes,commands,65536,&count));
  r->offset=slot;
  unsigned char pixels[2304]={0};assert(!mbx_wire_resource_append_linear(wire,sizeof wire,pixels,16,16,sizeof pixels,&index));
  struct mbx_wire_resources resources;assert(!mbx_wire_resources_parse(wire,f->bytes,&resources));
  static unsigned char arena[2304],compact[32768],expanded_frame[32768];unsigned packed,expanded;
  struct mbx_texture_resident cache={.session=17,.data=arena};
  assert(!mbx_texture_resident_commit(&cache,wire,&resources));
  assert(!mbx_texture_ref_pack(&cache,wire,f->bytes,compact,sizeof compact,&packed));
  memcpy(expanded_frame,compact,packed);assert(!mbx_texture_ref_expand(&cache,expanded_frame,packed,sizeof expanded_frame,&expanded));
  assert(expanded==f->bytes&&!memcmp(expanded_frame,wire,expanded));
  r=(void*)((unsigned char*)wire+64);r->bytes++;memset(compact,0x55,sizeof compact);
  assert(mbx_texture_ref_pack_subset(&cache,wire,f->bytes,compact,sizeof compact,&packed)&&compact[0]==0x55);
 }
 puts("native sampler: all fourteen client addresses/pitches exact; 240x320 pitch960 and twelve pitch512 UI images; scratch sampling rejected; mixed-upload cache expansion exact and stale generation rejected");
}
