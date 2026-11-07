/* SPDX-License-Identifier: MIT */
#ifdef NDEBUG
#undef NDEBUG
#endif
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "common/mbx_vgp_stream.h"
struct fake {unsigned used,drain,written,reads,barriers,pauses,fault_at,hold_reads;const struct mbx_command *expected;};
static unsigned status(void *p){struct fake *f=p;++f->reads;if(f->fault_at&&f->reads==f->fault_at)return 0x200;if(f->reads<=f->hold_reads){f->used=59;return 59<<16;}f->used=f->used>f->drain?f->used-f->drain:0;return f->used<<16;}
static void write_command(void *p,const struct mbx_command *c){struct fake *f=p;assert(f->used<59);assert(!memcmp(c,f->expected+f->written,sizeof(*c)));++f->used;++f->written;}
static void write_batch(void *p,const struct mbx_command *c,unsigned n){assert(n&&n<=42);for(unsigned i=0;i<n;++i)write_command(p,c+i);}
static void barrier(void *p){++((struct fake *)p)->barriers;}
static void relax_stream(void *p){(void)p;}
static void pause_stream(void *p){++((struct fake *)p)->pauses;}
int main(void){
 struct mbx_command commands[20000];for(unsigned i=0;i<20000;++i)commands[i]=(struct mbx_command){i%11?MBX_FIFO:MBX_POLYGON_CONTROL,i};
 struct fake f={0};struct mbx_vgp_stream_io io={.cookie=&f,.status=status,.write=write_command,.write_barrier=barrier,.pause=pause_stream};struct mbx_vgp_stream_result r;
 for(unsigned spin=0;spin<=32;spin+=16)for(unsigned mode=0;mode<2;++mode){
 io.spin_polls=spin;io.relax=relax_stream;
 io.write_batch=mode?write_batch:NULL;
 commands[19999].destination=MBX_FIFO;
 for(unsigned drain=1;drain<=59;++drain)for(unsigned used=0;used<=59;++used){
  f=(struct fake){.drain=drain,.used=used,.expected=commands};
  assert(!mbx_vgp_stream(&io,commands,20000,10,&r));assert(r.written==20000&&f.written==20000&&r.status_reads==f.reads);
 }
 f=(struct fake){.drain=59,.expected=commands};assert(!mbx_vgp_stream(&io,commands,20000,10,&r));assert(r.status_reads==477);
 f=(struct fake){.drain=59,.hold_reads=3,.expected=commands};assert(!mbx_vgp_stream(&io,commands,20000,10,&r));assert(r.status_reads==480&&r.spins==(spin?3:0)&&r.pauses==(spin?0:3));
 f=(struct fake){.used=59,.expected=commands};assert(mbx_vgp_stream(&io,commands,20000,10,&r)==-110&&r.written==0&&r.status_reads==10&&r.spins==(spin?10:0)&&r.pauses==(spin?0:10));
 f=(struct fake){.drain=59,.fault_at=2,.expected=commands};assert(mbx_vgp_stream(&io,commands,20000,10,&r)==-5&&r.written==42);
 f=(struct fake){.expected=commands};commands[19999].destination=2;assert(mbx_vgp_stream(&io,commands,20000,10,&r)==-22&&f.written==0&&f.reads==0);
 }
 f=(struct fake){.expected=commands};io.spin_polls=33;commands[19999].destination=MBX_FIFO;
 assert(mbx_vgp_stream(&io,commands,20000,10,&r)==-22&&!f.reads&&!f.written);
 puts("PASS 0/16/32 short polls, scalar and batch FIFO credits under 3540 drain/occupancy schedules; 20000 writes in 477 status reads when ready; faults and timeout retain accurate progress");
}
