/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Owned-fd adapter over the existing Nokia presenter. No VT/module lifecycle. */
#define _POSIX_C_SOURCE 200809L
#include "present.h"
#include <linux/fb.h>
#include <linux/omapfb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <time.h>
struct window {int fd;struct mbx_presenter presenter;uint64_t rfbi_pixels,rfbi_submits,partial_rejected,partial_submits;int full_only,timing;uint64_t wait_calls,wait_cpu_ns,wait_wall_ns,submit_calls,submit_cpu_ns,submit_wall_ns;};
static const char *error="Nokia display rejected";
static uint64_t present_cpu(struct window *w){struct rusage u;if(!w->timing||getrusage(RUSAGE_SELF,&u))return 0;return ((uint64_t)u.ru_utime.tv_sec+u.ru_stime.tv_sec)*1000000000ULL+((uint64_t)u.ru_utime.tv_usec+u.ru_stime.tv_usec)*1000ULL;}
static uint64_t present_wall(struct window *w){struct timespec t;if(!w->timing||clock_gettime(CLOCK_MONOTONIC,&t))return 0;return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
static int wait_frame(void *p){
 struct window *w=p;uint64_t cpu=present_cpu(w),wall=present_wall(w);int result=ioctl(w->fd,OMAPFB_SYNC_GFX),saved_errno=errno;
 if(w->timing){w->wait_cpu_ns+=present_cpu(w)-cpu;w->wait_wall_ns+=present_wall(w)-wall;++w->wait_calls;}errno=saved_errno;return result;
}
static int submit_frame(void *p){
 struct window *w=p;uint64_t cpu=present_cpu(w),wall=present_wall(w);struct mbx_rect r=w->presenter.submitted_region;
 /* RGB565 RFBI writes use paired pixels. Expand, never crop or rescale. */
 unsigned right=(r.x+r.width+1)&~1u;r.x&=~1u;r.width=right-r.x;
 struct omapfb_update_window u={.x=r.x,.y=r.y,.width=r.width,.height=r.height,
  .out_x=r.x,.out_y=r.y,.out_width=r.width,.out_height=r.height,.format=OMAPFB_COLOR_RGB565};
 int partial=r.x||r.y||r.width!=800||r.height!=480;
 if(partial&&w->full_only)u=(struct omapfb_update_window){.width=800,.height=480,.out_width=800,.out_height=480,.format=OMAPFB_COLOR_RGB565};
 int result=ioctl(w->fd,OMAPFB_UPDATE_WINDOW,&u);
 /* The n8x0 full-only driver rejects bounds before locking or starting RFBI.
  * EINVAL is an unsupported-region response, not a timeout/fault recovery. */
 if(result&&errno==EINVAL&&partial&&!w->full_only){
  w->full_only=1;++w->partial_rejected;
  u=(struct omapfb_update_window){.width=800,.height=480,.out_width=800,.out_height=480,.format=OMAPFB_COLOR_RGB565};
  result=ioctl(w->fd,OMAPFB_UPDATE_WINDOW,&u);
 }
 if(!result){++w->rfbi_submits;w->rfbi_pixels+=(uint64_t)u.width*u.height;if(u.width!=800||u.height!=480)++w->partial_submits;
  w->presenter.submitted_region=(struct mbx_rect){u.x,u.y,u.width,u.height};}
 int saved_errno=errno;if(w->timing){w->submit_cpu_ns+=present_cpu(w)-cpu;w->submit_wall_ns+=present_wall(w)-wall;++w->submit_calls;}errno=saved_errno;
 return result;
}
const char *pocket_window_error(void){return error;}
void *pocket_window_open(int fd){
 struct fb_var_screeninfo v;struct fb_fix_screeninfo f;enum omapfb_update_mode mode;
 if(fd<0||ioctl(fd,FBIOGET_VSCREENINFO,&v)||ioctl(fd,FBIOGET_FSCREENINFO,&f)||ioctl(fd,OMAPFB_GET_UPDATE_MODE,&mode)){error="An explicitly owned framebuffer fd is required";return NULL;}
 if(mode!=OMAPFB_MANUAL_UPDATE||v.xres!=800||v.yres!=480||v.xoffset||v.yoffset||v.bits_per_pixel!=16||v.red.offset!=11||v.red.length!=5||v.green.offset!=5||v.green.length!=6||v.blue.offset||v.blue.length!=5||v.red.msb_right||v.green.msb_right||v.blue.msb_right||v.transp.length||f.line_length!=1600||f.smem_len<768000){error="Expected owned800x480RGB565 manual-update display";return NULL;}
 struct window *w=calloc(1,sizeof(*w));if(!w)return NULL;w->fd=dup(fd);if(w->fd<0){free(w);return NULL;}
 const char *timing=getenv("POCKET_PRESENT_PROFILE");w->timing=timing&&!strcmp(timing,"1");
 void *pixels=mmap(NULL,768000,PROT_READ|PROT_WRITE,MAP_SHARED,w->fd,0);
 if(pixels==MAP_FAILED){close(w->fd);free(w);return NULL;}
 w->presenter=(struct mbx_presenter){.framebuffer={pixels,768000,1600,800,480},.ops={wait_frame,submit_frame},.context=w};
 if(wait_frame(w)){error="Previous display transfer did not drain";munmap(pixels,768000);close(w->fd);free(w);return NULL;}
 return w;
}
int pocket_window_present(void *ptr,const void *pixels){
 struct window *w=ptr;struct mbx_surface source={(void*)pixels,768000,1600,800,480};
 int result=mbx_present_rgb565(&w->presenter,&source,(struct mbx_rect){0,0,800,480},0,0);
 if(result)error="Display completion or submission failed; owner recovery required";
 return result;
}
int pocket_window_present_stats(void *ptr,uint64_t out[4]){
 struct window *w=ptr;if(!w||!out)return -1;
 out[0]=w->rfbi_submits;out[1]=w->rfbi_pixels;out[2]=w->partial_submits;out[3]=w->partial_rejected;return 0;
}
int pocket_window_timing_stats(void *ptr,uint64_t out[6]){
 struct window *w=ptr;if(!w||!out)return -1;
 out[0]=w->wait_calls;out[1]=w->wait_cpu_ns;out[2]=w->wait_wall_ns;out[3]=w->submit_calls;out[4]=w->submit_cpu_ns;out[5]=w->submit_wall_ns;return 0;
}
int pocket_window_dma_fd(void *ptr){struct window *w=ptr;return w?w->fd:-1;}
/* Read-only destination metadata; no framebuffer lease or write is granted. */
int pocket_window_prepare(void *ptr,struct mbx_surface *out){
 struct window *w=ptr;if(!w||!out||w->presenter.faulted||w->presenter.writing)return -1;
 *out=w->presenter.framebuffer;return 0;
}
int pocket_window_acquire(void *ptr,struct mbx_surface *surface){
 struct window *w=ptr;return w?mbx_present_acquire(&w->presenter,surface):-1;
}
int pocket_window_submit(void *ptr){
 struct window *w=ptr;return w?mbx_present_submit(&w->presenter,(struct mbx_rect){0,0,800,480}):-1;
}
int pocket_window_submit_region(void *ptr,unsigned x,unsigned y,unsigned width,unsigned height){
 struct window *w=ptr;if(!w)return -1;
 return width&&height?mbx_present_submit(&w->presenter,(struct mbx_rect){x,y,width,height}):mbx_present_cancel(&w->presenter);
}
int pocket_window_cancel(void *ptr){struct window *w=ptr;return w?mbx_present_cancel(&w->presenter):-1;}
int pocket_window_event(int out[6]){(void)out;return 0;}
int pocket_window_close(void *ptr){
 struct window *w=ptr;if(!w)return 0;
 if(mbx_present_drain(&w->presenter)){error="Display still faulted; owner recovery required";return -1;}
 munmap(w->presenter.framebuffer.pixels,768000);close(w->fd);free(w);return 0;
}

#ifdef POCKET_SCENE_GL
#include "gpu_scene.c"
#endif
