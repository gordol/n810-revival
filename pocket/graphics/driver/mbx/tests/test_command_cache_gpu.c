/* SPDX-License-Identifier: MIT */
/* Explicit offscreen device test. Requires a separately guarded GPU service.
 * Never loads a module, owns the display, sends input, or changes clock policy.
 * Compare identical runs with gpu_command_reuse=0/1. Readback is outside timing.
 */
#define _POSIX_C_SOURCE 200809L
#define MBX_COMMAND_CACHE_NO_MAIN
#include "test_command_cache.c"
#include <fcntl.h>
#include <unistd.h>
#include <sys/resource.h>
static unsigned char pixels[128*128*4];
static void save_pixels(int fd,const char *prefix,const char *suffix)
{
 unsigned at=0;
 while(at<sizeof pixels){ssize_t n=read(fd,pixels+at,sizeof pixels-at);assert(n>0);at+=(unsigned)n;}
 char path[512];assert(snprintf(path,sizeof path,"%s-%s.rgba",prefix,suffix)<(int)sizeof path);
 FILE *out=fopen(path,"wb");assert(out);assert(fwrite(pixels,1,sizeof pixels,out)==sizeof pixels);assert(!fclose(out));
}
static double seconds(struct timespec t){return t.tv_sec+t.tv_nsec*1e-9;}
int main(int argc,char **argv)
{
 if(argc!=3){fprintf(stderr,"usage: %s OUTPUT_PREFIX FRAME_COUNT (guarded service must already be running)\n",argv[0]);return 2;}
 unsigned frames=(unsigned)strtoul(argv[2],0,10);assert(frames>=32&&frames<=5000);
 int fd=open("/dev/n810-mbx-render",O_RDWR|O_CLOEXEC);assert(fd>=0);
 unsigned bytes=native_frame(0,16),at=64;
 for(unsigned i=0;i<16;i++){
  struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+at);
  d->viewport[0]=d->viewport[1]=d->viewport[2]=0x42800000;d->viewport[3]=0xc2800000;
  at+=d->bytes;
 }
 assert(write(fd,wire,bytes)==bytes);save_pixels(fd,argv[1],"first");
 struct timespec a,b;clock_t ca=clock();assert(!clock_gettime(CLOCK_MONOTONIC,&a));
 for(unsigned step=0;step<frames;step++){
  at=64;
  for(unsigned i=0;i<16;i++){
   struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+at);
   unsigned *uniform=(void*)((unsigned char*)(d+1)+8*d->instructions);
   uniform[16]=0x3e800000+(step%128)*0x10000;
   at+=d->bytes;
  }
  assert(write(fd,wire,bytes)==bytes);
 }
 assert(!clock_gettime(CLOCK_MONOTONIC,&b));clock_t cb=clock();
 save_pixels(fd,argv[1],"last");assert(!close(fd));
 struct rusage use;assert(!getrusage(RUSAGE_SELF,&use));double elapsed=seconds(b)-seconds(a);
 long rss=0,faults=0;
#ifdef __linux__
 rss=use.ru_maxrss;faults=use.ru_majflt;
#endif
 printf("{\"frames\":%u,\"width\":128,\"height\":128,\"draws\":16,\"seconds\":%.9f,\"gpu_completed_fps\":%.6f,\"cpu_ms_per_frame\":%.6f,\"peak_rss_kib\":%ld,\"major_faults\":%ld,\"visible_fps\":null,\"timed_readbacks\":0}\n",
  frames,elapsed,frames/elapsed,(cb-ca)*1000.0/CLOCKS_PER_SEC/frames,rss,faults);
 return 0;
}
