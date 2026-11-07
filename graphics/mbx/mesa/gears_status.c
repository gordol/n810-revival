/* SPDX-License-Identifier: MIT
 * Companion status window for the unchanged Debian glxgears executable.
 * Mode switches to GPU only after the Mesa backend reports completed jobs.
 * FPS comes from glxgears' own measured output, never a nominal refresh rate.
 */
#include <X11/Xlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/select.h>

static char mode[64]="Preparing graphics",fps[64]="Startup in progress",jobs[64]="GPU: awaiting completion";
static unsigned frames,fps_reports;
static const char *geometry="Transform/light: CPU";
static void draw(Display *d,Window w,GC gc)
{
    const char *lines[]={"Standard glxgears",mode,fps,jobs,"Whole frame per GPU job",geometry, "400x400; full quality"};
    XClearWindow(d,w);
    for(unsigned i=0;i<sizeof(lines)/sizeof(lines[0]);++i)
        XDrawString(d,w,gc,6,18+19*i,lines[i],strlen(lines[i]));
    XFlush(d);
}
static int line(const char *s)
{
    char previous_mode[64],previous_fps[64],previous_jobs[64];
    memcpy(previous_mode,mode,64);memcpy(previous_fps,fps,64);memcpy(previous_jobs,jobs,64);
    unsigned count,triangles,j;float seconds,rate;int end=0;
    if(!strncmp(s,"N810_MBX_STAGE ",15)){
        snprintf(mode,sizeof(mode),"%s",s+15);
        strcpy(fps,"Startup in progress");
    }
    if(sscanf(s,"%u frames in %f seconds = %f FPS",&count,&seconds,&rate)==3)
        snprintf(fps,sizeof(fps),"FPS: %.3f (%s)",rate,fps_reports++?"measured":"startup");
    if(sscanf(s,"N810_MBX_GPU_FRAME triangles=%u GPU_jobs=%u CPU_raster_triangles=0%n",&triangles,&j,&end)==2 && end && !s[end] && j){
        strcpy(mode,"GPU raster: verified");
        if(!frames)strcpy(fps,"FPS: 5-second sample");
        ++frames;
        snprintf(jobs,sizeof(jobs),"Batch: %u triangles",triangles);
    }else if(sscanf(s,"N810_MBX_GPU_FRAME completed=%u GPU_jobs=%u CPU_raster_triangles=0 async=1%n",&count,&j,&end)==2 && end && !s[end] && count && j){
        strcpy(mode,"GPU raster: verified");
        if(!frames)strcpy(fps,"FPS: 5-second sample");
        frames=count;
        snprintf(jobs,sizeof(jobs),"GPU completed: %u",count);
    }else if(strstr(s,"N810_MBX_GPU_VERTEX")&&strstr(s,"CPU_shaded_vertices=0")){geometry="Transform/light: GPU";
    }else if(strstr(s,"GL_RENDERER")&&strstr(s,"softpipe"))strcpy(mode,"CPU software rendering");
    if(strstr(s,"N810_MBX_GPU_FAILED"))strcpy(mode,"GPU FAILED - test stopped");
    return strcmp(previous_mode,mode)||strcmp(previous_fps,fps)||strcmp(previous_jobs,jobs);
}
int main(int argc,char **argv)
{
    Display *d=XOpenDisplay(NULL);if(!d)return 1;
    if(argc==2&&!strcmp(argv[1],"--ready-only")){XSync(d,False);XCloseDisplay(d);return 0;}
    int screen=DefaultScreen(d);
    Window w=XCreateSimpleWindow(d,RootWindow(d,screen),4,8,190,170,1,WhitePixel(d,screen),BlackPixel(d,screen));
    XStoreName(d,w,"Nokia rendering evidence");XSelectInput(d,w,ExposureMask|StructureNotifyMask);
    GC gc=XCreateGC(d,w,0,NULL);XSetForeground(d,gc,WhitePixel(d,screen));
    XMapRaised(d,w);XFlush(d);
    char buffer[32768];size_t used=0;int input_open=1;
    for(;;){
        while(XPending(d)){XEvent e;XNextEvent(d,&e);if(e.type==Expose)draw(d,w,gc);}
        fd_set f;FD_ZERO(&f);FD_SET(ConnectionNumber(d),&f);if(input_open)FD_SET(0,&f);
        int n=select(ConnectionNumber(d)+1,&f,NULL,NULL,NULL);if(n<0)break;
        if(input_open&&FD_ISSET(0,&f)){
            ssize_t got=read(0,buffer+used,sizeof(buffer)-used-1);
            if(got<=0){input_open=0;continue;}
            used+=got;buffer[used]=0;
            char *start=buffer,*end;int changed=0;
            while((end=strchr(start,'\n'))){*end=0;changed|=line(start);start=end+1;}
            size_t remaining=buffer+used-start;memmove(buffer,start,remaining);used=remaining;
            if(used==sizeof(buffer)-1)used=0;
            if(changed)draw(d,w,gc);
        }
    }
    XFreeGC(d,gc);XDestroyWindow(d,w);XCloseDisplay(d);return 0;
}
