#define _GNU_SOURCE
#include <GL/gl.h>
typedef void Display; typedef unsigned long GLXDrawable;
#include <dlfcn.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
static GLfloat buf[100000];
void glXSwapBuffers(Display *display, GLXDrawable draw) {
    static int index;
    if (index) {
        GLint n=glRenderMode(GL_RENDER);
        if (n<=0) _exit(2);
        char name[128];
        snprintf(name,sizeof(name),"live-%d.float",index);
        FILE *file=fopen(name,"wb");
        if (!file || fwrite(buf,sizeof(float),n,file) != (size_t)n) _exit(3);
        fclose(file);
    }
    if (++index==7) _exit(0);
    void (*swap)(Display *,GLXDrawable)=dlsym(RTLD_NEXT,"glXSwapBuffers");
    swap(display,draw);
    usleep(50000);
    glFeedbackBuffer(100000,GL_3D_COLOR,buf);
    glRenderMode(GL_FEEDBACK);
}
