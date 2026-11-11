/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Standard SDL window/input for the graphical frontend's development host.
 * Device framebuffer ownership remains the Nokia presenter's responsibility. */
#include <SDL.h>
#include <stdlib.h>
struct window {SDL_Window *window;SDL_Renderer *renderer;SDL_Texture *texture;};
static void *pocket_window_create(int fd,int hidden){
 (void)fd;
 if(SDL_Init(SDL_INIT_VIDEO|SDL_INIT_EVENTS))return NULL;
 struct window *w=calloc(1,sizeof(*w));if(!w)return NULL;
 w->window=SDL_CreateWindow("Pocket",SDL_WINDOWPOS_CENTERED,SDL_WINDOWPOS_CENTERED,800,480,(hidden?SDL_WINDOW_HIDDEN:SDL_WINDOW_SHOWN)
#ifdef __APPLE__
 |SDL_WINDOW_ALLOW_HIGHDPI
#endif
 );
 if(w->window)w->renderer=SDL_CreateRenderer(w->window,-1,SDL_RENDERER_ACCELERATED);
 if(w->renderer)w->texture=SDL_CreateTexture(w->renderer,SDL_PIXELFORMAT_RGB565,SDL_TEXTUREACCESS_STREAMING,800,480);
 if(!w->texture){if(w->renderer)SDL_DestroyRenderer(w->renderer);if(w->window)SDL_DestroyWindow(w->window);free(w);SDL_Quit();return NULL;}
 return w;
}
void *pocket_window_open(int fd){return pocket_window_create(fd,0);}
void *pocket_window_open_hidden(int fd){return pocket_window_create(fd,1);}
const char *pocket_window_error(void){return SDL_GetError();}
int pocket_window_present(void *ptr,const void *pixels){
 struct window *w=ptr;
 if(SDL_UpdateTexture(w->texture,NULL,pixels,1600)||SDL_RenderCopy(w->renderer,w->texture,NULL,NULL))return -1;
 SDL_RenderPresent(w->renderer);return 0;
}
/* type1 quit,2 pointer,3 key,4 redraw. Positions stay native800x480. */
int pocket_window_event(int out[6]){
 SDL_Event e;
 while(SDL_PollEvent(&e)){
  for(unsigned i=0;i<6;++i)out[i]=0;
  if(e.type==SDL_QUIT){out[0]=1;return 1;}
  if(e.type==SDL_WINDOWEVENT&&e.window.event==SDL_WINDOWEVENT_EXPOSED){out[0]=4;return 1;}
  if(e.type==SDL_MOUSEBUTTONDOWN||e.type==SDL_MOUSEBUTTONUP){out[0]=2;out[1]=e.button.x;out[2]=e.button.y;out[3]=e.button.button==SDL_BUTTON_LEFT?0:e.button.button==SDL_BUTTON_MIDDLE?1:2;out[4]=e.type==SDL_MOUSEBUTTONUP;return 1;}
  if(e.type==SDL_MOUSEMOTION&&e.motion.state&SDL_BUTTON_LMASK){out[0]=2;out[1]=e.motion.x;out[2]=e.motion.y;out[3]=32;return 1;}
  if(e.type==SDL_KEYDOWN||e.type==SDL_KEYUP){out[0]=3;out[1]=e.key.keysym.sym;out[4]=e.type==SDL_KEYUP;out[5]=e.key.repeat;return 1;}
 }
 return 0;
}
int pocket_window_close(void *ptr){struct window *w=ptr;if(!w)return 0;
#ifdef __APPLE__
 extern void pocket_native_text_close(void);pocket_native_text_close();
#endif
SDL_DestroyTexture(w->texture);SDL_DestroyRenderer(w->renderer);SDL_DestroyWindow(w->window);free(w);SDL_Quit();return 0;}
