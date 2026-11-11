/* SPDX-License-Identifier: MIT. Exact attribute/index reconstruction, no GPU. */
#define main baseline_sampler_main
#include "test_window_native_encoder.c"
#undef main
#include "../mesa/mbx_draw_batch.h"
static unsigned batch[262144],record[8192],before[262144];
static unsigned make_record(void){
 unsigned bytes=make_frame(0);struct mbx_vgp_wire_frame *f=(void*)wire;
 struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+48);
 d->reserved=64;d->viewport[0]=d->viewport[1]=0x43480000U;d->viewport[2]=0x43000000U;d->viewport[3]=0xc3000000U;
 memcpy(record,d,d->bytes);(void)bytes;(void)f;return d->bytes;
}
int main(void){
 unsigned size=make_record();struct mbx_vgp_wire_draw *r=(void*)record;
 struct mbx_vgp_wire_frame *f=(void*)batch;
 *f=(struct mbx_vgp_wire_frame){.magic=MBX_VGP_WIRE_MAGIC,.version=9,.bytes=64,.width=400,.height=256,.clear_depth=0x3f800000U,.clear_buffers=5};
 memset(batch+12,0,16);unsigned last=0,merged=0,total=0;
 for(unsigned i=0;i<768;i++){
  unsigned *v=record+16+16+20;v[2]=i; /* Every original vertex tuple identifiable. */
  struct mbx_vgp_wire_draw *p=mbx_batch_previous(batch,sizeof batch,last,r,record+16,record+32,record+52);
  struct mbx_vgp_wire_draw *next=(void*)((unsigned char*)batch+f->bytes);memcpy(next,r,size);f->bytes+=size;
  if(p){f->bytes-=mbx_batch_join(p,next);last=p->bytes;merged++;}
  else{last=size;f->draws++;}total+=2;
 }
 assert(f->draws==6&&merged==762&&total==1536);
 struct mbx_wire_resources resources;assert(!mbx_wire_resources_parse(batch,f->bytes,&resources));
 unsigned offset=resources.draw_offset,vertex_id=0;
 for(unsigned j=0;j<f->draws;j++){
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)batch+offset);assert(d->vertices==512&&d->triangles==256);
  const unsigned *vertices=(void*)((unsigned char*)d+mbx_batch_prefix(d));
  const unsigned short *index=(void*)(vertices+4*d->vertices);
  for(unsigned k=0;k<128;k++,vertex_id++){
   assert(vertices[k*16+2]==vertex_id);
   static const unsigned short expected[6]={0,1,2,1,3,2};
   for(unsigned n=0;n<6;n++)assert(index[k*6+n]==k*4+expected[n]);
  }
  offset+=d->bytes;
 }
 assert(vertex_id==768&&offset==f->bytes);unsigned count;assert(!mbx_vgp_wire_encode(batch,f->bytes,commands,65536,&count));
 /* Exhausted per-draw limits and changed state never merge, or mutate input. */
 memcpy(before,batch,f->bytes);assert(!mbx_batch_previous(batch,sizeof batch,last,r,record+16,record+32,record+52));assert(!memcmp(before,batch,f->bytes));
 f->bytes=64+size;f->draws=1;memcpy(batch+16,record,size);last=size;
 for(unsigned mutation=0;mutation<5;mutation++){
  struct mbx_vgp_wire_draw original=*r;
  if(mutation==0)r->reserved^=128;if(mutation==1)r->viewport[0]++;if(mutation==2)r->smooth^=1;if(mutation==3)record[16]^=1;if(mutation==4)record[32]^=1;
  assert(!mbx_batch_previous(batch,sizeof batch,last,r,record+16,record+32,record+52));
  if(mutation==3)record[16]^=1;if(mutation==4)record[32]^=1;*r=original;
 }
 puts("draw batch: 768 quads -> 6 bounded draws; exact ordered attributes/indices; state/program/uniform changes and 256-triangle ceiling respected; shared encoder accepted400x256");
}
