/* SPDX-License-Identifier: MIT */
#include <SDL.h>
#define CHECK(value) do { if(!(value)){fprintf(stderr,"Input check failed at line %d\n",__LINE__);if(w)pocket_window_close(w);return 1;} } while(0)
#include <stdio.h>
void *pocket_window_open(int);
int pocket_window_close(void *);
int pocket_window_event(int[6]);
int pocket_window_capture(void *,int);
void pocket_window_coordinates(void *,int *,int *);
int main(void){
 void *w=pocket_window_open(-1);CHECK(w);CHECK(!SDL_IsTextInputActive());
 int out[6];while(pocket_window_event(out)){}
 SDL_Event e;SDL_zero(e);e.type=SDL_KEYDOWN;e.key.keysym.sym=SDLK_LSHIFT;CHECK(SDL_PushEvent(&e)==1);
 CHECK(pocket_window_event(out)==1&&out[0]==3&&out[1]==SDLK_LSHIFT&&!out[4]);
 SDL_zero(e);e.type=SDL_MOUSEWHEEL;e.wheel.windowID=SDL_GetWindowID(*(SDL_Window**)w);e.wheel.y=1;e.wheel.preciseY=1;CHECK(SDL_PeepEvents(&e,1,SDL_ADDEVENT,0,0)==1);
 int wheel=0;for(unsigned i=0;i<100;i++){if(pocket_window_event(out)){if(out[0]==2&&out[3]==64){wheel=1;break;}}SDL_Delay(2);}CHECK(wheel);
 CHECK(pocket_window_capture(w,1)==0);while(pocket_window_event(out)){}
 SDL_zero(e);e.type=SDL_MOUSEMOTION;e.motion.xrel=17;e.motion.yrel=-9;CHECK(SDL_PushEvent(&e)==1);
 CHECK(pocket_window_event(out)==1&&out[0]==5&&out[1]==17&&out[2]==-9);
 SDL_zero(e);e.type=SDL_WINDOWEVENT;e.window.event=SDL_WINDOWEVENT_FOCUS_LOST;CHECK(SDL_PushEvent(&e)==1);
 int lost=0;for(unsigned i=0;i<100;i++){int got=pocket_window_event(out);if(got&&out[0]==6){lost=1;break;}SDL_Delay(2);}
 CHECK(lost&&!SDL_GetRelativeMouseMode());
 SDL_SetWindowSize(*(SDL_Window**)w,1000,800);SDL_Delay(50);while(pocket_window_event(out)){}
 int x=500,y=400;pocket_window_coordinates(w,&x,&y);CHECK(abs(x-400)<=1&&abs(y-240)<=1);
 CHECK(pocket_window_capture(w,0)==0);pocket_window_close(w);
 puts("Native SDL text-input, shift, wheel, captured mouse and focus-loss checks pass.");return 0;
}
