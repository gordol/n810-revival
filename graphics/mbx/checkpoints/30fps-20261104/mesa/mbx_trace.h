/* SPDX-License-Identifier: MIT
 * Opt-in per-thread stage accounting. Wall time and thread CPU time are
 * separate: off-CPU time is not assumed to be GPU execution. Windows from
 * different threads can overlap and must not be added as frame latency.
 */
#ifndef MBX_TRACE_H
#define MBX_TRACE_H
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <sys/syscall.h>
struct mbx_trace_stamp { uint64_t wall,cpu; };
struct mbx_trace_row {
 const char *name;uint64_t calls,units,wall,cpu,max_wall,begin,last_end;
};
static _Thread_local int mbx_trace_state=-1;
static _Thread_local long mbx_trace_tid;
static _Thread_local struct mbx_trace_row mbx_trace_rows[16];
static bool mbx_trace_enabled(void)
{
 if(mbx_trace_state<0){
  const char *v=getenv("N810_MBX_TRACE");mbx_trace_state=v&&!strcmp(v,"1");
  if(mbx_trace_state){mbx_trace_tid=syscall(SYS_gettid);fprintf(stderr,"N810_MBX_TRACE_CONFIG thread=%ld clocks=monotonic,thread_cpu version=1\n",mbx_trace_tid);}
 }
 return mbx_trace_state!=0;
}
static struct mbx_trace_stamp mbx_trace_begin(void)
{
 struct mbx_trace_stamp s={0};struct timespec t;
 if(!mbx_trace_enabled())return s;
 if(clock_gettime(CLOCK_MONOTONIC,&t))return s;
 s.wall=(uint64_t)t.tv_sec*1000000000+t.tv_nsec;
 if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&t)){s.wall=0;return s;}
 s.cpu=(uint64_t)t.tv_sec*1000000000+t.tv_nsec;return s;
}
static void mbx_trace_emit(struct mbx_trace_row *r)
{
  fprintf(stderr,"N810_MBX_TRACE thread=%ld stage=%s calls=%llu units=%llu wall_ns=%llu cpu_ns=%llu max_wall_ns=%llu begin_ns=%llu end_ns=%llu\n",
   mbx_trace_tid,r->name,(unsigned long long)r->calls,(unsigned long long)r->units,(unsigned long long)r->wall,
   (unsigned long long)r->cpu,(unsigned long long)r->max_wall,(unsigned long long)r->begin,(unsigned long long)r->last_end);
  const char *name=r->name;memset(r,0,sizeof(*r));r->name=name;
}
static void mbx_trace_flush(void)
{for(unsigned i=0;i<16;++i)if(mbx_trace_rows[i].calls)mbx_trace_emit(&mbx_trace_rows[i]);}
static void mbx_trace_end_n(const char *name,struct mbx_trace_stamp start,uint64_t units,unsigned window)
{
 if(!start.wall)return;
 struct mbx_trace_stamp end=mbx_trace_begin();
 if(end.wall<start.wall||end.cpu<start.cpu)return;
 struct mbx_trace_row *r=NULL;
 for(unsigned i=0;i<16;++i)if(!mbx_trace_rows[i].name||!strcmp(mbx_trace_rows[i].name,name)){r=&mbx_trace_rows[i];break;}
 if(!r)return;
 if(!r->name)r->name=name;
 if(!r->calls)r->begin=start.wall;
 uint64_t wall=end.wall-start.wall,cpu=end.cpu-start.cpu;
 ++r->calls;r->last_end=end.wall;r->units+=units;r->wall+=wall;r->cpu+=cpu;if(wall>r->max_wall)r->max_wall=wall;
 if(r->calls>=window){
  mbx_trace_emit(r);
 }
}
static void mbx_trace_end(const char *name,struct mbx_trace_stamp start,uint64_t units)
{mbx_trace_end_n(name,start,units,128);}
#endif
