/* Visible target collection. Saves raw pairs; never changes kernel calibration. */
#define _POSIX_C_SOURCE 200809L
#include <errno.h>
#include <fcntl.h>
#include <linux/fb.h>
#include <linux/input.h>
#include <linux/kd.h>
#include <linux/omapfb.h>
#include <poll.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopped;
static void stop(int sig) { (void)sig; stopped=1; }
static long elapsed(void) { struct timespec t; clock_gettime(CLOCK_MONOTONIC,&t); return t.tv_sec; }
static int input_open(void)
{
    for (int i=0;i<32;i++) {
        char path[64], name[128]={0};
        snprintf(path,sizeof(path),"/dev/input/event%d",i);
        int fd=open(path,O_RDONLY|O_CLOEXEC|O_NONBLOCK);
        if (fd<0) continue;
        if (ioctl(fd,EVIOCGNAME(sizeof(name)),name)>=0 && !strcmp(name,"TSC2005 touchscreen")) return fd;
        close(fd);
    }
    errno=ENODEV; return -1;
}
static int refresh(int fd)
{
    struct omapfb_update_window w={.width=800,.height=480,.out_width=800,.out_height=480};
    return ioctl(fd,OMAPFB_UPDATE_WINDOW,&w);
}
static void pixel(unsigned char *mem,const struct fb_fix_screeninfo *f,
                  const struct fb_var_screeninfo *v,int x,int y,uint16_t value)
{
    if(x>=0 && x<800 && y>=0 && y<480)
        memcpy(mem+(size_t)(y+v->yoffset)*f->line_length+(size_t)(x+v->xoffset)*2,&value,2);
}
static int pointer_test(int fb,int in,unsigned char *mem,
                        const struct fb_fix_screeninfo *f,const struct fb_var_screeninfo *v,
                        const double c[6])
{
    for(int y=0;y<480;y++) for(int x=0;x<800;x++) pixel(mem,f,v,x,y,0x0841);
    const int targets[5][2]={{80,48},{720,48},{720,432},{80,432},{400,240}};
    for(int i=0;i<5;i++) for(int k=-12;k<=12;k++) {
        pixel(mem,f,v,targets[i][0]+k,targets[i][1],0x7bef);
        pixel(mem,f,v,targets[i][0],targets[i][1]+k,0x7bef);
    }
    unsigned char *background=malloc(f->smem_len);
    if(!background) return 1;
    memcpy(background,mem,f->smem_len);
    if(refresh(fb)<0) {free(background);return 1;}
    int x=-1,y=-1,down=0,dirty=0,frames=0,oldx=-1,oldy=-1;
    long deadline=elapsed()+120;
    struct timespec last={0};
    while(!stopped && elapsed()<deadline) {
        struct pollfd p={.fd=in,.events=POLLIN};
        int ready=poll(&p,1,16);
        if(ready<0 && errno==EINTR) continue;
        if(ready<0 || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) {free(background);return 1;}
        if(ready) {
            /* Drain queued events before rendering, so the pointer uses current input. */
            for(int batch=0;batch<16;batch++) {
                struct input_event events[32];
                ssize_t got=read(in,events,sizeof(events));
                if(got<0 && errno==EAGAIN) break;
                if(got<0 && errno==EINTR) continue;
                if(got<=0 || got%sizeof(events[0])) {free(background);return 1;}
                for(size_t i=0;i<(size_t)got/sizeof(events[0]);i++) {
                    struct input_event e=events[i];
                    if(e.type==EV_ABS && e.code==ABS_X) x=e.value;
                    if(e.type==EV_ABS && e.code==ABS_Y) y=e.value;
                    if(e.type==EV_KEY && e.code==BTN_TOUCH) down=e.value!=0;
                    if(e.type==EV_SYN && e.code==SYN_REPORT) dirty=1;
                }
            }
        }
        struct timespec now;clock_gettime(CLOCK_MONOTONIC,&now);
        double delta=(now.tv_sec-last.tv_sec)+(now.tv_nsec-last.tv_nsec)/1e9;
        if(dirty && x>=0 && y>=0 && delta>=0.033) {
            double px=c[0]*x+c[1]*y+c[2],py=c[3]*x+c[4]*y+c[5];
            int tx=(int)(fmax(0,fmin(799,px))+0.5),ty=(int)(fmax(0,fmin(479,py))+0.5);
            if(oldx>=0) {
                for(int row=oldy-9;row<=oldy+9;row++) {
                    if(row<0 || row>=480) continue;
                    int left=oldx-9<0?0:oldx-9,right=oldx+10>800?800:oldx+10;
                    size_t offset=(size_t)(row+v->yoffset)*f->line_length+(size_t)(left+v->xoffset)*2;
                    memcpy(mem+offset,background+offset,(size_t)(right-left)*2);
                }
            }
            for(int k=-9;k<=9;k++) {
                pixel(mem,f,v,tx+k,ty,down?0x07ff:0xffff);
                pixel(mem,f,v,tx,ty+k,down?0x07ff:0xffff);
            }
            if(refresh(fb)<0) {free(background);return 1;}
            oldx=tx;oldy=ty;
            last=now;dirty=0;frames++;
        }
    }
    fprintf(stderr,"Pointer test finished: %d rendered frames\n",frames);
    free(background);return stopped?1:0;
}
int main(int argc,char **argv)
{
    int fb=-1,in=-1,tty=-1,oldmode=KD_TEXT,result=1,graphics=0;
    unsigned char *mem=MAP_FAILED,*saved=NULL;
    struct fb_fix_screeninfo f; struct fb_var_screeninfo v;
    FILE *out=NULL;
    int pointer=argc==3 && !strcmp(argv[1],"--pointer");
    double coefficients[6]={0};
    const int targets[5][2]={{80,48},{720,48},{720,432},{80,432},{400,240}};
    if(argc!=2 && !pointer) { fprintf(stderr,"Usage: n810-touch-calibrate OUTPUT.csv (run on a temporary VT)\n"); return 2; }
    if(pointer) {
        FILE *config=fopen(argv[2],"r");
        if(!config) {perror("mapping");return 1;}
        int n=fscanf(config,"%lf %lf %lf %lf %lf %lf",&coefficients[0],&coefficients[1],&coefficients[2],&coefficients[3],&coefficients[4],&coefficients[5]);
        int extra;do {extra=fgetc(config);} while(extra==' '||extra=='\n'||extra=='\t'||extra=='\r');
        fclose(config);
        if(n!=6 || extra!=EOF) {fprintf(stderr,"Mapping requires six coefficients\n");return 1;}
        for(int i=0;i<6;i++) if(!isfinite(coefficients[i]) || fabs(coefficients[i])>10000) return 1;
    }
    fb=open("/dev/fb0",O_RDWR|O_CLOEXEC);in=input_open();tty=open("/dev/tty",O_RDWR|O_CLOEXEC);
    if(fb<0 || in<0 || tty<0 || ioctl(fb,FBIOGET_FSCREENINFO,&f)<0 || ioctl(fb,FBIOGET_VSCREENINFO,&v)<0 || ioctl(tty,KDGETMODE,&oldmode)<0) { perror("device");goto done; }
    if(v.xres!=800 || v.yres!=480 || v.bits_per_pixel!=16 || f.visual!=FB_VISUAL_TRUECOLOR ||
       v.red.offset!=11 || v.red.length!=5 || v.green.offset!=5 || v.green.length!=6 || v.blue.offset!=0 || v.blue.length!=5 ||
       (uint64_t)(v.xoffset+800)*2>f.line_length || (uint64_t)(v.yoffset+480)*f.line_length>f.smem_len) {
        fprintf(stderr,"Requires the N810 800x480 RGB565 framebuffer\n");goto done;
    }
    saved=malloc(f.smem_len); if(!saved) goto done;
    mem=mmap(NULL,f.smem_len,PROT_READ|PROT_WRITE,MAP_SHARED,fb,0); if(mem==MAP_FAILED) {perror("mmap");goto done;}
    memcpy(saved,mem,f.smem_len);
    if(!pointer) {out=fopen(argv[1],"wx"); if(!out) {perror("output (choose a new file)");goto done;}}
    signal(SIGINT,stop);signal(SIGTERM,stop);signal(SIGHUP,stop);
    if(ioctl(tty,KDSETMODE,KD_GRAPHICS)<0) {perror("graphics");goto done;} graphics=1;
    if(pointer) {result=pointer_test(fb,in,mem,&f,&v,coefficients);goto done;}
    fprintf(out,"screen_x,screen_y,raw_x,raw_y,samples\n");fflush(out);
    long deadline=elapsed()+300;
    for(int target=0;target<5 && !stopped;target++) {
        for(int y=0;y<480;y++) for(int x=0;x<800;x++) pixel(mem,&f,&v,x,y,0x0841);
        int tx=targets[target][0],ty=targets[target][1];
        for(int k=-18;k<=18;k++) for(int thickness=-1;thickness<=1;thickness++) {
            pixel(mem,&f,&v,tx+k,ty+thickness,0xffff);pixel(mem,&f,&v,tx+thickness,ty+k,0xffff);
        }
        for(int k=0;k<=target;k++) for(int y=12;y<18;y++) for(int x=12+k*12;x<18+k*12;x++) pixel(mem,&f,&v,x,y,0x07ff);
        if(refresh(fb)<0) {perror("display refresh");goto done;}
        fprintf(stderr,"Target %d/5: tap the white cross\n",target+1);
        int x=-1,y=-1,down=0,n=0,released=0; long sx=0,sy=0;
        struct input_event e;
        while(!stopped && elapsed()<deadline && !released) {
            struct pollfd p={.fd=in,.events=POLLIN};int ready=poll(&p,1,500);
            if(ready<0 && errno==EINTR) continue;
            if(ready<0 || (p.revents&(POLLERR|POLLHUP|POLLNVAL))) {perror("input poll");goto done;}
            if(!ready) continue;
            ssize_t got=read(in,&e,sizeof(e));
            if(got<0 && (errno==EAGAIN||errno==EINTR)) continue;
            if(got!=sizeof(e)) {fprintf(stderr,"Input read failed\n");goto done;}
            if(e.type==EV_ABS && e.code==ABS_X) x=e.value;
            if(e.type==EV_ABS && e.code==ABS_Y) y=e.value;
            if(e.type==EV_KEY && e.code==BTN_TOUCH) {if(e.value) down=1; else if(down && n) released=1;else down=0;}
            if(e.type==EV_SYN && e.code==SYN_REPORT && down && x>=0 && y>=0) {sx+=x;sy+=y;n++;}
        }
        if(!released) {fprintf(stderr,"Cancelled or timed out; calibration incomplete\n");goto done;}
        fprintf(out,"%d,%d,%.3f,%.3f,%d\n",tx,ty,(double)sx/n,(double)sy/n,n);fflush(out);
        struct timespec pause={.tv_nsec=250000000};nanosleep(&pause,NULL);
    }
    if(!stopped) {result=0;fprintf(stderr,"Five targets collected. Calibration is not yet applied.\n");}
 done:
    if(graphics) {memcpy(mem,saved,f.smem_len);refresh(fb);ioctl(tty,KDSETMODE,oldmode);}
    if(out) fclose(out);
    if(mem!=MAP_FAILED) munmap(mem,f.smem_len);
    free(saved);if(tty>=0)close(tty);if(in>=0)close(in);if(fb>=0)close(fb);
    return result;
}
