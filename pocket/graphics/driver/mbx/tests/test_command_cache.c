/* SPDX-License-Identifier: MIT. Independent full encoding is the oracle. */
#define main prepared_fixture_main
#include "test_prepared.c"
#undef main
#include "mbx_command_cache.h"
#include <time.h>
static struct mbx_command_cache compiled;
static unsigned char large[1048576];
static unsigned native_frame(unsigned kind,unsigned draws)
{
 unsigned bytes=make_frame(kind!=0),old=kind?8240:48;
 unsigned draw_bytes=bytes-old;
 memcpy(large,(unsigned char*)wire+old,draw_bytes);
 memmove((unsigned char*)wire+64,large,draw_bytes);
 memset((unsigned char*)wire+48,0,16);
 struct mbx_vgp_wire_frame *f=(void*)wire;
 f->version=10;f->width=f->height=128;f->bytes=64+draw_bytes;
 if(kind==1){unsigned index;
  struct mbx_window_token t={17,19,2};
  assert(!mbx_wire_resource_append_window_layout(wire,sizeof wire,t,2,&index));
 }else if(kind==2){unsigned index;static unsigned char pixels[2304];
  assert(!mbx_wire_resource_append_linear(wire,sizeof wire,pixels,16,16,sizeof pixels,&index));
 }
 struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(wire,f->bytes,&r));
 assert(r.draw_offset+draws*draw_bytes<=sizeof wire);
 for(unsigned i=1;i<draws;i++)memcpy((unsigned char*)wire+r.draw_offset+i*draw_bytes,large,draw_bytes);
 f->draws=draws;f->bytes=r.draw_offset+draws*draw_bytes;return f->bytes;
}
static void parity(unsigned bytes)
{
 unsigned n,m;
 assert(!mbx_command_cache_encode(&compiled,wire,bytes,command,65536,&n,0));
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&m));
 assert(n==m&&!memcmp(command,reference,n*sizeof(*command)));
}
static void correctness(void)
{
 for(unsigned kind=0;kind<3;kind++){
  unsigned bytes=native_frame(kind,8),hit=compiled.hits;
  parity(bytes);parity(bytes);assert(compiled.hits==hit+1);
  /* Consumer post-encode mutations cannot poison a stored command. */
  command[0].value^=255;parity(bytes);assert(compiled.hits==hit+2);
  if(kind){
   if(kind==1){struct mbx_wire_resource *r=(void*)((unsigned char*)wire+64);r->bytes++;r->reserved++;
    /* A compilation hit is not a valid surface handle. Actual service lookup
     * rejects the new generation until a producer has published it. */
    struct mbx_window_state windows={.session=17,.layout=2};
    struct mbx_window_token stale={r->reserved,r->bytes,r->offset};
    assert(mbx_window_lookup(&windows,stale));
   }else{struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(wire,bytes,&r));
    memset((unsigned char*)wire+r.data_offset,0x75,r.bytes);}
   parity(bytes);assert(compiled.hits==hit+3);
  }
  struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(wire,bytes,&r));
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+r.draw_offset);
  unsigned *u=(void*)((unsigned char*)(d+1)+8*d->instructions);
  /* Valid dynamic uniforms/viewports patch only recorded command values. */
  unsigned dynamic_hits=compiled.hits;u[16]=0x3f000000;parity(bytes);assert(compiled.hits==dynamic_hits+1);
  d->viewport[0]=0x42800000;parity(bytes);assert(compiled.hits==dynamic_hits+2);
  memcpy(before,command,sizeof command);unsigned count=73;
  u[16]=0x7fc00000;
  assert(mbx_command_cache_encode(&compiled,wire,bytes,command,65536,&count,0));
  /* Bad draw may write an unsubmitted prefix, but must never cache/accept it. */
  u[16]=0x3f000000;parity(bytes);
  unsigned hits=compiled.hits;memcpy(before,command,sizeof command);count=73;
  assert(mbx_command_cache_encode(&compiled,wire,bytes,command,1,&count,0));
  assert(count==73&&compiled.hits==hits&&!memcmp(before,command,sizeof command));
 }
 /* Four alternating passes remain useful instead of evicting each other.
  * Every immutable shader/index/attribute byte still participates in equality. */
 memset(&compiled,0,sizeof compiled);
 static unsigned frames[4][8192];unsigned sizes[4];
 for(unsigned slot=0;slot<4;slot++){
  sizes[slot]=native_frame(slot%3,8);wire[6]=slot?0x3e800000+slot*0x100000:0;
  memcpy(frames[slot],wire,sizes[slot]);parity(sizes[slot]);
 }
 for(unsigned step=0;step<128;step++){
  unsigned slot=step%4;memcpy(wire,frames[slot],sizes[slot]);
  struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(wire,sizes[slot],&r));
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+r.draw_offset);
  unsigned *u=(void*)((unsigned char*)(d+1)+8*d->instructions);
  d->viewport[0]=0x42000000+step*0x1000;u[16]=0x3e800000+step*0x1000;
  unsigned hits=compiled.hits;parity(sizes[slot]);assert(compiled.hits==hits+1);
 }
 /* Scissor coordinates are geometry in the compiled tile mask. They cannot
  * be treated as an ordinary dynamic uniform. */
 unsigned bytes=native_frame(0,1);
 struct mbx_vgp_wire_draw *scissor=(void*)((unsigned char*)wire+64);
 scissor->reserved|=128;
 unsigned *clip=(void*)((unsigned char*)(scissor+1)+8*scissor->instructions+16*(scissor->uniforms-1));
 clip[0]=clip[1]=0;clip[2]=clip[3]=128;parity(bytes);
 unsigned misses=compiled.misses;clip[2]=64;parity(bytes);assert(compiled.misses==misses+1);
 /* Key and command storage caps fall back to the full encoder. */
 native_frame(0,1);struct mbx_vgp_wire_frame *big=(void*)large;
 memcpy(large,wire,64);unsigned draw_bytes=((struct mbx_vgp_wire_draw*)((unsigned char*)wire+64))->bytes;
 for(unsigned i=0;i<128;i++)memcpy(large+64+i*draw_bytes,(unsigned char*)wire+64,draw_bytes);
 big->draws=128;big->bytes=64+128*draw_bytes;unsigned n_big,m_big,bypasses=compiled.bypasses;
 assert(!mbx_command_cache_encode(&compiled,large,big->bytes,command,65536,&n_big,0));
 assert(compiled.bypasses==bypasses+1);
 assert(!mbx_vgp_wire_encode(large,big->bytes,reference,65536,&m_big)&&n_big==m_big&&!memcmp(command,reference,n_big*sizeof(*command)));
 bytes=native_frame(0,1);
 struct mbx_vgp_wire_draw *dense=(void*)((unsigned char*)wire+64);
 unsigned short *indices=(void*)((unsigned char*)(dense+1)+8*dense->instructions+16*dense->uniforms+16*dense->inputs*dense->vertices);
 for(unsigned i=0;i<256;i++){indices[3*i]=0;indices[3*i+1]=1;indices[3*i+2]=2;}
 dense->triangles=256;dense->bytes=(unsigned)((unsigned char*)(indices+768)-((unsigned char*)dense));
 draw_bytes=dense->bytes;
 for(unsigned i=1;i<8;i++)memcpy((unsigned char*)wire+64+i*draw_bytes,dense,draw_bytes);
 ((struct mbx_vgp_wire_frame*)wire)->draws=8;bytes=64+8*draw_bytes;((struct mbx_vgp_wire_frame*)wire)->bytes=bytes;
 bypasses=compiled.bypasses;
 assert(!mbx_command_cache_encode(&compiled,wire,bytes,command,65536,&n_big,0)&&compiled.bypasses==bypasses+1);
 assert(!mbx_vgp_wire_encode(wire,bytes,reference,65536,&m_big)&&n_big==m_big&&!memcmp(command,reference,n_big*sizeof(*command)));
 /* Differential mutations cover admission as well as successful commands. */
 unsigned mutation_bytes=native_frame(1,4),seed=0x81234;
 static unsigned mutation_source[8192];memcpy(mutation_source,wire,mutation_bytes);
 for(unsigned step=0;step<1024;step++){
  memcpy(wire,mutation_source,mutation_bytes);parity(mutation_bytes);
  seed=seed*1664525U+1013904223U;unsigned offset=seed%mutation_bytes;
  seed=seed*1664525U+1013904223U;((unsigned char*)wire)[offset]^=(unsigned char)(1U<<(seed%8));
  unsigned n=0,m=0;
  int cached=mbx_command_cache_encode(&compiled,wire,mutation_bytes,command,65536,&n,0);
  int full=mbx_vgp_wire_encode(wire,mutation_bytes,reference,65536,&m);
  assert(cached==full);if(!full)assert(n==m&&!memcmp(command,reference,n*sizeof(*command)));
 }
 /* Raw two-plane pixels change every job; their fixed mask-init compilation
  * is still reusable. Neither plane is copied into this CPU command cache. */
 memset(large,0,sizeof large);
 struct mbx_vgp_wire_frame *f=(void*)large;
 *f=(struct mbx_vgp_wire_frame){.magic=MBX_VGP_WIRE_MAGIC,.version=10,.bytes=80+128*128*8,
  .width=128,.height=128,.clear_depth=0x3f800000};
 unsigned *table=(void*)(large+48);table[0]=1;table[1]=128*128*8;
 struct mbx_wire_resource *resource=(void*)(large+64);*resource=(struct mbx_wire_resource){9,128*128*8,0,8};
 unsigned n,m;assert(!mbx_command_cache_encode(&compiled,large,f->bytes,command,65536,&n,0));
 unsigned hits=compiled.hits;memset(large+80,0xf7,128*128*8);
 assert(!mbx_command_cache_encode(&compiled,large,f->bytes,command,65536,&n,0)&&compiled.hits==hits+1);
 assert(!mbx_vgp_wire_encode(large,f->bytes,reference,65536,&m)&&n==m&&!memcmp(command,reference,n*sizeof(*command)));
 resource->reserved=16;assert(mbx_command_cache_encode(&compiled,large,f->bytes,command,65536,&n,0));
 resource->reserved=8;
 f->clear_depth=0;assert(mbx_command_cache_encode(&compiled,large,f->bytes,command,65536,&n,0));
 puts("command cache: full command parity; token and texture updates; private output; dynamic uniform/viewport patches; malformed/capacity failures; raw channel planes excluded from key");
}
static void benchmark(unsigned iterations)
{
 unsigned bytes=native_frame(1,16),n;struct mbx_vgp_shader_cache shader={0};
 clock_t a=clock();
 for(unsigned i=0;i<iterations;i++){
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+80);
  d->viewport[0]=0x42800000+(i&255U)*0x1000;
  assert(!mbx_vgp_wire_encode_cached(wire,bytes,command,65536,&n,&shader));
 }
 clock_t b=clock();memset(&compiled,0,sizeof compiled);
 for(unsigned i=0;i<iterations;i++){
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+80);
  d->viewport[0]=0x42800000+(i&255U)*0x1000;
  assert(!mbx_command_cache_encode(&compiled,wire,bytes,command,65536,&n,&shader));
 }
 clock_t c=clock();
 printf("{\"iterations\":%u,\"draws\":16,\"commands\":%u,\"baseline_cpu_ns\":%.0f,\"cached_cpu_ns\":%.0f,\"hits\":%u,\"cache_bytes\":%zu}\n",
  iterations,n,(b-a)*1e9/CLOCKS_PER_SEC,(c-b)*1e9/CLOCKS_PER_SEC,compiled.hits,sizeof compiled);
}
#ifndef MBX_COMMAND_CACHE_NO_MAIN
int main(int argc,char **argv){correctness();if(argc>1)benchmark((unsigned)strtoul(argv[1],0,10));return 0;}
#endif
