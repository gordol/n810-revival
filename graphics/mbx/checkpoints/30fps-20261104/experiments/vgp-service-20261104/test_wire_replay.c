/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "common/mbx_vgp_wire.h"
#include "common/mbx_vgp_transform.h"
static unsigned char baseline[524288] __attribute__((aligned(4)));
static unsigned char input[524288] __attribute__((aligned(4)));
static unsigned char snapshot[65536] __attribute__((aligned(4)));
static struct mbx_command reference[65536],replayed[65536],alternate[65536];
static struct mbx_vgp_shader_cache shader;
static struct mbx_vgp_wire_replay_cache cache;
static unsigned checks;
static void compare(unsigned bytes,unsigned capacity,struct mbx_command *output)
{
 unsigned a=0,b=0;
 int expected=mbx_vgp_wire_encode_cached(input,bytes,reference,capacity,&a,&shader);
 int actual=mbx_vgp_wire_encode_replay(input,bytes,output,capacity,&b,&shader,&cache);
 assert(expected==actual);
 if(!expected){assert(a==b);assert(!memcmp(reference,output,a*sizeof(*output)));}
 else assert(!cache.bytes);
 ++checks;
}
int main(int argc,char **argv)
{
 assert(argc==2);FILE *f=fopen(argv[1],"rb");assert(f);
 unsigned bytes=fread(baseline,1,sizeof(baseline),f);fclose(f);
 assert(bytes>=48&&bytes<=sizeof(snapshot));
 cache.snapshot=snapshot;cache.snapshot_capacity=sizeof(snapshot);
 memcpy(input,baseline,bytes);compare(bytes,65536,replayed);assert(cache.misses==1&&!cache.hits);
 compare(bytes,65536,replayed);assert(cache.hits==1);
 for(unsigned trial=0;trial<1000;++trial){
  memcpy(input,baseline,bytes);
  for(unsigned i=0;i<cache.draws;++i){
   struct mbx_vgp_wire_replay_record *r=cache.record+i;
   struct mbx_vgp_wire_draw *h=(void *)(input+r->wire_offset);
   unsigned *u=(void *)((unsigned char *)h+r->uniform_offset);
   for(unsigned j=0;j<r->uniform_words;++j)u[j]=(u[j]&0xff800000U)|((u[j]+trial*314159+j*63)&0x7fffff);
   for(unsigned j=0;j<6;++j)h->viewport[j]^=(trial+j)&0xffff;
  }
  unsigned hits=cache.hits;compare(bytes,65536,replayed);assert(cache.hits==hits+1);
 }
 /* Every wire word is independently changed: headers, shaders, uniforms,
  * viewport, immediates, attributes, indices, reserved fields and padding.
  * Compare successful output bytes and rejection behavior against full encode. */
 for(unsigned at=0;at<bytes;at+=4){
  memcpy(input,baseline,bytes);compare(bytes,65536,replayed);
  ((unsigned *)input)[at/4]^=0x00800001U;compare(bytes,65536,replayed);
 }
 memcpy(input,baseline,bytes);compare(bytes,65536,replayed);
 for(unsigned i=0;i<cache.draws;++i){
  struct mbx_vgp_wire_replay_record r=cache.record[i];
  if(r.uniform_words){
   ((unsigned *)(input+r.wire_offset+r.uniform_offset))[r.uniform_words-1]=0x7f800000;
   compare(bytes,65536,replayed);assert(!cache.bytes);
   memcpy(input,baseline,bytes);compare(bytes,65536,replayed);
  }
 }
 /* Changed output ownership and insufficient storage cannot reuse commands. */
 unsigned misses=cache.misses;compare(bytes,65536,alternate);assert(cache.misses==misses+1);
 compare(bytes,1,replayed);
 compare(bytes,65536,replayed);
 compare(bytes-1,65536,replayed);
 compare(bytes,65536,replayed);
 cache.bytes=0;cache.snapshot_capacity=1;
 compare(bytes,65536,replayed);assert(!cache.bytes);
 cache.snapshot=NULL;compare(bytes,65536,replayed);assert(!cache.bytes);
 /* Valid zero-uniform draw: transformation/color come from immediates. */
 cache=(struct mbx_vgp_wire_replay_cache){.snapshot=snapshot,.snapshot_capacity=sizeof(snapshot)};
 memcpy(input,baseline,48);
 struct mbx_vgp_wire_frame *frame=(void *)input;
 frame->draws=1;frame->bytes=312;
 struct mbx_vgp_wire_draw *draw=(void *)(input+48);memset(draw,0,264);
 *draw=(struct mbx_vgp_wire_draw){.bytes=264,.instructions=8,.immediates=5,.inputs=1,.vertices=3,.triangles=1,
  .viewport={0x43480000,0x43480000,0x43480000,0xc3480000,0x3f000000,0x3f000000}};
 unsigned *program=(void *)(draw+1);assert(mbx_vgp_transform(96,100,112,program,16)==8);
 unsigned *immediate=program+16;immediate[0]=immediate[5]=immediate[10]=immediate[15]=immediate[19]=0x3f800000;
 unsigned *vertices=immediate+20;
 for(unsigned i=0;i<3;++i){vertices[4*i]=i?0x3f000000:0xbf000000;vertices[4*i+1]=i==2?0x3f000000:0xbf000000;vertices[4*i+3]=0x3f800000;}
 unsigned short *indices=(void *)(vertices+12);indices[0]=0;indices[1]=1;indices[2]=2;
 compare(312,65536,replayed);assert(cache.bytes==312);
 unsigned hits=cache.hits;draw->viewport[0]^=1;compare(312,65536,replayed);assert(cache.hits==hits+1);
 /* Empty draw list still replays its validated clear commands. */
 frame->draws=0;frame->bytes=48;compare(48,65536,replayed);hits=cache.hits;
 compare(48,65536,replayed);assert(cache.hits==hits+1);
 printf("PASS %u differential command comparisons and rejection checks; hits=%u misses=%u\n",checks,cache.hits,cache.misses);
}
