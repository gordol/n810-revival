/* SPDX-License-Identifier: MIT
 * Opt-in statistical CPU sampling for the driver bring-up. Never enabled by
 * normal rendering. Records interrupted ARM PC/LR without instrumenting the app.
 */
#if defined(__arm__) && defined(__linux__)
#include <signal.h>
#include <sys/time.h>
#include <ucontext.h>
static volatile sig_atomic_t mbx_sample_count;
static uint32_t mbx_samples[1024][2];
static volatile sig_atomic_t mbx_sample_ready[1024];
static bool mbx_profile_started,mbx_profile_finished;
static void mbx_sample_signal(int signo,siginfo_t *info,void *context)
{
 (void)signo;(void)info;
 unsigned n=__sync_fetch_and_add(&mbx_sample_count,1);
 if(n<1024){
  const ucontext_t *u=context;
  mbx_samples[n][0]=u->uc_mcontext.arm_pc;
  mbx_samples[n][1]=u->uc_mcontext.arm_lr;
  __sync_synchronize();mbx_sample_ready[n]=1;
 }
}
static void mbx_profile_begin(void)
{
 if(mbx_profile_started||!getenv("N810_MBX_CPU_PROFILE"))return;
 mbx_profile_started=true;
 struct sigaction previous,action={0};struct itimerval old,timer={{0,10000},{0,10000}};
 if(sigaction(SIGPROF,NULL,&previous)||previous.sa_handler!=SIG_DFL||getitimer(ITIMER_PROF,&old)||old.it_value.tv_sec||old.it_value.tv_usec)return;
 action.sa_sigaction=mbx_sample_signal;action.sa_flags=SA_SIGINFO;sigemptyset(&action.sa_mask);
 if(sigaction(SIGPROF,&action,NULL))return;
 if(setitimer(ITIMER_PROF,&timer,NULL)){sigaction(SIGPROF,&previous,NULL);return;}
 fprintf(stderr,"N810_MBX_CPU_PROFILE_BEGIN interval_us=10000 samples=1024\n");
 FILE *f=fopen("/proc/self/maps","r");char line[512];
 if(f){while(fgets(line,sizeof(line),f))fprintf(stderr,"N810_MBX_CPU_MAP %s",line);fclose(f);}
}
static void mbx_profile_poll(void)
{
 if(!mbx_profile_started||mbx_profile_finished||mbx_sample_count<1024)return;
 for(unsigned i=0;i<1024;++i)if(!mbx_sample_ready[i])return;
 __sync_synchronize();
 struct itimerval stopped={0};setitimer(ITIMER_PROF,&stopped,NULL);mbx_profile_finished=true;
 fprintf(stderr,"N810_MBX_CPU_PROFILE_END samples=1024\n");
 for(unsigned i=0;i<1024;++i)fprintf(stderr,"N810_MBX_CPU_SAMPLE %08x %08x\n",mbx_samples[i][0],mbx_samples[i][1]);
}
#else
static void mbx_profile_begin(void){}
static void mbx_profile_poll(void){}
#endif
