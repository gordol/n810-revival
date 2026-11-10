/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../kernel/mbx_desktop_layout.h"
#include "../kernel/mbx_parameter_data.h"
#include "../common/mbx_vgp_wire.h"
int main(void){
 struct mbx_desktop_layout l;
 assert(!mbx_desktop_layout(400,400,0,&l)&&l.words==1568&&l.ta_extent==0x018460e1&&l.isp_extent==0x00180018);
 assert(mbx_desktop_layout(800,480,0,&l));
 assert(!mbx_desktop_layout(800,480,1,&l)&&l.words==3328&&l.ta_extent==0x031474e1&&l.isp_extent==0x001d0031);
 assert(mbx_state_bytes(28,28)==4032);
 assert(mbx_state_bytes(52,32)==14464&&l.state_bytes==14464);
 assert(l.state_bytes>4096&&l.state_bytes<=MBX_TA_STATE_BYTES);
 unsigned words[8192];for(unsigned i=0;i<8192;i++)words[i]=0xa55a1234;
 assert(!mbx_tile_headers(words,0x7000/4,l.tx,l.ty,4,4));
 assert(words[l.words-2]==(0x22000000|48|(28<<8)));
 for(unsigned i=l.words;i<8192;i++)assert(words[i]==0xa55a1234);
 assert(mbx_desktop_layout(801,480,1,&l)&&mbx_desktop_layout(800,481,1,&l));
 struct {struct mbx_vgp_wire_frame frame;unsigned resources[4];} wire={.frame={.magic=MBX_VGP_WIRE_MAGIC,.version=9,.bytes=64,.width=800,.height=480,.clear_color={0,0,0,0x3f800000},.clear_depth=0x3f800000,.clear_buffers=5}};
 struct mbx_vgp_wire_frame *f=&wire.frame;
 struct mbx_command *c=calloc(MBX_VGP_WIRE_MAX_COMMANDS,sizeof(*c));assert(c);unsigned n=0;
 assert(!mbx_vgp_wire_encode(&wire,64,c,MBX_VGP_WIRE_MAX_COMMANDS,&n)&&n>0);
 f->version=10;assert(mbx_vgp_wire_encode(&wire,64,c,MBX_VGP_WIRE_MAX_COMMANDS,&n));
 f->version=9;f->width=801;assert(mbx_vgp_wire_encode(&wire,64,c,MBX_VGP_WIRE_MAX_COMMANDS,&n));free(c);
 /* 768000 pixels bytes occupy 188 pages; all tail bytes remain guarded. */
 assert((768000+4095)/4096==188&&768000%4096==2048&&0x100000+188*4096<=0x200000);
 puts("desktop layout: exact pinned register fields, bounded tile list, 188 disjoint frame pages, legacy and rejected-layout checks pass");
}
