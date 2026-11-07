/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../common/mbx_vgp_wire.h"
#include "../experiments/vgp-persistent-20261104/common/mbx_gears_frame.c"
static unsigned storage[MBX_VGP_WIRE_MAX_BYTES/4];
static struct mbx_command expected[24000],actual[24000];
int main(int argc,char **argv)
{
 unsigned char *bytes=(void *)storage;
 struct mbx_vgp_wire_frame *f=(void *)bytes;
 unsigned offset=48,n=0,want=0,last=0;
 *f=(struct mbx_vgp_wire_frame){.magic=MBX_VGP_WIRE_MAGIC,.version=1,.width=400,.height=400,
    .clear_depth=0x3f800000,.clear_buffers=5};
 for(unsigned i=0;i<21;++i){
  const struct mbx_gears_draw_fixture *source=gears_draws+i;
  struct mbx_vgp_draw draw=source->draw;
  unsigned short indices[768];unsigned count;
  assert(!mbx_vgp_topology(source->primitive,source->indices,source->count,source->lengths,
      source->runs,draw.vertex_count,indices,768,&count));
  if(!count)continue;
  draw.triangle_count=count/3;draw.cull_mode=1;
  unsigned size=mbx_vgp_wire_draw_bytes(&draw);assert(size&&offset+size<sizeof(storage));
  struct mbx_vgp_wire_draw *h=(void *)(bytes+offset);
  *h=(struct mbx_vgp_wire_draw){.bytes=size,.instructions=draw.instructions,.uniforms=draw.uniform_count,
    .immediates=draw.immediate_count,.inputs=draw.input_count,.vertices=draw.vertex_count,
    .triangles=draw.triangle_count,.smooth=draw.smooth,.cull_mode=draw.cull_mode};
  memcpy(h->viewport,draw.viewport,sizeof(h->viewport));
  unsigned char *p=(void *)(h+1);
#define APPEND(pointer,length) do{unsigned length_bytes=(length);memcpy(p,(pointer),length_bytes);p+=length_bytes;}while(0)
  APPEND(draw.program,draw.instructions*8);APPEND(draw.uniforms,draw.uniform_count*16);
  APPEND(draw.immediates,draw.immediate_count*16);APPEND(draw.vertices,draw.input_count*draw.vertex_count*16);
  APPEND(indices,count*2);
#undef APPEND
  last=offset;offset+=size;++f->draws;
 }
 f->bytes=offset;
 assert(!mbx_vgp_wire_encode(bytes,offset,actual,24000,&n));
 assert(!mbx_encode_gears_frame(expected,24000,&want,0));
 assert(n==want&&n==23831&&!memcmp(expected,actual,n*sizeof(*actual)));
 if(argc==2){FILE *out=fopen(argv[1],"wbx");assert(out&&fwrite(bytes,1,offset,out)==offset&&!fclose(out));}
 struct mbx_vgp_wire_draw *end=(void *)(bytes+last);unsigned saved=end->vertices;
 end->vertices=~0U;n=777;assert(mbx_vgp_wire_encode(bytes,offset,actual,24000,&n)<0&&n==777);end->vertices=saved;
 end->cull_mode=3;assert(mbx_vgp_wire_encode(bytes,offset,actual,24000,&n)<0&&n==777);end->cull_mode=1;
 unsigned *program=(void *)(end+1);saved=program[0];program[0]|=31;assert(mbx_vgp_wire_encode(bytes,offset,actual,24000,&n)<0&&n==777);program[0]=saved;
 unsigned short *indices=(void *)((unsigned char *)(end+1)+end->instructions*8+
    (end->uniforms+end->immediates+end->vertices*end->inputs)*16);
 unsigned short index=indices[end->triangles*3-1];indices[end->triangles*3-1]=end->vertices;
 assert(mbx_vgp_wire_encode(bytes,offset,actual,24000,&n)<0&&n==777);indices[end->triangles*3-1]=index;
 for(unsigned cut=0;cut<offset;cut+=97)assert(mbx_vgp_wire_encode(bytes,cut,actual,24000,&n)<0&&n==777);
 f->clear_color[0]=0x3f800000;assert(mbx_vgp_wire_encode(bytes,offset,actual,24000,&n)<0&&n==777);f->clear_color[0]=0;
 f->draws=0;f->bytes=48;assert(!mbx_vgp_wire_encode(bytes,48,actual,24000,&n)&&n==162);
 assert(!mbx_encode_gears_frame(expected,24000,&want,1)&&want==n&&!memcmp(expected,actual,n*sizeof(*actual)));
 printf("PASS %u-byte typed Mesa frame reproduces all 23831 verified commands; clear-only, truncation, invalid shader/index/count/culling/clear checks pass\n",offset);
}
