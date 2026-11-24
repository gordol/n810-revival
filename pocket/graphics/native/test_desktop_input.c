/* SPDX-License-Identifier: MIT */
#include <SDL.h>
#define CHECK(value) do { if(!(value)){fprintf(stderr,"Input check failed at line %d\n",__LINE__);if(w)pocket_window_close(w);return 1;} } while(0)
#include <stdio.h>
void *pocket_window_open(int);
void *pocket_window_open_mobile(int);
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
 w=pocket_window_open_mobile(-1);CHECK(w);while(pocket_window_event(out)){}
 SDL_zero(e);e.type=SDL_FINGERDOWN;e.tfinger.x=.75f;e.tfinger.y=.25f;e.tfinger.fingerId=7;
 CHECK(SDL_PeepEvents(&e,1,SDL_ADDEVENT,0,0)==1);
 CHECK(pocket_window_event(out)&&out[0]==2&&out[1]==600&&out[2]==120&&!out[4]);
 int first=out[5];CHECK(first>0);
 e.tfinger.fingerId=0x100000007LL;e.tfinger.x=.25f;
 CHECK(SDL_PeepEvents(&e,1,SDL_ADDEVENT,0,0)==1);
 SDL_Event pair[2];pair[0]=e;pair[0].type=SDL_FINGERUP;pair[0].tfinger.fingerId=7;
 pair[1]=e;pair[1].type=SDL_FINGERMOTION;pair[1].tfinger.x=.4f;
 CHECK(SDL_PeepEvents(pair,2,SDL_ADDEVENT,0,0)==2);
 e.type=SDL_FINGERUP;CHECK(SDL_PeepEvents(&e,1,SDL_ADDEVENT,0,0)==1);
 int index=0,second=0;
 for(unsigned i=0;i<100&&index<4;i++){
  if(!pocket_window_event(out)){SDL_Delay(2);continue;}
  if((out[0]!=2&&out[0]!=9)||!out[5])continue;
  if(index==0){second=out[5];CHECK(second!=first&&out[0]==9&&!out[4]);}
  if(index==1)CHECK(out[0]==2&&out[4]&&out[5]==first);
  if(index==2)CHECK(out[0]==9&&out[3]==32&&out[5]==second);
  if(index==3)CHECK(out[0]==9&&out[4]&&out[5]==second);
  index++;
 }
 CHECK(index==4);
 pocket_window_close(w);
 puts("Native SDL text-input, shift, wheel, captured mouse and focus-loss checks pass.");return 0;
}
