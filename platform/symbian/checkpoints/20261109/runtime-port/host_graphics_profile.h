// SPDX-License-Identifier: MIT
#pragma once
#include <signal.h>
#include <time.h>
#include <sys/syscall.h>
#include <sys/resource.h>
#include <ucontext.h>
#include <unistd.h>
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
namespace host_graphics_profile {
// Only the selected graphics thread receives the timer signal. No allocation,
// logging, locks or GPU calls occur in its handler. Samples charge both user
// and system CPU; a syscall's charged time can appear at its return PC.
inline volatile sig_atomic_t count=0;
inline volatile sig_atomic_t requested=0;
inline void request_toggle(int){requested=!requested;}
inline uintptr_t pcs[4096],lrs[4096];
inline unsigned ticks[4096],r6[4096],r4[4096];
inline void capture(int,siginfo_t *info,void *context) {
 const unsigned n=count;
 if(n>=4096)return;
 auto *u=static_cast<ucontext_t*>(context);
#if defined(__arm__)
 pcs[n]=u->uc_mcontext.arm_pc;lrs[n]=u->uc_mcontext.arm_lr;
 r6[n]=u->uc_mcontext.arm_r6;r4[n]=u->uc_mcontext.arm_r4;
#elif defined(__x86_64__)
 pcs[n]=u->uc_mcontext.gregs[REG_RIP];lrs[n]=0;
#endif
 ticks[n]=1u+(info && info->si_overrun>0?unsigned(info->si_overrun):0u);
 count=n+1;
}
struct sampler {
 timer_t timer{};struct sigaction previous{};int signo=0;bool active=false,done=false;
 const char *trigger=nullptr;pid_t tid=0;rusage before{};
 int control_signo=0;struct sigaction previous_control{};bool signal_control=false;
 explicit sampler(const char *owner="graphics") {
  const char *selected=std::getenv("N810_SYMBIAN_HOST_CPU_OWNER");
  if(!selected)selected="graphics";
  if(!std::strcmp(selected,owner))trigger=std::getenv("N810_SYMBIAN_HOST_CPU_TRIGGER");
  if(trigger && std::getenv("N810_SYMBIAN_HOST_CPU_SIGNAL")) {
   control_signo=SIGRTMIN+7;
   if(control_signo>SIGRTMAX || sigaction(control_signo,nullptr,&previous_control) || previous_control.sa_handler!=SIG_DFL){trigger=nullptr;return;}
   struct sigaction action{};action.sa_handler=request_toggle;action.sa_flags=SA_RESTART;sigemptyset(&action.sa_mask);
   if(sigaction(control_signo,&action,nullptr)){trigger=nullptr;return;}
   signal_control=true;requested=0;
  }
 }
 void poll(){
  if(!trigger||done)return;
  const bool enabled=signal_control?requested!=0:access(trigger,F_OK)==0;
  if(active){if(count>=4096||!enabled)finish();return;}
  if(!enabled)return;
  signo=SIGRTMIN+6;
  if(signo>SIGRTMAX||sigaction(signo,nullptr,&previous)||previous.sa_handler!=SIG_DFL){done=true;std::fprintf(stderr,"HOST_CPU_PROFILE unavailable=signal\n");return;}
  struct sigaction action{};action.sa_sigaction=capture;action.sa_flags=SA_SIGINFO|SA_RESTART;sigemptyset(&action.sa_mask);
  if(sigaction(signo,&action,nullptr)){done=true;return;}
  tid=syscall(SYS_gettid);sigevent event{};event.sigev_notify=SIGEV_THREAD_ID;event.sigev_signo=signo;event._sigev_un._tid=tid;
  if(timer_create(CLOCK_THREAD_CPUTIME_ID,&event,&timer)){sigaction(signo,&previous,nullptr);done=true;std::fprintf(stderr,"HOST_CPU_PROFILE unavailable=timer\n");return;}
  for(int fd=0;fd<64;++fd){char path[64],target[512];std::snprintf(path,sizeof path,"/proc/self/fd/%d",fd);auto n=readlink(path,target,sizeof target-1);if(n>=0){target[n]=0;std::fprintf(stderr,"HOST_CPU_FD %d %s\n",fd,target);}}
  count=0;getrusage(RUSAGE_THREAD,&before);itimerspec interval{};interval.it_interval.tv_nsec=20000000;interval.it_value=interval.it_interval;
  if(timer_settime(timer,0,&interval,nullptr)){timer_delete(timer);sigaction(signo,&previous,nullptr);done=true;return;}
  active=true;std::fprintf(stderr,"HOST_CPU_PROFILE_BEGIN tid=%d interval_us=20000 max_samples=4096\n",tid);
 }
 void finish(){
  if(!active)return;
  sigset_t set,old;sigemptyset(&set);sigaddset(&set,signo);pthread_sigmask(SIG_BLOCK,&set,&old);
  timer_delete(timer);rusage after{};getrusage(RUSAGE_THREAD,&after);
  timespec zero{};while(sigtimedwait(&set,nullptr,&zero)>=0){}
  sigaction(signo,&previous,nullptr);active=false;done=true;
  auto us=[](timeval t){return int64_t(t.tv_sec)*1000000+t.tv_usec;};
  std::fprintf(stderr,"HOST_CPU_PROFILE_END tid=%d samples=%d user_us=%lld system_us=%lld\n",tid,int(count),(long long)(us(after.ru_utime)-us(before.ru_utime)),(long long)(us(after.ru_stime)-us(before.ru_stime)));
  for(int i=0;i<count;++i)std::fprintf(stderr,"HOST_CPU_SAMPLE %lx %lx %u %u %u\n",(unsigned long)pcs[i],(unsigned long)lrs[i],ticks[i],r6[i],r4[i]);
  FILE *f=std::fopen("/proc/self/maps","r");char line[512];if(f){while(std::fgets(line,sizeof line,f))std::fprintf(stderr,"HOST_CPU_MAP %s",line);std::fclose(f);}
  pthread_sigmask(SIG_SETMASK,&old,nullptr);
 }
 ~sampler(){finish();if(signal_control)sigaction(control_signo,&previous_control,nullptr);}
};
}
