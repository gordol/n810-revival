// SPDX-License-Identifier: MIT
// Bounded, opt-in host CPU sampler. Guest workers have no profiling timer.
#pragma once
#include <signal.h>
#include <sys/time.h>
#include <sys/syscall.h>
#include <ucontext.h>
#include <unistd.h>
#include <cstdint>
#include <time.h>
#include <cstdio>
#include <cstdlib>
namespace native_profile {
static volatile sig_atomic_t count;
static uint32_t samples[2048][3];
static volatile sig_atomic_t ready[2048];
static bool active=false,finished=false,armed=false;
static time_t start_after=0;
static void capture(int,siginfo_t*,void *context) {
 unsigned n=__sync_fetch_and_add(&count,1);
 if(n<2048){auto *u=static_cast<ucontext_t*>(context);samples[n][0]=u->uc_mcontext.arm_pc;samples[n][1]=u->uc_mcontext.arm_lr;samples[n][2]=syscall(SYS_gettid);__sync_synchronize();ready[n]=1;}
}
static void begin(){
 if(active||finished||!getenv("N810_SYMBIAN_CPU_PROFILE"))return;
 timespec now{};if(clock_gettime(CLOCK_MONOTONIC,&now))return;
 if(!armed){
  const char *value=getenv("N810_SYMBIAN_CPU_PROFILE_DELAY_S");
  char *end=nullptr;long delay=value?strtol(value,&end,10):0;
  if(value&&(!*value||*end||delay<0||delay>600)){finished=true;return;}
  start_after=now.tv_sec+delay;armed=true;
 }
 if(now.tv_sec<start_after)return;
 struct sigaction previous{},action{};itimerval old{},timer{{0,10000},{0,10000}};
 if(sigaction(SIGPROF,nullptr,&previous)||previous.sa_handler!=SIG_DFL||getitimer(ITIMER_PROF,&old)||old.it_value.tv_sec||old.it_value.tv_usec)return;
 action.sa_sigaction=capture;action.sa_flags=SA_SIGINFO|SA_RESTART;sigemptyset(&action.sa_mask);
 if(sigaction(SIGPROF,&action,nullptr))return;
 if(setitimer(ITIMER_PROF,&timer,nullptr)){sigaction(SIGPROF,&previous,nullptr);return;}
 active=true;printf("NATIVE_CPU_PROFILE_BEGIN interval_us=10000 max_samples=2048\n");
 FILE *f=fopen("/proc/self/maps","r");char line[512];if(f){while(fgets(line,sizeof line,f))printf("NATIVE_CPU_MAP %s",line);fclose(f);}
}
static void poll(bool finish=false){
 if(!active&&!finish)begin();
 if(!active||finished||(!finish&&count<2048))return;
 unsigned n=count<2048?count:2048;for(unsigned i=0;i<n;++i)if(!ready[i])return;
 itimerval stopped{};setitimer(ITIMER_PROF,&stopped,nullptr);finished=true;__sync_synchronize();
 printf("NATIVE_CPU_PROFILE_END samples=%u\n",n);for(unsigned i=0;i<n;++i)printf("NATIVE_CPU_SAMPLE %08x %08x %u\n",samples[i][0],samples[i][1],samples[i][2]);
}
}
