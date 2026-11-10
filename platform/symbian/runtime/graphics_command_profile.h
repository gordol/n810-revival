#pragma once
#include <time.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
// Graphics-owner-thread only. Wall time includes driver waits; CPU time does not.
// Fixed storage, no per-command output, disabled unless explicitly requested.
namespace n810_command_profile {
struct bucket { uint64_t calls=0, wall=0, cpu=0; };
inline uint64_t now(clockid_t clock) { timespec t{}; if(clock_gettime(clock,&t)) return 0; return uint64_t(t.tv_sec)*1000000000ULL+t.tv_nsec; }
struct counters {
 bucket values[128]{}; uint64_t last=0;
 void report(uint64_t stamp) {
  for(unsigned i=0;i<128;++i) if(values[i].calls) {
   auto &v=values[i];
   std::fprintf(stderr,"graphics_opcode opcode=%u calls=%llu wall_us=%llu cpu_us=%llu\n",i,(unsigned long long)v.calls,(unsigned long long)(v.wall/1000),(unsigned long long)(v.cpu/1000));
   v={};
  }
  last=stamp;
 }
};
inline counters &state() { static thread_local counters s; return s; }
struct scope {
 bool enabled; unsigned opcode; uint64_t wall=0,cpu=0;
 explicit scope(unsigned op):opcode(op<127?op:127) {
  static const bool active=std::getenv("N810_SYMBIAN_COMMAND_PROFILE")!=nullptr;
  enabled=active; if(!enabled)return;
  auto &s=state(); auto stamp=now(CLOCK_MONOTONIC);
  if(!s.last)s.last=stamp;
  if(stamp-s.last>=5000000000ULL)s.report(stamp);
  wall=now(CLOCK_MONOTONIC);cpu=now(CLOCK_THREAD_CPUTIME_ID);
 }
 void finish() { if(!enabled)return;enabled=false;auto cpu_end=now(CLOCK_THREAD_CPUTIME_ID),wall_end=now(CLOCK_MONOTONIC);auto &v=state().values[opcode];++v.calls;if(cpu_end>=cpu)v.cpu+=cpu_end-cpu;if(wall_end>=wall)v.wall+=wall_end-wall; }
 ~scope() { finish(); }
};
}
