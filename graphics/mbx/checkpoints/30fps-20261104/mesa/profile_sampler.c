/* SPDX-License-Identifier: MIT
 * Bounded native telemetry sampler. No Python paging in the measured loop.
 * Usage: profile_sampler OUTPUT COUNT PERIOD_MS PID...
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
#include <fcntl.h>
#include <errno.h>
static uint64_t stamp(clockid_t c){struct timespec t;if(clock_gettime(c,&t))exit(3);return (uint64_t)t.tv_sec*1000000000+t.tv_nsec;}
static int read_text(const char *path,char *b,size_t n)
{int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)return -1;ssize_t k=read(fd,b,n-1);int e=errno;close(fd);errno=e;if(k<0)return -1;b[k]=0;return 0;}
static uint64_t number(const char *path){char b[128];return read_text(path,b,sizeof(b))?0:strtoull(b,NULL,10);}
static uint64_t display_count(void)
{
 FILE *f=fopen("/proc/interrupts","r");if(!f)return 0;char b[512];unsigned long long n=0;
 while(fgets(b,sizeof(b),f))if(strstr(b,"OMAP DISPC")){char *colon=strchr(b,':');if(colon)n=strtoull(colon+1,NULL,10);break;}
 fclose(f);return n;
}
static void process(FILE *f,long pid,int *first)
{
 char path[80],b[4096];snprintf(path,sizeof(path),"/proc/%ld/stat",pid);
 if(read_text(path,b,sizeof(b)))return;
 uint64_t at=stamp(CLOCK_MONOTONIC);char *p=strrchr(b,')');if(!p)return;p+=2;
 uint64_t values[22]={0};unsigned i=0;char *save=NULL;
 for(char *t=strtok_r(p," ", &save);t&&i<22;t=strtok_r(NULL," ",&save),++i)values[i]=strtoull(t,NULL,10);
 if(i<20)return;
 fprintf(f,"%s\"%ld\":{\"ticks\":%llu,\"start\":\"%llu\",\"minor_faults\":%llu,\"major_faults\":%llu,\"sample_ns\":%llu}",*first?"":",",pid,
  (unsigned long long)(values[11]+values[12]),(unsigned long long)values[19],(unsigned long long)values[7],(unsigned long long)values[9],(unsigned long long)at);*first=0;
}
static void pressure(FILE *f,const char *path,const char *key)
{
 char b[512];if(read_text(path,b,sizeof(b)))return;char *a=strstr(b,"total=");if(!a)return;
 uint64_t some=strtoull(a+6,NULL,10);a=strstr(a+6,"total=");uint64_t full=a?strtoull(a+6,NULL,10):0;
 fprintf(f,",\"%s_some_us\":%llu,\"%s_full_us\":%llu",key,(unsigned long long)some,key,(unsigned long long)full);
}
int main(int argc,char **argv)
{
 if(argc<5)return 2;
 char *end_count,*end_period;
 unsigned long count=strtoul(argv[2],&end_count,10),period=strtoul(argv[3],&end_period,10);
 if(*end_count||*end_period)return 2;
 if(!count||count>120||period<10||period>60000||argc>40)return 2;
 long pids[36];for(int i=4;i<argc;++i){char *end;pids[i-4]=strtol(argv[i],&end,10);if(*end||pids[i-4]<=0)return 2;}
 FILE *output=fopen(argv[1],"wx");if(!output)return 3;
 char *buffer=NULL;size_t length=0;FILE *f=open_memstream(&buffer,&length);
 if(!f){fclose(output);return 3;}
 /* Keep telemetry in RAM until sampling finishes: no periodic disk writes. */
 uint64_t due=stamp(CLOCK_MONOTONIC);
 for(unsigned sample=0;sample<count;++sample){
  struct timespec deadline={(time_t)(due/1000000000),(long)(due%1000000000)};
  int e;while((e=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&deadline,NULL))==EINTR){}
  if(e){fclose(f);return 4;}
  uint64_t began=stamp(CLOCK_MONOTONIC),cpu=stamp(CLOCK_THREAD_CPUTIME_ID);
  fprintf(f,"{\"monotonic_ns\":%llu,\"processes\":{",(unsigned long long)began);int first=1;
  for(int i=4;i<argc;++i)process(f,pids[i-4],&first);
  process(f,(long)getpid(),&first);
  uint64_t before=stamp(CLOCK_MONOTONIC),jobs=number("/sys/module/n810_mbx_gpu_probe/parameters/gpu_service_jobs"),after=stamp(CLOCK_MONOTONIC);
  fprintf(f,"},\"gpu_jobs\":%llu,\"gpu_sample_ns\":%llu,\"gpu_sample_uncertainty_ns\":%llu",(unsigned long long)jobs,(unsigned long long)((before+after)/2),(unsigned long long)((after-before)/2));
  uint64_t display=display_count();fprintf(f,",\"display_interrupts\":%llu,\"display_sample_ns\":%llu",(unsigned long long)display,(unsigned long long)stamp(CLOCK_MONOTONIC));
  char b[4096];unsigned long long t[8]={0};if(!read_text("/proc/stat",b,sizeof(b)))sscanf(b,"cpu %llu %llu %llu %llu %llu %llu %llu %llu",&t[0],&t[1],&t[2],&t[3],&t[4],&t[5],&t[6],&t[7]);
  fprintf(f,",\"cpu_total_ticks\":[%llu,%llu,%llu,%llu,%llu,%llu,%llu,%llu],\"cpu_khz\":%llu",t[0],t[1],t[2],t[3],t[4],t[5],t[6],t[7],(unsigned long long)number("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq"));
  pressure(f,"/proc/pressure/memory","memory_pressure");pressure(f,"/proc/pressure/io","io_pressure");
  fprintf(f,",\"collection_ns\":%llu,\"collection_cpu_ns\":%llu}\n",(unsigned long long)(stamp(CLOCK_MONOTONIC)-began),(unsigned long long)(stamp(CLOCK_THREAD_CPUTIME_ID)-cpu));
  if(fflush(f)){fclose(f);return 5;}due+=(uint64_t)period*1000000;
 }
 if(fclose(f)){fclose(output);free(buffer);return 5;}
 int failed=fwrite(buffer,1,length,output)!=length;free(buffer);
 if(fclose(output))failed=1;
 return failed?5:0;
}
