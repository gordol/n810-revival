/* SPDX-License-Identifier: MIT
 * Read-only MIT-SHM fd import of an already-owned completed GPU image.
 * X reads that image directly. XSync fences its consumption before GPU reuse.
 * XCB ABI declarations below match the public MIT-SHM 1.2 API; optional runtime
 * loading keeps the established path independent of additional build packages.
 */
#include <X11/Xlib.h>
#include <X11/Xutil.h>
#include <X11/extensions/XShm.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <dlfcn.h>
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <unistd.h>
#include <string.h>
#include <stdio.h>
#include <fcntl.h>
struct sw_displaytarget;
int n810_mbx_shared_bind(struct sw_displaytarget *,int,size_t);
struct mbx_xcb_connection;
struct mbx_xcb_cookie {unsigned sequence;};
struct mbx_shared_image {
 Display *display;void *map;size_t bytes;int fd;
 XShmSegmentInfo segment;XImage *image;GC gc;Drawable drawable;
 bool attached,pending,verified;
};
static struct mbx_shared_image *mbx_last_shared_present;
static int mbx_shared_attach(Display *display,XShmSegmentInfo *segment,int fd)
{
 static void *x11xcb,*xcb,*shm;
 struct mbx_xcb_connection *(*connection)(Display *);
 uint32_t (*id)(struct mbx_xcb_connection *);
 struct mbx_xcb_cookie (*attach)(struct mbx_xcb_connection *,uint32_t,int32_t,uint8_t);
 void *(*check)(struct mbx_xcb_connection *,struct mbx_xcb_cookie);
 if(!x11xcb)x11xcb=dlopen("libX11-xcb.so.1",RTLD_NOW|RTLD_LOCAL);
 if(!xcb)xcb=dlopen("libxcb.so.1",RTLD_NOW|RTLD_LOCAL);
 if(!shm)shm=dlopen("libxcb-shm.so.0",RTLD_NOW|RTLD_LOCAL);
 if(!x11xcb||!xcb||!shm)return -1;
 connection=dlsym(x11xcb,"XGetXCBConnection");id=dlsym(xcb,"xcb_generate_id");
 attach=dlsym(shm,"xcb_shm_attach_fd_checked");check=dlsym(xcb,"xcb_request_check");
 if(!connection||!id||!attach||!check)return -1;
 struct mbx_xcb_connection *c=connection(display);if(!c)return -1;
 int sent=fcntl(fd,F_DUPFD_CLOEXEC,3);if(sent<0)return -1;
 segment->shmseg=id(c);
 /* libxcb owns the duplicate once queued; the caller's fd stays untouched. */
 struct mbx_xcb_cookie cookie=attach(c,segment->shmseg,sent,1);
 void *error=check(c,cookie);
 if(error){free(error);return -1;}
 return 0;
}
static int mbx_shared_prepare(struct mbx_shared_image **out,Display *display,int fd,size_t bytes)
{
 if(*out)return (*out)->bytes>=bytes?0:-1;
 struct stat st;if(fstat(fd,&st)||st.st_size<=0||st.st_size>512*1024||
    (uint64_t)st.st_size<bytes||((uint64_t)st.st_size&4095))return -1;
 struct mbx_shared_image *s=calloc(1,sizeof(*s));if(!s)return -1;
 s->display=display;s->bytes=st.st_size;s->fd=-1;
 s->map=mmap(NULL,s->bytes,PROT_READ,MAP_SHARED,fd,0);
 if(s->map==MAP_FAILED){free(s);return -1;}
 s->fd=fcntl(fd,F_DUPFD_CLOEXEC,3);
 if(s->fd<0){munmap(s->map,s->bytes);free(s);return -1;}
 s->segment.shmid=-1;s->segment.shmaddr=s->map;s->segment.readOnly=True;
 *out=s;return 0;
}
static void mbx_shared_wait(struct mbx_shared_image *s)
{
 /* Different GL buffers can share the one bounded GPU target. Fence the
  * most recent presentation globally, not just the current displaytarget. */
 if(mbx_last_shared_present&&mbx_last_shared_present->pending){
  XSync(mbx_last_shared_present->display,False);mbx_last_shared_present->pending=false;
 }
 if(s&&s->pending){XSync(s->display,False);s->pending=false;}
}
static int mbx_shared_display(struct mbx_shared_image *s,Visual *visual,unsigned depth,
 Drawable drawable,unsigned width,unsigned height,unsigned stride,int x,int y,unsigned w,unsigned h)
{
 if(depth!=16||stride%2||(size_t)stride*height>s->bytes||width*2>stride||
    x<0||y<0||(unsigned)x>width||(unsigned)y>height||w>width-(unsigned)x||h>height-(unsigned)y)return -1;
 if(!s->image){
  int major,minor;Bool pixmaps;
  if(!XShmQueryVersion(s->display,&major,&minor,&pixmaps)||major<1||(major==1&&minor<2))return -1;
  s->image=XShmCreateImage(s->display,visual,depth,ZPixmap,s->map,&s->segment,stride/2,height);
  if(!s->image)return -1;
  if(s->image->bits_per_pixel!=16||s->image->bytes_per_line!=(int)stride||
     s->image->red_mask!=0xf800||s->image->green_mask!=0x7e0||s->image->blue_mask!=0x1f)return -1;
  if(mbx_shared_attach(s->display,&s->segment,s->fd))return -1;
  s->attached=true;close(s->fd);s->fd=-1;
  fprintf(stderr,"N810_MBX_SHARED_IMAGE attached=1 cpu_readback_copy=0 readonly=1 stride=%u\n",stride);
 }
 if(s->drawable!=drawable){
  mbx_shared_wait(s);if(s->gc)XFreeGC(s->display,s->gc);
  s->gc=XCreateGC(s->display,drawable,0,NULL);s->drawable=drawable;
 }
 if(!XShmPutImage(s->display,drawable,s->gc,s->image,x,y,x,y,w,h,False))return -1;
 XFlush(s->display);s->pending=true;mbx_last_shared_present=s;
 if(!s->verified&&getenv("N810_MBX_VERIFY_SHARED_IMAGE")){
  mbx_shared_wait(s);
  XImage *actual=XGetImage(s->display,drawable,x,y,w,h,AllPlanes,ZPixmap);
  if(!actual)return -1;
  bool equal=true;unsigned mismatches=0;
  for(unsigned row=0;row<h;++row)for(unsigned col=0;col<w;++col){
   const uint16_t *pixels=(const uint16_t *)((const char *)s->map+(y+row)*stride);
   unsigned got=XGetPixel(actual,col,row),expected=pixels[x+col];
   if(got!=expected){equal=false;if(mismatches++<8)fprintf(stderr,"N810_MBX_X_PIXEL_MISMATCH x=%u y=%u expected=%04x actual=%04x\n",x+col,y+row,expected,got);}
  }
  XDestroyImage(actual);if(!equal){fprintf(stderr,"N810_MBX_X_MISMATCH_COUNT %u\n",mismatches);return -1;}
  s->verified=true;fprintf(stderr,"N810_MBX_SHARED_IMAGE_VERIFIED pixels=%u bit_exact=1\n",w*h);
 }
 return 0;
}
static void mbx_shared_destroy(struct mbx_shared_image *s)
{
 if(!s)return;
 mbx_shared_wait(s);
 if(s->attached){XShmDetach(s->display,&s->segment);XSync(s->display,False);}
 if(s->image){s->image->data=NULL;XDestroyImage(s->image);}
 if(s->gc)XFreeGC(s->display,s->gc);
 if(s->fd>=0)close(s->fd);
 if(mbx_last_shared_present==s)mbx_last_shared_present=NULL;
 munmap(s->map,s->bytes);free(s);
}
