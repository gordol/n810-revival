/* SPDX-License-Identifier: MIT
 * Exercise the production fd-sharing helper against a real X server, including
 * repeated reuse, exact pixels, fd ownership and detach/destruction.
 */
#define _GNU_SOURCE
#include "../mesa/mbx_shared_image.h"
#include <assert.h>
#include <dirent.h>
static unsigned fds(void){unsigned n=0;DIR *d=opendir("/proc/self/fd");assert(d);while(readdir(d))++n;closedir(d);return n;}
int main(void){
 Display *d=XOpenDisplay(NULL);assert(d);int screen=DefaultScreen(d);assert(DefaultDepth(d,screen)==16);
 Window w=XCreateSimpleWindow(d,RootWindow(d,screen),0,0,128,96,0,0,0);XMapWindow(d,w);XSync(d,False);
 unsigned before=fds();
 for(unsigned cycle=0;cycle<8;++cycle){
  int fd=memfd_create("mbx-shared-image-test",MFD_CLOEXEC);assert(fd>=0);
  size_t bytes=7*4096;assert(!ftruncate(fd,bytes));
  uint16_t *cpu=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0);assert(cpu!=MAP_FAILED);
  struct mbx_shared_image *s=NULL,*other=NULL;
  assert(mbx_shared_prepare(&s,d,fd,bytes+1)==-1&&!s);
  assert(!mbx_shared_prepare(&s,d,fd,288*96));
  assert(!mbx_shared_prepare(&other,d,fd,288*96));
  for(unsigned frame=0;frame<16;++frame){
   struct mbx_shared_image *current=frame%2?s:other;
   mbx_shared_wait(current);
   for(unsigned y=0;y<96;++y)for(unsigned x=0;x<144;++x)cpu[y*144+x]=(x*217+y*733+frame*931+cycle*57)&0xffff;
   assert(!mbx_shared_display(current,DefaultVisual(d,screen),16,w,128,96,288,0,0,128,96));
   mbx_shared_wait(s);
   XImage *image=XGetImage(d,w,0,0,128,96,AllPlanes,ZPixmap);assert(image);
   for(unsigned y=0;y<96;++y)for(unsigned x=0;x<128;++x)assert(XGetPixel(image,x,y)==cpu[y*144+x]);
   XDestroyImage(image);
  }
  assert(fcntl(fd,F_GETFD)>=0); /* passing a duplicate must not consume caller fd */
  mbx_shared_destroy(s);mbx_shared_destroy(other);munmap(cpu,bytes);close(fd);XSync(d,False);assert(fds()==before);
 }
 XDestroyWindow(d,w);XCloseDisplay(d);
 puts("PASS: 128 shared presentations, 1572864 exact pixels, fences, 8 detach cycles, no fd leaks");
}
