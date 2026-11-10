/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_wire.h"
#include "mbx_vgp_transform.h"
#include "mbx_vgp_isa.h"
#include "../mesa/mbx_template_update.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned wire[8192],snapshot[8192],update[512];
static struct mbx_command command[65536],reference[65536],before[65536];
static struct mbx_vgp_prepared object;
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
static void exercise(unsigned texture)
{
 unsigned bytes=make_frame(texture),written,count;
 struct mbx_vgp_prepared_handle h,old,wrong;
 assert(!mbx_vgp_prepared_dispatch(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));
 assert(count==object.cache.written&&!memcmp(command,reference,count*sizeof *command));
 memcpy(before,command,count*sizeof *command);
 for(unsigned i=0;i<1000;i++){
  assert(!mbx_vgp_prepared_begin(&object,h,0,0,&written));assert(written==count);
  assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));assert(mbx_vgp_prepared_close(&object));
  assert(!mbx_vgp_prepared_complete(&object,h,1));
 }
 assert(!memcmp(command,before,count*sizeof *command));assert(!memcmp(snapshot,wire,bytes));
 if(texture){
  wire[12]^=1;assert(!mbx_template_update(snapshot,bytes,wire,bytes,h.generation,update,sizeof update,&written));wire[12]^=1;
 }
 struct mbx_vgp_wire_update *u=(void *)update;
 *u=(struct mbx_vgp_wire_update){.magic=MBX_VGP_UPDATE_MAGIC,.version=1,.bytes=136,.draws=1,.generation=h.generation};
 struct mbx_vgp_wire_draw *d=(void *)((unsigned char *)wire+48+(texture?8192:0));
 unsigned *uniform=(void *)((unsigned char *)(d+1)+8*d->instructions);
 d->viewport[0]=0x43490000;uniform[16]=0x3f000000;
 assert(mbx_template_update(snapshot,bytes,wire,bytes,h.generation,u,sizeof update,&written)==1);assert(written==136);
 assert(!mbx_vgp_prepared_dispatch(&object,7,u,136,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));
 assert(written==count&&!memcmp(command,reference,count*sizeof *command));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 for(unsigned step=0;step<64;step++){
  d->viewport[0]=0x43000000+step*0x10000;uniform[16]=0x3e800000+step*0x1000;
  assert(mbx_template_update(snapshot,bytes,wire,bytes,h.generation,u,sizeof update,&written)==1);assert(written==136);
  assert(!mbx_vgp_prepared_dispatch(&object,7,u,136,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
  assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));
  assert(written==count&&!memcmp(command,reference,count*sizeof *command));
  assert(!mbx_vgp_prepared_complete(&object,h,1));
 }
 assert(!mbx_vgp_prepared_export(&object,h));
 assert(mbx_vgp_prepared_close(&object));assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));
 assert(mbx_vgp_prepared_create(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&old));
 assert(!mbx_vgp_prepared_release(&object,h));assert(mbx_vgp_prepared_release(&object,h));
 memcpy(before,command,count*sizeof *command);
 update[33]=0x7fc00000;assert(mbx_vgp_prepared_begin(&object,h,u,136,&written));
 assert(!memcmp(command,before,count*sizeof *command));update[33]=0x3f800000;
 assert(mbx_vgp_prepared_begin(&object,h,u,132,&written));
 wrong=h;wrong.session++;assert(mbx_vgp_prepared_begin(&object,wrong,0,0,&written));
 assert(mbx_vgp_prepared_dispatch(&object,8,u,136,command,65536,(void *)snapshot,sizeof snapshot,0,&wrong,&written));
 assert(mbx_vgp_prepared_dispatch(&object,7,u,136,reference,65536,(void *)snapshot,sizeof snapshot,0,&wrong,&written));
 assert(!memcmp(command,before,count*sizeof *command));
 old=h;assert(!mbx_vgp_prepared_create(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h));
 assert(mbx_vgp_prepared_begin(&object,old,0,0,&written));
 assert(mbx_vgp_prepared_begin(&object,h,u,136,&written)); /* stale update generation */
 assert(!mbx_vgp_prepared_begin(&object,h,0,0,&written));assert(!mbx_vgp_prepared_complete(&object,h,0));
 assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));assert(mbx_vgp_prepared_export(&object,h));
 assert(!mbx_vgp_prepared_close(&object));assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));
 printf("prepared %s: exact full/update command parity; 1000 repeats with zero upload; lifetime guards pass\n",texture?"textured":"geometry");
}
static void mixed_resources(void)
{
 unsigned bytes=make_frame(1),written,count,index;static unsigned char texture[8192];
 struct mbx_vgp_prepared_handle h;
 memmove((unsigned char *)wire+80,(unsigned char *)wire+48,bytes-48);
 wire[1]=9;wire[2]=bytes+=32;wire[12]=1;wire[13]=8192;wire[14]=wire[15]=0;
 wire[16]=3;wire[17]=8192;wire[18]=wire[19]=0;
 memset(texture,0x5a,sizeof texture);
 assert(!mbx_wire_resource_append(wire,sizeof wire,texture,3,sizeof texture,&index)&&index==1);
 bytes=wire[2];struct mbx_wire_resources resources;assert(!mbx_wire_resources_parse(wire,bytes,&resources));
 struct mbx_vgp_wire_draw *d=(void *)((unsigned char *)wire+resources.draw_offset);
 d->reserved|=mbx_resource_index_flags(index)|128U;
 unsigned *uniform=(void *)((unsigned char *)(d+1)+8*d->instructions);
 uniform[16]=uniform[17]=0;uniform[18]=uniform[19]=400;
 assert(!mbx_vgp_prepared_dispatch(&object,9,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));assert(count==written&&!memcmp(command,reference,count*sizeof *command));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 d->viewport[0]=0x43490000;
 assert(mbx_template_update(snapshot,bytes,wire,bytes,h.generation,update,sizeof update,&written));
 assert(!mbx_vgp_prepared_dispatch(&object,9,update,written,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));assert(count==written&&!memcmp(command,reference,count*sizeof *command));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 uniform[18]=399;assert(!mbx_template_update(snapshot,bytes,wire,bytes,h.generation,update,sizeof update,&written));uniform[18]=400;
 ((unsigned char *)wire)[resources.data_offset+8192]^=1;
 assert(!mbx_template_update(snapshot,bytes,wire,bytes,h.generation,update,sizeof update,&written));
 assert(!mbx_vgp_prepared_close(&object));
 puts("mixed textures and immutable scissor: exact dynamic command parity; changed resource/clip requires replacement");
}
static void retirement(void)
{
 unsigned bytes=make_frame(0),written;
 struct mbx_vgp_prepared_handle h;
 assert(!mbx_vgp_prepared_dispatch(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(mbx_vgp_prepared_close(&object));
 assert(mbx_vgp_prepared_retire_after_reset(&object,0,0,1));
 assert(mbx_vgp_prepared_retire_after_reset(&object,1,1,1));
 assert(mbx_vgp_prepared_retire_after_reset(&object,1,~0U,1));
 assert(mbx_vgp_prepared_retire_after_reset(&object,1,0,0));
 assert(object.busy&&object.valid&&object.cache.owner==command);
 assert(!mbx_vgp_prepared_retire_after_reset(&object,1,0,1));
 assert(!object.busy&&!object.valid&&!object.cache.owner);
 assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));
 assert(!mbx_vgp_prepared_dispatch(&object,8,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_prepared_complete(&object,h,1));assert(!mbx_vgp_prepared_export(&object,h));
 assert(mbx_vgp_prepared_retire_after_reset(&object,1,0,1));
 assert(!mbx_vgp_prepared_release(&object,h));assert(!mbx_vgp_prepared_retire_after_reset(&object,1,0,1));
 puts("reset retirement: failed evidence retains ownership; verified reset retires; exports block release");
}
static void pool(void)
{
 struct mbx_vgp_prepared objects[MBX_VGP_PREPARED_SLOTS]={0};
 struct mbx_vgp_prepared_handle handles[MBX_VGP_PREPARED_SLOTS];
 struct mbx_command *commands[MBX_VGP_PREPARED_SLOTS];unsigned char *saved[MBX_VGP_PREPARED_SLOTS];
 unsigned written,bytes,count,uploads=0,updates=0;
 for(unsigned i=0;i<MBX_VGP_PREPARED_SLOTS;i++){
  commands[i]=malloc(sizeof command);saved[i]=malloc(sizeof snapshot);assert(commands[i]&&saved[i]);
  bytes=make_frame(0);wire[4]=400-16*i;objects[i].generation=i;
  assert(!mbx_vgp_prepared_dispatch(objects+i,41,wire,bytes,commands[i],65536,saved[i],sizeof snapshot,0,handles+i,&written));
  assert(!mbx_vgp_prepared_complete(objects+i,handles[i],1));uploads+=bytes;
 }
 for(unsigned step=0;step<64;step++)for(unsigned i=0;i<MBX_VGP_PREPARED_SLOTS;i++){
  bytes=make_frame(0);wire[4]=400-16*i;
  struct mbx_vgp_wire_draw *d=(void *)((unsigned char *)wire+48);d->viewport[0]=0x43000000+step*0x10000;
  unsigned matches=0;
  for(unsigned j=0;j<MBX_VGP_PREPARED_SLOTS;j++)if(mbx_template_update(saved[j],objects[j].cache.bytes,wire,bytes,
      handles[j].generation,update,sizeof update,&written)){assert(i==j);matches++;}
  assert(matches==1);
  int slot=mbx_vgp_prepared_find(objects,MBX_VGP_PREPARED_SLOTS,41,handles[i].generation);assert(slot==(int)i);
  assert(!mbx_vgp_prepared_dispatch(objects+i,41,update,136,commands[i],65536,saved[i],sizeof snapshot,0,handles+i,&written));
  assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&count));assert(count==written&&!memcmp(commands[i],reference,count*sizeof *reference));
  assert(!mbx_vgp_prepared_complete(objects+i,handles[i],1));updates+=136;
 }
 unsigned stale=handles[0].generation;bytes=make_frame(0);wire[4]=336;objects[0].generation=4;
 assert(!mbx_vgp_prepared_dispatch(objects,41,wire,bytes,commands[0],65536,saved[0],sizeof snapshot,0,handles,&written));
 assert(mbx_vgp_prepared_find(objects,4,41,stale)<0);assert(mbx_vgp_prepared_find(objects,4,42,handles[1].generation)<0);
 assert(!mbx_vgp_prepared_complete(objects,handles[0],1));
 for(unsigned i=0;i<4;i++){assert(!mbx_vgp_prepared_close(objects+i));free(commands[i]);free(saved[i]);}
 printf("four-slot dispatch: uploads=%u update_bytes=%u updates=256 exact commands; stale eviction rejected\n",uploads,updates);
}
static void rejection(void)
{
 unsigned bytes=make_frame(0),written;
 struct mbx_vgp_prepared_handle h;
 assert(!mbx_vgp_prepared_create(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h));
 wire[0]=0;
 assert(mbx_vgp_prepared_create(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h));
 assert(mbx_vgp_prepared_begin(&object,h,0,0,&written));
 assert(!mbx_vgp_prepared_close(&object));
 bytes=make_frame(0);
 /* Static scissor is retained; updates cannot leave mask commands stale. */
 memmove((unsigned char *)wire+64,(unsigned char *)wire+48,bytes-48);
 memset((unsigned char *)wire+48,0,16);bytes+=16;wire[1]=9;wire[2]=bytes;
 struct mbx_vgp_wire_draw *d=(void *)((unsigned char *)wire+64);d->reserved=128;
 unsigned *uniform=(void *)((unsigned char *)(d+1)+8*d->instructions);
 uniform[16]=uniform[17]=0;uniform[18]=uniform[19]=400;
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&written));
 assert(!mbx_vgp_prepared_dispatch(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!memcmp(command,reference,written*sizeof *command));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 struct mbx_vgp_wire_update *u=(void *)update;
 *u=(struct mbx_vgp_wire_update){.magic=MBX_VGP_UPDATE_MAGIC,.version=1,.bytes=136,.draws=1,.generation=h.generation};
 memcpy(u+1,d->viewport,24);memcpy((unsigned char *)(u+1)+24,uniform,80);
 assert(!mbx_vgp_prepared_dispatch(&object,7,u,136,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!mbx_vgp_prepared_complete(&object,h,1));
 memcpy(before,command,written*sizeof *command);update[32]=399;
 assert(mbx_vgp_prepared_dispatch(&object,7,u,136,command,65536,(void *)snapshot,sizeof snapshot,0,&h,&written));
 assert(!memcmp(command,before,written*sizeof *command));
 assert(!mbx_vgp_prepared_close(&object));object.generation=~0U;
 assert(mbx_vgp_prepared_create(&object,7,wire,bytes,command,65536,(void *)snapshot,sizeof snapshot,0,&h));
 puts("static scissor exact; changed scissor, invalid replacement and exhausted generation rejected");
}
int main(void){exercise(0);exercise(1);mixed_resources();pool();retirement();rejection();return 0;}
