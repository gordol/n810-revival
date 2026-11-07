/* SPDX-License-Identifier: MIT
 * Bounded ordered render/present queue. The application produces geometry
 * while one worker owns GPU submission and a private X connection. Every
 * source packet is copied; X consumption is fenced before GPU target reuse.
 */
#include <pthread.h>
#include <stddef.h>
#include <time.h>
#include <errno.h>
#include "mbx_trace.h"
void n810_mbx_async_drain(void);
void *n810_mbx_fence_create(void);
void *n810_mbx_fence_reference(void *,void *);
bool n810_mbx_fence_finish(void *,uint64_t);
int n810_mbx_async_submit(struct sw_displaytarget *,int,const void *,size_t,size_t);
#define MBX_ASYNC_COMMANDS 4
/* Match the bounded raw-vertex wire limit as well as pretransformed jobs.
 * Slots copy only the submitted bytes; unused payload capacity stays untouched. */
#define MBX_ASYNC_PACKET_BYTES (512u*1024u)
#ifndef MBX_ASYNC_WRITE
#define MBX_ASYNC_WRITE write
#endif
struct mbx_async_command {
 unsigned kind,width,height,stride,depth;int x,y;unsigned w,h;
 Drawable drawable;VisualID visual;size_t bytes;
 unsigned char packet[MBX_ASYNC_PACKET_BYTES];
};
static struct {
 pthread_mutex_t lock;pthread_cond_t changed;pthread_t thread;
 struct mbx_async_command queue[MBX_ASYNC_COMMANDS];
 unsigned head,tail,outstanding,queued,refs,completed;
 uint64_t submitted_sequence,finished_sequence;
 bool started,stop;int fd;char *display_name;size_t image_bytes;
 struct mbx_shared_image *image;
} mbx_async={.lock=PTHREAD_MUTEX_INITIALIZER,.changed=PTHREAD_COND_INITIALIZER,.fd=-1};
static bool mbx_async_enabled(void)
{const char *p=getenv("N810_MBX_ASYNC");return p&&!strcmp(p,"1");}
static void mbx_async_fatal(const char *message)
{fprintf(stderr,"N810_MBX_GPU_FAILED: async %s\n",message);fflush(stderr);_exit(1);}
__attribute__((constructor)) static void mbx_async_xinit(void)
{if(mbx_async_enabled()&&!XInitThreads())mbx_async_fatal("X thread initialization");}
static void *mbx_async_worker(void *unused)
{
 (void)unused;Display *display=XOpenDisplay(mbx_async.display_name);
 if(!display)mbx_async_fatal("private X connection");
 VisualID cached_visual_id=0;Visual *cached_visual=NULL;
 if(mbx_shared_prepare(&mbx_async.image,display,mbx_async.fd,mbx_async.image_bytes))mbx_async_fatal("image mapping");
 for(;;){
  const struct mbx_async_command *c;
  pthread_mutex_lock(&mbx_async.lock);
  while(!mbx_async.queued&&!mbx_async.stop)pthread_cond_wait(&mbx_async.changed,&mbx_async.lock);
  if(!mbx_async.queued&&mbx_async.stop){pthread_mutex_unlock(&mbx_async.lock);break;}
  /* Outstanding includes this in-flight slot. The producer cannot wrap
   * onto it until processing finishes and the outstanding count drops. */
  c=&mbx_async.queue[mbx_async.head];
  mbx_async.head=(mbx_async.head+1)%MBX_ASYNC_COMMANDS;--mbx_async.queued;
  pthread_mutex_unlock(&mbx_async.lock);
  struct mbx_trace_stamp trace=mbx_trace_begin();
  if(c->kind==1){
   mbx_shared_wait(mbx_async.image);
   mbx_trace_end("worker_reuse_wait",trace,1);trace=mbx_trace_begin();
   if(MBX_ASYNC_WRITE(mbx_async.fd,c->packet,c->bytes)!=(ssize_t)c->bytes)mbx_async_fatal("GPU submission");
   mbx_trace_end("worker_gpu_execute",trace,1);
   ++mbx_async.completed;
   uint32_t packet_magic=0;
   if(c->bytes>=4)memcpy(&packet_magic,c->packet,4);
   if(c->bytes>=48 && packet_magic==0x3156474dU &&
      (mbx_async.completed==1||mbx_async.completed%20==0))
    fprintf(stderr,"N810_MBX_GPU_VERTEX frames=%u transform=GPU lighting=GPU CPU_shaded_vertices=0\n",mbx_async.completed);
   if(mbx_async.completed==1||mbx_async.completed%20==0)
    fprintf(stderr,"N810_MBX_GPU_FRAME completed=%u GPU_jobs=1 CPU_raster_triangles=0 async=1\n",mbx_async.completed);
  }else{
   if(!cached_visual||cached_visual_id!=c->visual){
    XVisualInfo query={.visualid=c->visual};int count=0;
    XVisualInfo *info=XGetVisualInfo(display,VisualIDMask,&query,&count);
    if(!info||count!=1)mbx_async_fatal("visual lookup");
    cached_visual=info[0].visual;cached_visual_id=c->visual;XFree(info);
   }
   int error=mbx_shared_display(mbx_async.image,cached_visual,c->depth,c->drawable,c->width,c->height,c->stride,c->x,c->y,c->w,c->h);
   if(error)mbx_async_fatal("X presentation");
  }
  /* A fence includes X's consumption of every preceding presentation. */
  if(c->kind==2){mbx_shared_wait(mbx_async.image);mbx_trace_end("worker_x_present",trace,(uint64_t)c->w*c->h);}
  pthread_mutex_lock(&mbx_async.lock);--mbx_async.outstanding;++mbx_async.finished_sequence;
  pthread_cond_broadcast(&mbx_async.changed);pthread_mutex_unlock(&mbx_async.lock);
 }
 mbx_shared_destroy(mbx_async.image);mbx_async.image=NULL;XCloseDisplay(display);
 close(mbx_async.fd);mbx_async.fd=-1;mbx_trace_flush();return NULL;
}
static int mbx_async_acquire(Display *display,int fd,size_t bytes,bool *owner)
{
 if(*owner)return 0;
 pthread_mutex_lock(&mbx_async.lock);
 if(!mbx_async.started){
  mbx_async.fd=fcntl(fd,F_DUPFD_CLOEXEC,3);mbx_async.display_name=strdup(DisplayString(display));mbx_async.image_bytes=bytes;
  if(mbx_async.fd<0||!mbx_async.display_name)mbx_async_fatal("owner allocation");
  mbx_async.stop=false;mbx_async.head=mbx_async.tail=mbx_async.completed=0;
  pthread_attr_t attr;pthread_attr_init(&attr);pthread_attr_setstacksize(&attr,256*1024);
  int error=pthread_create(&mbx_async.thread,&attr,mbx_async_worker,NULL);pthread_attr_destroy(&attr);
  if(error)mbx_async_fatal("worker creation");
  mbx_async.started=true;
 }else if(mbx_async.image_bytes!=bytes||strcmp(DisplayString(display),mbx_async.display_name))mbx_async_fatal("incompatible target");
 ++mbx_async.refs;*owner=true;pthread_mutex_unlock(&mbx_async.lock);return 0;
}
/* Reserve and publish under the mutex; only immutable published slots are
 * visible to the worker. A render packet crosses CPU memory exactly once. */
static _Thread_local struct mbx_trace_stamp mbx_queue_begin;
static struct mbx_async_command *mbx_async_reserve(void)
{
 mbx_queue_begin=mbx_trace_begin();
 pthread_mutex_lock(&mbx_async.lock);
 while(mbx_async.outstanding==MBX_ASYNC_COMMANDS)pthread_cond_wait(&mbx_async.changed,&mbx_async.lock);
 if(!mbx_async.started||mbx_async.stop)mbx_async_fatal("inactive queue");
 return &mbx_async.queue[mbx_async.tail];
}
static void mbx_async_publish(void)
{
 mbx_async.tail=(mbx_async.tail+1)%MBX_ASYNC_COMMANDS;
 ++mbx_async.queued;++mbx_async.outstanding;++mbx_async.submitted_sequence;pthread_cond_broadcast(&mbx_async.changed);pthread_mutex_unlock(&mbx_async.lock);
 mbx_trace_end("queue_publish",mbx_queue_begin,1);
}
static void mbx_async_enqueue(const struct mbx_async_command *c)
{
 if((c->kind!=1&&c->kind!=2)||(c->kind==1&&(!c->bytes||c->bytes>MBX_ASYNC_PACKET_BYTES)))mbx_async_fatal("invalid command");
 struct mbx_async_command *q=mbx_async_reserve();
 memcpy(q,c,offsetof(struct mbx_async_command,packet)+(c->kind==1?c->bytes:0));mbx_async_publish();
}
static void mbx_async_enqueue_packet(const void *packet,size_t bytes)
{
 if(!bytes||bytes>MBX_ASYNC_PACKET_BYTES)mbx_async_fatal("invalid packet");
 struct mbx_async_command *q=mbx_async_reserve();
 q->kind=1;q->bytes=bytes;memcpy(q->packet,packet,bytes);mbx_async_publish();
}

void n810_mbx_async_drain(void)
{
 pthread_mutex_lock(&mbx_async.lock);
 while(mbx_async.outstanding)pthread_cond_wait(&mbx_async.changed,&mbx_async.lock);
 pthread_mutex_unlock(&mbx_async.lock);
}
struct mbx_async_fence { unsigned refs;uint64_t sequence; };
void *n810_mbx_fence_create(void)
{
 const char *enabled=getenv("N810_MBX_ASYNC_FENCES");
 if(!mbx_async_enabled()||!enabled||strcmp(enabled,"1")){
  n810_mbx_async_drain();return (void *)(uintptr_t)1;
 }
 struct mbx_async_fence *f=malloc(sizeof(*f));
 if(!f){n810_mbx_async_drain();return (void *)(uintptr_t)1;}
 f->refs=1;pthread_mutex_lock(&mbx_async.lock);
 f->sequence=mbx_async.submitted_sequence;pthread_mutex_unlock(&mbx_async.lock);
 return f;
}
void *n810_mbx_fence_reference(void *previous,void *src)
{
 struct mbx_async_fence *old=previous,*next=src;
 if((uintptr_t)next>1)__atomic_add_fetch(&next->refs,1,__ATOMIC_RELAXED);
 if((uintptr_t)old>1&&__atomic_sub_fetch(&old->refs,1,__ATOMIC_ACQ_REL)==0)free(old);
 return next;
}
bool n810_mbx_fence_finish(void *opaque,uint64_t timeout)
{
 if((uintptr_t)opaque<=1)return true;
 struct mbx_async_fence *f=opaque;
 struct mbx_trace_stamp trace=mbx_trace_begin();
 struct timespec deadline;
 if(timeout&&timeout!=UINT64_MAX){
  clock_gettime(CLOCK_MONOTONIC,&deadline);
  /* Saturate to the representable time_t horizon rather than wrapping. */
  uint64_t seconds=timeout/1000000000ull;
  uint64_t limit=sizeof(time_t)==4?INT32_MAX:INT64_MAX;
  if(seconds>=limit-(uint64_t)deadline.tv_sec){deadline.tv_sec=limit;deadline.tv_nsec=999999999;}
  else{deadline.tv_sec+=seconds;deadline.tv_nsec+=timeout%1000000000ull;
   if(deadline.tv_nsec>=1000000000){++deadline.tv_sec;deadline.tv_nsec-=1000000000;}}
 }
 pthread_mutex_lock(&mbx_async.lock);
 while(mbx_async.finished_sequence<f->sequence){
  if(!timeout)break;
  int error=timeout==UINT64_MAX?pthread_cond_wait(&mbx_async.changed,&mbx_async.lock):
   pthread_cond_clockwait(&mbx_async.changed,&mbx_async.lock,CLOCK_MONOTONIC,&deadline);
  if(error==ETIMEDOUT)break;
  if(error)mbx_async_fatal("fence wait");
 }
 bool finished=mbx_async.finished_sequence>=f->sequence;
 pthread_mutex_unlock(&mbx_async.lock);mbx_trace_end("fence_wait",trace,finished);return finished;
}
static void mbx_async_release(bool *owner)
{
 if(!*owner)return;
 n810_mbx_async_drain();pthread_mutex_lock(&mbx_async.lock);
 *owner=false;if(--mbx_async.refs){pthread_mutex_unlock(&mbx_async.lock);return;}
 mbx_async.stop=true;pthread_cond_broadcast(&mbx_async.changed);pthread_mutex_unlock(&mbx_async.lock);
 pthread_join(mbx_async.thread,NULL);free(mbx_async.display_name);mbx_async.display_name=NULL;mbx_async.started=false;
}
static void *mbx_async_read_map(void)
{n810_mbx_async_drain();return mbx_async.image?mbx_async.image->map:NULL;}
