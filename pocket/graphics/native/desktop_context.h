/* SPDX-License-Identifier: MIT */
#ifndef POCKET_MAC_CONTEXT_H
#define POCKET_MAC_CONTEXT_H
#include <SDL.h>
#ifdef __APPLE__
#include <OpenGL/gl.h>
#include <OpenGL/glext.h>
#else
#include <GL/gl.h>
#include <GL/glext.h>
#endif
#include <stdint.h>
#include <string.h>
#include <stdio.h>
#include <stdlib.h>
#define OSMESA_RGB_565 0x5
#define OSMESA_Y_UP 0x11
struct mac_context {SDL_Window *window;SDL_GLContext context;uint16_t *buffer;uint16_t readback[160000];};
typedef struct mac_context *OSMesaContext;
static OSMesaContext mac_current;
static OSMesaContext OSMesaCreateContextExt(unsigned format,int depth,int stencil,int accum,void *share) {
 (void)format;(void)stencil;(void)accum;(void)share;
 if(SDL_InitSubSystem(SDL_INIT_VIDEO|SDL_INIT_EVENTS))return NULL;
 OSMesaContext c=calloc(1,sizeof(*c));if(!c)return NULL;
 SDL_GL_SetAttribute(SDL_GL_CONTEXT_MAJOR_VERSION,2);SDL_GL_SetAttribute(SDL_GL_CONTEXT_MINOR_VERSION,1);
 SDL_GL_SetAttribute(SDL_GL_DEPTH_SIZE,depth);
 c->window=SDL_CreateWindow("Pocket GPU context",0,0,400,400,SDL_WINDOW_OPENGL|SDL_WINDOW_HIDDEN);
 if(c->window)c->context=SDL_GL_CreateContext(c->window);
 if(!c->context){if(c->window)SDL_DestroyWindow(c->window);free(c);return NULL;}
 return c;
}
static int OSMesaMakeCurrent(OSMesaContext c,void *buffer,unsigned type,int w,int h) {
 if(!c||!buffer||type!=GL_UNSIGNED_SHORT_5_6_5||w!=400||h!=400||SDL_GL_MakeCurrent(c->window,c->context))return 0;
 c->buffer=buffer;mac_current=c;return 1;
}
static void OSMesaDestroyContext(OSMesaContext c){if(!c)return;if(mac_current==c)mac_current=NULL;SDL_GL_DeleteContext(c->context);SDL_DestroyWindow(c->window);free(c);}
static void OSMesaPixelStore(int key,int value){(void)key;(void)value;}
static OSMesaContext OSMesaGetCurrentContext(void){return mac_current;}
static int OSMesaGetColorBuffer(OSMesaContext c,int *w,int *h,int *format,void **buffer){if(!c)return 0;*w=400;*h=400;*format=OSMESA_RGB_565;*buffer=c->buffer;return 1;}
static void mac_finish(void){
 glFinish();if(!mac_current)return;
 glPixelStorei(GL_PACK_ALIGNMENT,2);
 glReadPixels(0,0,400,400,GL_RGB,GL_UNSIGNED_SHORT_5_6_5,mac_current->readback);
 for(unsigned y=0;y<400;y++)memcpy(mac_current->buffer+y*400,mac_current->readback+(399-y)*400,800);
}
const char *pocket_mac_renderer(void){return (const char*)glGetString(GL_RENDERER);}
#define glFinish mac_finish
#endif
