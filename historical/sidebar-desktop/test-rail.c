/* Integration test against an isolated X server; never uses the physical display. */
#define _POSIX_C_SOURCE 200809L
#include <X11/Xlib.h>
#include <X11/Xatom.h>
#include <X11/keysym.h>
#include <X11/extensions/XTest.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>
static Display *d;
static void pause_tick(void) { struct timespec ts={0,100000000}; nanosleep(&ts,NULL); }
static void key(KeySym sym) {
 KeyCode code=XKeysymToKeycode(d,sym);
 XTestFakeKeyEvent(d,code,True,CurrentTime); XTestFakeKeyEvent(d,code,False,CurrentTime); XFlush(d);
}
static Window find_rail(void) {
 Window root,parent,*children=NULL,result=None; unsigned n=0;
 XQueryTree(d,DefaultRootWindow(d),&root,&parent,&children,&n);
 for(unsigned i=0;i<n;i++){char *name=NULL;XFetchName(d,children[i],&name);
  if(name && !strcmp(name,"N810 app switcher"))result=children[i];
  if(name)XFree(name);
 }
 if(children)XFree(children);
 return result;
}
static int mapped(Window w) { XWindowAttributes a;return XGetWindowAttributes(d,w,&a)&&a.map_state==IsViewable; }
static Window active(void) {
 Atom type;int format;unsigned long n,left;unsigned char *data=NULL;Window result=None;
 XGetWindowProperty(d,DefaultRootWindow(d),XInternAtom(d,"_NET_ACTIVE_WINDOW",False),0,1,False,XA_WINDOW,&type,&format,&n,&left,&data);
 if(data && type==XA_WINDOW && format==32 && n==1)result=*(Window *)data;
 if(data)XFree(data);
 return result;
}
static int client_width(Window w) {
 XWindowAttributes a; return XGetWindowAttributes(d,w,&a) ? a.width : -1;
}
static Window launched(Window a, Window b) {
 Atom type;int format;unsigned long n,left;unsigned char *data=NULL;Window result=None;
 XGetWindowProperty(d,DefaultRootWindow(d),XInternAtom(d,"_NET_CLIENT_LIST",False),0,64,False,XA_WINDOW,&type,&format,&n,&left,&data);
 if(data && type==XA_WINDOW && format==32) for(unsigned long i=0;i<n;i++) {
  Window w=((Window *)data)[i]; char *name=NULL; XFetchName(d,w,&name);
  if(w!=a && w!=b && name && strcmp(name,"N810 rail space") && strcmp(name,"N810 app switcher")) result=w;
  if(name)XFree(name);
 }
 if(data)XFree(data);
 return result;
}
int main(void) {
 d=XOpenDisplay(NULL);if(!d)return 1;
 Window a=XCreateSimpleWindow(d,DefaultRootWindow(d),0,0,200,100,0,0,0);
 Window b=XCreateSimpleWindow(d,DefaultRootWindow(d),0,0,200,100,0,0,0);
 Atom delete=XInternAtom(d,"WM_DELETE_WINDOW",False);
 XSetWMProtocols(d,a,&delete,1);XSetWMProtocols(d,b,&delete,1);
 XStoreName(d,a,"Shell");XStoreName(d,b,"Mail");XMapWindow(d,a);XMapWindow(d,b);XSync(d,False);
 Window rail=None;for(int i=0;i<50 && rail==None;i++){pause_tick();rail=find_rail();}
 if(rail==None){fputs("No rail process.\n",stderr);return 1;}
 if(mapped(rail)){fputs("Rail must start hidden.\n",stderr);return 1;}
 Window before=active();
 key(XK_F14);pause_tick();if(!mapped(rail)){fputs("Switcher did not open.\n",stderr);return 1;}
 key(XK_Escape);pause_tick();if(mapped(rail)){fputs("Escape did not dismiss.\n",stderr);return 1;}
 key(XK_F14);pause_tick();key(XK_F17);key(XK_F14);pause_tick();
 if(mapped(rail)||active()==before||active()==None){fputs("Previous/select failed.\n",stderr);return 1;}
 key(XK_F14);pause_tick();
 XEvent e={0};e.xbutton.type=ButtonPress;e.xbutton.display=d;e.xbutton.window=rail;e.xbutton.y=20;e.xbutton.button=1;
 XSendEvent(d,rail,False,ButtonPressMask,&e);
 e.xbutton.type=ButtonRelease;XSendEvent(d,rail,False,ButtonReleaseMask,&e);
 e.xbutton.type=ButtonPress;XFlush(d);pause_tick();
 if(mapped(rail)){fputs("Touch selection did not dismiss.\n",stderr);return 1;}
 Window focused=active();
 key(XK_F15);pause_tick();
 if(!mapped(rail)||client_width(focused)!=752){fputs("Pinned rail did not reserve 48 pixels.\n",stderr);return 1;}
 key(XK_F14);pause_tick();key(XK_F16);key(XK_F14);pause_tick();
 if(!mapped(rail)||active()==focused){fputs("Closed-keyboard pinned selection failed.\n",stderr);return 1;}
 focused=active();
 key(XK_F14);pause_tick();key(XK_Escape);pause_tick();
 if(!mapped(rail)){fputs("Back hid pinned rail.\n",stderr);return 1;}
 key(XK_F11);pause_tick();
 if(mapped(rail)||client_width(focused)!=800){fputs("Fullscreen did not reclaim rail space.\n",stderr);return 1;}
 key(XK_F14);pause_tick();
 e.xbutton.y=2*48+20;
 XSendEvent(d,rail,False,ButtonPressMask,&e);XFlush(d);pause_tick();
 if(!mapped(rail)){fputs("App picker did not stay open.\n",stderr);return 1;}
 key(XK_F14);
 Window added=None;for(int i=0;i<50 && added==None;i++){pause_tick();added=launched(a,b);}
 if(added==None||mapped(rail)){fputs("App picker did not launch terminal.\n",stderr);return 1;}
 key(XK_F14);pause_tick();
 e.xbutton.y=20;e.xbutton.time=1000;e.xbutton.type=ButtonPress;
 XSendEvent(d,rail,False,ButtonPressMask,&e);
 e.xbutton.type=ButtonRelease;e.xbutton.time=2000;
 XSendEvent(d,rail,False,ButtonReleaseMask,&e);XFlush(d);pause_tick();
 if(!mapped(rail)){fputs("Hold did not open actions.\n",stderr);return 1;}
 key(XK_Down);key(XK_Return);pause_tick();
 int requested=0;while(XPending(d)){XEvent event;XNextEvent(d,&event);
  if(event.type==ClientMessage && (Atom)event.xclient.data.l[0]==delete)requested=1;
 }
 if(!requested){fputs("Close did not request WM_DELETE_WINDOW.\n",stderr);return 1;}
 const char *screen=getenv("N810_TEST_SCREEN_DIR");
 char lock_path[1024];snprintf(lock_path,sizeof lock_path,"%s/locked",screen);
 FILE *lock=fopen(lock_path,"w");if(!lock)return 1;fclose(lock);pause_tick();
 key(XK_F14);key(XK_F15);pause_tick();
 if(mapped(rail)){fputs("Locked GUI accepted shortcut.\n",stderr);return 1;}
 int grab=XGrabPointer(d,DefaultRootWindow(d),False,0,GrabModeAsync,GrabModeAsync,None,None,CurrentTime);
 if(grab!=AlreadyGrabbed){fputs("Lock did not inhibit touch.\n",stderr);return 1;}
 unlink(lock_path);pause_tick();
 grab=XGrabPointer(d,DefaultRootWindow(d),False,0,GrabModeAsync,GrabModeAsync,None,None,CurrentTime);
 if(grab!=GrabSuccess){fputs("Unlock did not release touch.\n",stderr);return 1;}
 XUngrabPointer(d,CurrentTime);
 key(XK_F14);pause_tick();key(XK_Escape);pause_tick();
 XKillClient(d,added);
 puts("PASS: closed-keyboard switch/select and app launch, touch, pinned rail resize/restore, Back, lock/unlock input inhibition.");
 XDestroyWindow(d,a);XDestroyWindow(d,b);XCloseDisplay(d);return 0;
}
