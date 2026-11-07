/* SPDX-License-Identifier: MIT
 * Standard-GL diagnostic workload, separate from unchanged glxgears.
 * Shared grid vertices expose input reuse; motion and color changes vary it.
 */
#define _POSIX_C_SOURCE 200809L
#include <GL/gl.h>
#include <GL/glx.h>
#include <X11/Xlib.h>
#include <X11/keysym.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static double now(void){struct timespec t;clock_gettime(CLOCK_MONOTONIC,&t);return t.tv_sec+t.tv_nsec/1e9;}
static void vertex(float x,float y){glNormal3f(0,0,1);glVertex3f(x,y,0);}
int main(int argc,char **argv)
{
 unsigned cells=12,frames=0,limit=0;int moving=0,colors=0;
 for(int i=1;i<argc;++i){
  if(!strcmp(argv[i],"--moving"))moving=1;
  else if(!strcmp(argv[i],"--colors"))colors=1;
  else if(!strcmp(argv[i],"--cells")&&i+1<argc)cells=(unsigned)strtoul(argv[++i],NULL,10);
  else if(!strcmp(argv[i],"--frames")&&i+1<argc)limit=(unsigned)strtoul(argv[++i],NULL,10);
  else{fprintf(stderr,"usage: %s [--moving] [--colors] [--cells 1..15] [--frames N]\n",argv[0]);return 2;}
 }
 if(!cells||cells>15)return 2;
 Display *d=XOpenDisplay(NULL);if(!d)return 3;
 int attributes[]={GLX_RGBA,GLX_DOUBLEBUFFER,GLX_DEPTH_SIZE,16,None};XVisualInfo *v=glXChooseVisual(d,DefaultScreen(d),attributes);if(!v)return 4;
 Colormap cm=XCreateColormap(d,RootWindow(d,v->screen),v->visual,AllocNone);
 XSetWindowAttributes a={.colormap=cm,.event_mask=ExposureMask|KeyPressMask|StructureNotifyMask};
 Window w=XCreateWindow(d,RootWindow(d,v->screen),200,40,400,400,0,v->depth,InputOutput,v->visual,CWColormap|CWEventMask,&a);
 XStoreName(d,w,"MBX standard-GL profiling grid (not glxgears)");
 GLXContext ctx=glXCreateContext(d,v,NULL,True);if(!ctx||!glXMakeCurrent(d,w,ctx))return 5;
 XMapWindow(d,w);XSync(d,False);
 glViewport(0,0,400,400);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(-1,1,-1,1,1,5);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 GLfloat light[]={5,5,10,0};glLightfv(GL_LIGHT0,GL_POSITION,light);
 glEnable(GL_LIGHTING);glEnable(GL_LIGHT0);glEnable(GL_NORMALIZE);glEnable(GL_COLOR_MATERIAL);glColorMaterial(GL_FRONT_AND_BACK,GL_AMBIENT_AND_DIFFUSE);
 glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);glEnable(GL_CULL_FACE);glShadeModel(GL_FLAT);glClearColor(0,0,0,0);
 printf("MBX_PROFILE_SCENE renderer=%s cells=%u moving=%d colors=%d\n",glGetString(GL_RENDERER),cells,moving,colors);fflush(stdout);
 unsigned count=0;double began=now();int done=0;
 while(!done&&(!limit||frames<limit)){
  while(XPending(d)){XEvent e;XNextEvent(d,&e);if(e.type==KeyPress&&XLookupKeysym(&e.xkey,0)==XK_Escape)done=1;if(e.type==ConfigureNotify)glViewport(0,0,e.xconfigure.width,e.xconfigure.height);}
  glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);glLoadIdentity();glTranslatef(0,0,-2);if(moving)glRotatef((frames%360)*.25f,0,0,1);
  glBegin(GL_TRIANGLES);
  for(unsigned y=0;y<cells;++y)for(unsigned x=0;x<cells;++x){
   float x0=-.6f+1.2f*x/cells,x1=-.6f+1.2f*(x+1)/cells,y0=-.6f+1.2f*y/cells,y1=-.6f+1.2f*(y+1)/cells;
   if(colors&&((x+y)&1))glColor3f(.8f,.2f,.1f);else glColor3f(.2f,.5f,.8f);
   vertex(x0,y0);vertex(x1,y0);vertex(x1,y1);vertex(x0,y0);vertex(x1,y1);vertex(x0,y1);
  }
  glEnd();glXSwapBuffers(d,w);++frames;++count;
  double elapsed=now()-began;if(elapsed>=5){printf("MBX_PROFILE_SCENE %u frames in %.3f seconds = %.3f FPS\n",count,elapsed,count/elapsed);fflush(stdout);count=0;began=now();}
 }
 glFinish();GLenum error=glGetError();glXMakeCurrent(d,None,NULL);glXDestroyContext(d,ctx);XDestroyWindow(d,w);XFreeColormap(d,cm);XFree(v);XCloseDisplay(d);
 return error==GL_NO_ERROR?0:6;
}
