/* SPDX-License-Identifier: MIT */
#include <SDL.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
struct window {SDL_Window *window;SDL_Renderer *renderer;SDL_Texture *texture;};
void *pocket_window_open(int);
int pocket_window_close(void *);
int pocket_window_canvas(void *,unsigned,unsigned);
int pocket_window_draw(void *,const void *);
int pocket_window_event(int[6]);
int main(void){
 struct window *w=pocket_window_open(-1);if(!w)return 1;
 const int sizes[][2]={{1000,800},{887,593},{1200,700},{801,481},{640,600}};
 uint16_t *canvas=malloc(800*480*2);if(!canvas)return 2;
 for(unsigned n=0;n<5;n++){
  SDL_SetWindowSize(w->window,sizes[n][0],sizes[n][1]);SDL_Delay(30);int event[6];while(pocket_window_event(event)){}
  for(unsigned frame=0;frame<4;frame++){
   for(unsigned i=0;i<800*480;i++)canvas[i]=frame&1?0x7e0:0xf800;
   /* Seed garbage into the whole target before the real draw. */
   SDL_SetRenderDrawColor(w->renderer,255,0,255,255);SDL_RenderClear(w->renderer);
   if(pocket_window_draw(w,canvas))return 3;
   int width,height;SDL_GetRendererOutputSize(w->renderer,&width,&height);
   uint32_t *pixels=malloc((size_t)width*height*4);if(!pixels)return 4;
   SDL_RenderSetLogicalSize(w->renderer,0,0);
   SDL_Rect all={0,0,width,height};
   if(SDL_RenderReadPixels(w->renderer,&all,SDL_PIXELFORMAT_ARGB8888,pixels,width*4))return 5;
   SDL_RenderSetLogicalSize(w->renderer,800,480);
   unsigned red=0,green=0,black=0,bad=0;
   for(int y=0;y<height;y++)for(int x=0;x<width;x++){
    unsigned c=pixels[y*width+x]&0xffffff;
    if(c==0)black++;else if((c&0xffff)==0)red++;else if((c&0xff00ff)==0)green++;else {if(!bad)fprintf(stderr,"unexpected pixel %x at %d,%d\n",c,x,y);bad++;}
   }
   free(pixels);
   if(bad||(!(frame&1)&&(!red||green))||((frame&1)&&(!green||red))){fprintf(stderr,"Uncleared/mixed frame: %ux%u bad=%u black=%u\n",width,height,bad,black);return 6;}
   SDL_RenderPresent(w->renderer);
  }
  printf("%dx%d: alternating frames and all border pixels clean\n",sizes[n][0],sizes[n][1]);
 }
 free(canvas);pocket_window_close(w);return 0;
}
