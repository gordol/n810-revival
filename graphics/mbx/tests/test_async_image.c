#define _GNU_SOURCE
#include "../mesa/mbx_shared_image.h"
#include <assert.h>
#include <dirent.h>
#include <stdatomic.h>
static atomic_bool blocked;
static uint16_t *target;static unsigned expected_frame;static atomic_uint written;
static ssize_t render(int fd,const void *packet,size_t bytes)
{
 while(atomic_load(&blocked))usleep(100);
 (void)fd;assert(bytes==sizeof(unsigned)||bytes==24+512*76);unsigned frame;memcpy(&frame,packet,sizeof(frame));
 assert(frame==expected_frame++);usleep(2000);
 for(size_t i=sizeof(frame);i<bytes;++i)assert(((const unsigned char *)packet)[i]==(unsigned char)(frame^i));
 for(unsigned y=0;y<96;++y)for(unsigned x=0;x<144;++x)target[y*144+x]=(frame*931+x*217+y*733)&65535;
 atomic_fetch_add(&written,1);return bytes;
}
#define MBX_ASYNC_WRITE render
#include "../mesa/mbx_async_image.h"
static unsigned fds(void){unsigned n=0;DIR *d=opendir("/proc/self/fd");assert(d);while(readdir(d))++n;closedir(d);return n;}
int main(void)
{
 setenv("N810_MBX_ASYNC_FENCES","1",1);
 void *retained=NULL;
 Display *d=XOpenDisplay(NULL);assert(d);int screen=DefaultScreen(d);assert(DefaultDepth(d,screen)==16);
 Window w=XCreateSimpleWindow(d,RootWindow(d,screen),0,0,128,96,0,0,0);XMapWindow(d,w);XSync(d,False);
 unsigned before=fds(),pixels=0;
 for(unsigned cycle=0;cycle<8;++cycle){
  int fd=memfd_create("mbx-async",MFD_CLOEXEC);assert(fd>=0);size_t bytes=7*4096;assert(!ftruncate(fd,bytes));
  target=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(target!=MAP_FAILED);
  bool owner=false,other=false;assert(!mbx_async_acquire(d,fd,288*96,&owner));assert(!mbx_async_acquire(d,fd,288*96,&other));
  if(retained){assert(n810_mbx_fence_finish(retained,0));retained=n810_mbx_fence_reference(retained,NULL);}
  expected_frame=0;atomic_store(&written,0);
  for(unsigned frame=0;frame<32;++frame){
   struct mbx_async_command c;memset(&c,0,offsetof(struct mbx_async_command,packet));
   c.kind=1;c.bytes=(frame%4<2)?sizeof(frame):sizeof(c.packet);
   for(size_t i=sizeof(frame);i<c.bytes;++i)c.packet[i]=(unsigned char)(frame^i);
   memcpy(c.packet,&frame,sizeof(frame));
   if(frame<=1)atomic_store(&blocked,true);
   if(frame&1)mbx_async_enqueue_packet(c.packet,c.bytes);else mbx_async_enqueue(&c);
   memset(c.packet,0xff,c.bytes); /* producer storage must not be retained */
   c.kind=2;c.bytes=0;c.width=128;c.height=96;c.stride=288;c.depth=16;c.drawable=w;
   c.visual=XVisualIDFromVisual(DefaultVisual(d,screen));c.w=128;c.h=96;mbx_async_enqueue(&c);
   void *fence=n810_mbx_fence_create();assert((uintptr_t)fence>1);
   if(frame==0){
    assert(!n810_mbx_fence_finish(fence,0));assert(!n810_mbx_fence_finish(fence,1000000));
    retained=n810_mbx_fence_reference(NULL,fence);atomic_store(&blocked,false);
    assert(n810_mbx_fence_finish(fence,UINT64_MAX));
   }
   if(frame==1){
    assert(n810_mbx_fence_finish(retained,0));
    assert(!n810_mbx_fence_finish(fence,0));atomic_store(&blocked,false);
    assert(n810_mbx_fence_finish(fence,UINT64_MAX));
    assert(n810_mbx_fence_finish(fence,UINT64_MAX-1));
   }
   fence=n810_mbx_fence_reference(fence,NULL);assert(!fence);
   pthread_mutex_lock(&mbx_async.lock);assert(mbx_async.outstanding<=MBX_ASYNC_COMMANDS);pthread_mutex_unlock(&mbx_async.lock);
   if(frame%8==7){
    n810_mbx_async_drain();assert(atomic_load(&written)==frame+1);
    /* Main-display synchronization alone cannot fence the private connection. */
    mbx_shared_wait(mbx_async.image);
    XImage *actual=XGetImage(d,w,0,0,128,96,AllPlanes,ZPixmap);assert(actual);
    for(unsigned y=0;y<96;++y)for(unsigned x=0;x<128;++x){assert(XGetPixel(actual,x,y)==((frame*931+x*217+y*733)&65535));++pixels;}
    XDestroyImage(actual);assert(mbx_async_read_map());
   }
  }
  mbx_async_release(&owner);assert(mbx_async.started);mbx_async_release(&other);assert(!mbx_async.started&&!mbx_async.outstanding);
  assert(fcntl(fd,F_GETFD)>=0);munmap(target,bytes);close(fd);XSync(d,False);assert(fds()==before);
 }
 retained=n810_mbx_fence_reference(retained,NULL);
 XDestroyWindow(d,w);XCloseDisplay(d);printf("PASS256 ordered asynchronous renders, %u exact pixels, bounded queue, copied packets,8 ownership cycles, no fd leaks\n",pixels);
}
