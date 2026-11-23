#!/usr/bin/env python3
"""Exercise the reconstructed omapfb worker with deterministic driver callbacks.

Run with the path to a patched Linux 5.15.224 source tree.
"""
from pathlib import Path
import subprocess
import sys
import tempfile


def check(tree):
    source = (tree / "drivers/video/fbdev/omap2/omapfb/omapfb-main.c").read_text()
    callbacks = source[source.index("static void omapfb_fillrect("):
                       source.index("static unsigned calc_rotation_offset_dma(")]
    worker = source[source.index("static bool omapfb_video_enabled("):
                    source.index("void omapfb_start_auto_update(")]
    harness = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
typedef unsigned short u16;
#define HZ 100U
#define OMAP_DSS_GFX 0
#define READ_ONCE(x) (x)
#define max(x,y) ((x) > (y) ? (x) : (y))
#define time_before(x,y) ((long)((x)-(y)) < 0)
#define container_of(ptr,type,member) ((type *)(ptr))
#define FB2OFB(x) (x)
#define atomic_set(p,x) (*(p)=(x))
#define atomic_read(p) (*(p))
#define atomic_inc(p) (++*(p))
#define atomic_dec(p) (--*(p))
static int atomic_xchg(int *p,int x) {int old=*p; *p=x; return old;}
struct work_struct {int unused;};
struct omap_overlay {int id; bool (*is_enabled)(struct omap_overlay *);};
struct omapfb2_device {
    unsigned num_displays, num_overlays;
    struct omap_overlay *overlays[2];
    int console_dirty,user_opens,auto_update_wq;
    unsigned long refresh_deadline;
};
struct fb_info {struct omapfb2_device *fbdev;};
struct fb_copyarea {int x;}; struct fb_image {int x;}; struct fb_fillrect {int x;};
#define cfb_fillrect(f,r) ((void)(r))
#define cfb_copyarea(f,r) ((void)(r))
#define cfb_imageblit(f,r) ((void)(r))
struct omap_dss_device;
struct omap_dss_driver {
    int (*sync)(struct omap_dss_device *);
    void (*get_resolution)(struct omap_dss_device *,u16 *,u16 *);
    int (*update)(struct omap_dss_device *,int,int,int,int);
};
struct omap_dss_device {struct omap_dss_driver *driver;};
struct omapfb_display_data {
    struct work_struct auto_update_work;
    struct omap_dss_device *dssdev;
    struct omapfb2_device *fbdev;
};
static unsigned auto_update_freq,delay;
static unsigned long jiffies;
static int sends,syncs,fail;
#define queue_delayed_work(q,w,t) ((void)(delay=(t)))
static int sync_display(struct omap_dss_device *d){return ++syncs;}
static void resolution(struct omap_dss_device *d,u16 *w,u16 *h){*w=800;*h=480;}
static int update(struct omap_dss_device *d,int x,int y,int w,int h){
    assert(!x && !y && w==800 && h==480); sends++; return fail;
}
static bool enabled(struct omap_overlay *v){return true;}
"""
    main = r"""
int main(void){
    struct omap_dss_driver ops={sync_display,resolution,update};
    struct omap_dss_device panel={&ops};
    struct omap_overlay video={1,enabled};
    struct omapfb2_device fb={.num_displays=1,.console_dirty=1,.overlays={&video}};
    struct omapfb_display_data d={.dssdev=&panel,.fbdev=&fb};
    struct fb_info info={&fb};
#define tick() do {omapfb_auto_update_work(&d.auto_update_work); jiffies+=delay;} while(0)
    for(int i=0;i<20;i++) tick();
    assert(sends==1 && syncs==1 && jiffies==100);
    tick(); assert(sends==2);
    omapfb_fillrect(&info,0); omapfb_imageblit(&info,0); tick(); assert(sends==3);
    omapfb_copyarea(&info,0); fail=1; tick(); fail=0; tick(); assert(sends==5);
    omapfb_open(&info,1); tick(); tick(); assert(sends==7);
    omapfb_release(&info,1); tick(); tick(); assert(sends==8);
    omapfb_open(&info,0); tick(); omapfb_release(&info,0); assert(sends==8);
    fb.num_overlays=1; tick(); tick(); assert(sends==10);
    fb.num_overlays=0; fb.num_displays=2; tick(); tick(); assert(sends==12);
    fb.num_displays=1; auto_update_freq=20; tick(); tick(); assert(sends==14);
    auto_update_freq=101; tick(); assert(delay==1 && sends==syncs);
    puts("Idle, draw, retry, user open/close, video, multi-display and fixed rate passed.");
}
"""
    with tempfile.TemporaryDirectory() as directory:
        c = Path(directory) / "refresh.c"
        exe = c.with_suffix("")
        c.write_text(harness + callbacks + worker + main)
        subprocess.run(["cc", "-std=c11", "-Wall", "-Werror", str(c), "-o", str(exe)], check=True)
        subprocess.run([str(exe)], check=True)


if __name__ == "__main__":
    check(Path(sys.argv[1]))
