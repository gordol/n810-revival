/* Owned-fd adapter over the existing Nokia presenter. No VT/module lifecycle. */
#include "present.h"
#include <linux/fb.h>
#include <linux/omapfb.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <string.h>
struct window {int fd;struct mbx_presenter presenter;};
static const char *error="Nokia display rejected";
static int wait_frame(void *p){return ioctl(((struct window*)p)->fd,OMAPFB_SYNC_GFX);}
static int submit_frame(void *p){struct omapfb_update_window u={.width=800,.height=480,.out_width=800,.out_height=480,.format=OMAPFB_COLOR_RGB565};return ioctl(((struct window*)p)->fd,OMAPFB_UPDATE_WINDOW,&u);}
const char *pocket_window_error(void){return error;}
void *pocket_window_open(int fd){
 struct fb_var_screeninfo v;struct fb_fix_screeninfo f;enum omapfb_update_mode mode;
 if(fd<0||ioctl(fd,FBIOGET_VSCREENINFO,&v)||ioctl(fd,FBIOGET_FSCREENINFO,&f)||ioctl(fd,OMAPFB_GET_UPDATE_MODE,&mode)){error="An explicitly owned framebuffer fd is required";return NULL;}
 if(mode!=OMAPFB_MANUAL_UPDATE||v.xres!=800||v.yres!=480||v.xoffset||v.yoffset||v.bits_per_pixel!=16||v.red.offset!=11||v.red.length!=5||v.green.offset!=5||v.green.length!=6||v.blue.offset||v.blue.length!=5||v.red.msb_right||v.green.msb_right||v.blue.msb_right||v.transp.length||f.line_length!=1600||f.smem_len<768000){error="Expected owned800x480RGB565 manual-update display";return NULL;}
 struct window *w=calloc(1,sizeof(*w));if(!w)return NULL;w->fd=dup(fd);if(w->fd<0){free(w);return NULL;}
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
int pocket_window_event(int out[6]){(void)out;return 0;}
int pocket_window_close(void *ptr){
 struct window *w=ptr;if(!w)return 0;
 if(mbx_present_drain(&w->presenter)){error="Display still faulted; owner recovery required";return -1;}
 munmap(w->presenter.framebuffer.pixels,768000);close(w->fd);free(w);return 0;
}
