/* SPDX-License-Identifier: MIT */
#define pocket_window_open pocket_base_window_open
#define pocket_window_present pocket_base_window_present
#define pocket_window_event pocket_base_window_event
#define pocket_window_close pocket_base_window_close
#include "window.c"
#undef pocket_window_close
#undef pocket_window_open
#undef pocket_window_present
#undef pocket_window_event
#ifdef __APPLE__
#include "native_text.h"
#endif
static struct window *input_window;
static unsigned canvas_width=800,canvas_height=480;
static int dynamic_canvas;
static int mobile_input;
static struct {int active,primary; SDL_TouchID device; SDL_FingerID finger;} contacts[10];

static SDL_GameController *pad;
static void find_pad(void){
 for(int i=0;!pad && i<SDL_NumJoysticks();i++)
  if(SDL_IsGameController(i))pad=SDL_GameControllerOpen(i);
}
void pocket_window_pad_sticks(int axes[4]){
 memset(axes,0,4*sizeof(int));
 if(!pad || !input_window || SDL_GetKeyboardFocus()!=input_window->window)return;
 for(int i=0;i<4;i++)axes[i]=SDL_GameControllerGetAxis(pad,(SDL_GameControllerAxis)i);
}
int pocket_window_flight_throttle(void){
 if(!pad || !input_window || SDL_GetKeyboardFocus()!=input_window->window)return 0;
 return SDL_GameControllerGetAxis(pad,SDL_CONTROLLER_AXIS_TRIGGERRIGHT)
      - SDL_GameControllerGetAxis(pad,SDL_CONTROLLER_AXIS_TRIGGERLEFT);
}
int pocket_window_flight_rudder(void){
 if(!pad || !input_window || SDL_GetKeyboardFocus()!=input_window->window)return 0;
 return SDL_GameControllerGetButton(pad,SDL_CONTROLLER_BUTTON_RIGHTSHOULDER)
      - SDL_GameControllerGetButton(pad,SDL_CONTROLLER_BUTTON_LEFTSHOULDER);
}
int pocket_window_flight_dpad(void){
 if(!pad || !input_window || SDL_GetKeyboardFocus()!=input_window->window)return 0;
 return SDL_GameControllerGetButton(pad,SDL_CONTROLLER_BUTTON_DPAD_RIGHT)
      - SDL_GameControllerGetButton(pad,SDL_CONTROLLER_BUTTON_DPAD_LEFT);
}
int pocket_window_close(void *ptr){
 if(pad){SDL_GameControllerClose(pad);pad=NULL;}
 input_window=NULL;
 return pocket_base_window_close(ptr);
}
static void *desktop_open(int fd,int mobile){
 mobile_input=mobile;memset(contacts,0,sizeof contacts);
 if(mobile){SDL_SetHint(SDL_HINT_TOUCH_MOUSE_EVENTS,"0");SDL_SetHint(SDL_HINT_MOUSE_TOUCH_EVENTS,"0");}
 void *window=pocket_window_create(fd,0,mobile);
 if(window){
  input_window=window;SDL_StopTextInput();
  if(SDL_InitSubSystem(SDL_INIT_GAMECONTROLLER)==0)find_pad();
  SDL_SetWindowResizable(input_window->window,SDL_TRUE);
  SDL_SetWindowMinimumSize(input_window->window,400,240);
  SDL_RenderSetLogicalSize(input_window->renderer,800,480);
  SDL_RenderSetVSync(input_window->renderer,1);
 }
 return window;
}
void *pocket_window_open(int fd){return desktop_open(fd,0);}
void *pocket_window_open_mobile(int fd){return desktop_open(fd,1);}
int pocket_window_canvas(void *ptr,unsigned width,unsigned height){
 struct window *w=ptr;if(!w||width<8||height<16||width>4096||height>4096)return -1;
 if(width==canvas_width&&height==canvas_height)return 0;
 SDL_Texture *texture=SDL_CreateTexture(w->renderer,SDL_PIXELFORMAT_RGB565,SDL_TEXTUREACCESS_STREAMING,width,height);
 if(!texture)return -1;
 SDL_DestroyTexture(w->texture);w->texture=texture;canvas_width=width;canvas_height=height;
 return SDL_RenderSetLogicalSize(w->renderer,width,height);
}
int pocket_window_set_size(void *ptr,int width,int height){if(!ptr||width<320||height<224||width>4096||height>4096)return -1;SDL_SetWindowSize(((struct window*)ptr)->window,width,height);return 0;}
int pocket_window_size(void *ptr,int out[2]){if(!ptr||!out)return -1;SDL_GetWindowSize(((struct window*)ptr)->window,out,out+1);return 0;}
void pocket_window_dynamic(void *ptr,int enabled){(void)ptr;dynamic_canvas=!!enabled;}
int pocket_window_draw(void *ptr,const void *pixels){
 struct window *w=ptr;if(!w||!pixels)return -1;
 if(SDL_SetRenderDrawColor(w->renderer,0,0,0,255)||SDL_RenderClear(w->renderer))return -1;
 if(SDL_UpdateTexture(w->texture,NULL,pixels,canvas_width*2)||SDL_RenderCopy(w->renderer,w->texture,NULL,NULL))return -1;
 return 0;
}
int pocket_window_present(void *ptr,const void *pixels){
 if(pocket_window_draw(ptr,pixels))return -1;
#ifdef __APPLE__
 if(pocket_native_text_draw(((struct window*)ptr)->renderer,canvas_width,canvas_height))return -1;
#endif
 SDL_RenderPresent(((struct window*)ptr)->renderer);return 0;
}
int pocket_window_fullscreen(void *ptr,int enabled){
 struct window *w=ptr;return SDL_SetWindowFullscreen(w->window,enabled?SDL_WINDOW_FULLSCREEN_DESKTOP:0);
}
int pocket_window_is_fullscreen(void *ptr){return !!(SDL_GetWindowFlags(((struct window*)ptr)->window)&SDL_WINDOW_FULLSCREEN_DESKTOP);}
void pocket_window_game_title(void *ptr,int enabled){SDL_SetWindowTitle(((struct window*)ptr)->window,enabled?"Pocket Room — Game ON · G toggle · F11 fullscreen":"Pocket Room — G game mode · F11 fullscreen");}
void pocket_window_coordinates(void *ptr,int *x,int *y){
 float lx,ly;SDL_RenderWindowToLogical(((struct window*)ptr)->renderer,*x,*y,&lx,&ly);*x=(int)lx;*y=(int)ly;
}
int pocket_window_capture(void *ptr,int enabled){
 struct window *w=ptr;
 if(SDL_SetRelativeMouseMode(enabled?SDL_TRUE:SDL_FALSE))return -1;
 SDL_SetWindowGrab(w->window,enabled?SDL_TRUE:SDL_FALSE);return 0;
}
int pocket_window_event(int out[6]){
 SDL_Event e;
 while(SDL_PollEvent(&e)){
  memset(out,0,6*sizeof(int));
  if(e.type==SDL_CONTROLLERDEVICEADDED){find_pad();continue;}
  if(e.type==SDL_CONTROLLERDEVICEREMOVED){
   if(pad && !SDL_GameControllerGetAttached(pad)){SDL_GameControllerClose(pad);pad=NULL;find_pad();}
   continue;
  }
  if(e.type==SDL_CONTROLLERBUTTONDOWN && pad && input_window &&
     SDL_GetKeyboardFocus()==input_window->window &&
     e.cbutton.which==SDL_JoystickInstanceID(SDL_GameControllerGetJoystick(pad))){
   out[0]=10;out[1]=e.cbutton.button;return 1;
  }
  if(e.type==SDL_QUIT){out[0]=1;return 1;}
  if(e.type==SDL_WINDOWEVENT){
   if(e.window.event==SDL_WINDOWEVENT_FOCUS_GAINED)SDL_StopTextInput();
   if(e.window.event==SDL_WINDOWEVENT_FOCUS_LOST){memset(contacts,0,sizeof contacts);SDL_SetRelativeMouseMode(SDL_FALSE);out[0]=6;return 1;}
   if(e.window.event==SDL_WINDOWEVENT_SIZE_CHANGED&&dynamic_canvas){out[0]=8;out[1]=e.window.data1;out[2]=e.window.data2;return 1;}
   if(e.window.event==SDL_WINDOWEVENT_SIZE_CHANGED||e.window.event==SDL_WINDOWEVENT_EXPOSED){out[0]=4;return 1;}
  }
  if(e.type==SDL_KEYDOWN&&!e.key.repeat&&input_window){
   SDL_Keycode key=e.key.keysym.sym;SDL_Keymod mods=e.key.keysym.mod;
   if(key==SDLK_F11||(key==SDLK_f&&(mods&KMOD_GUI)&&(mods&KMOD_CTRL))){
    int full=pocket_window_is_fullscreen(input_window);
    if(pocket_window_fullscreen(input_window,!full)){out[0]=1;return 1;}
    out[0]=4;return 1;
   }
   if(key==SDLK_ESCAPE&&pocket_window_is_fullscreen(input_window)&&!SDL_GetRelativeMouseMode()){
    pocket_window_fullscreen(input_window,0);out[0]=4;return 1;
   }
  }
  if(e.type==SDL_MOUSEWHEEL){
   int x,y;SDL_GetMouseState(&x,&y);if(input_window)pocket_window_coordinates(input_window,&x,&y);out[0]=2;out[1]=x;out[2]=y;
   float delta=e.wheel.preciseY?e.wheel.preciseY:(float)e.wheel.y;
   if(!delta)continue;
   int up=delta>0;if(e.wheel.direction==SDL_MOUSEWHEEL_FLIPPED)up=!up;
   out[3]=up?64:65;return 1;
  }
  if(mobile_input&&(e.type==SDL_FINGERDOWN||e.type==SDL_FINGERMOTION||e.type==SDL_FINGERUP)){
   int slot=-1,empty=-1,held=0;
   for(int i=0;i<10;i++){
    if(!contacts[i].active){if(empty<0)empty=i;continue;}
    held++;
    if(contacts[i].device==e.tfinger.touchId&&contacts[i].finger==e.tfinger.fingerId)slot=i;
   }
   if(e.type==SDL_FINGERDOWN){
    if(slot>=0||empty<0)continue;
    slot=empty;contacts[slot].active=1;contacts[slot].primary=!held;
    contacts[slot].device=e.tfinger.touchId;contacts[slot].finger=e.tfinger.fingerId;
    SDL_ShowCursor(SDL_DISABLE);
   }else if(slot<0)continue;
   out[0]=contacts[slot].primary?2:9;out[5]=slot+1;
   out[1]=(int)(e.tfinger.x*canvas_width);out[2]=(int)(e.tfinger.y*canvas_height);
   out[3]=e.type==SDL_FINGERMOTION?32:0;out[4]=e.type==SDL_FINGERUP;
   if(out[4])contacts[slot].active=0;
   return 1;
  }
  if(mobile_input&&(e.type==SDL_MOUSEMOTION||e.type==SDL_MOUSEBUTTONDOWN||e.type==SDL_MOUSEBUTTONUP)){
   Uint32 which=e.type==SDL_MOUSEMOTION?e.motion.which:e.button.which;
   if(which==SDL_TOUCH_MOUSEID)continue;
   SDL_ShowCursor(SDL_ENABLE);
  }
  if(e.type==SDL_MOUSEMOTION&&SDL_GetRelativeMouseMode()){
   out[0]=5;out[1]=e.motion.xrel;out[2]=e.motion.yrel;return 1;
  }
  if(e.type==SDL_MOUSEBUTTONDOWN||e.type==SDL_MOUSEBUTTONUP){out[0]=2;out[1]=e.button.x;out[2]=e.button.y;out[3]=e.button.button==SDL_BUTTON_LEFT?0:e.button.button==SDL_BUTTON_MIDDLE?1:2;out[4]=e.type==SDL_MOUSEBUTTONUP;return 1;}
  if(e.type==SDL_MOUSEMOTION&&e.motion.state&SDL_BUTTON_LMASK){out[0]=2;out[1]=e.motion.x;out[2]=e.motion.y;out[3]=32;return 1;}
  if(e.type==SDL_KEYDOWN||e.type==SDL_KEYUP){out[0]=3;out[1]=e.key.keysym.sym;out[3]=e.key.keysym.mod;out[4]=e.type==SDL_KEYUP;out[5]=e.key.repeat;return 1;}
 }
 return 0;
}

#include "gpu_scene.c"
