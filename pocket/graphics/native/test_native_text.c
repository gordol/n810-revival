/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "native_text.h"
#include <stdio.h>
#include <assert.h>
#include <string.h>
int main(void){
 assert(pocket_native_text_density(1774,1186,887,593,880,592)==2);
 assert(pocket_native_text_density(887,593,887,593,880,592)==1);
 assert(pocket_native_text_density(640,160,0,0,320,80)==2);
 assert(!pocket_native_text_density(0,160,0,0,320,80));
 unsigned previous_white=0,previous_partial=0;
 for(unsigned scale=1;scale<=2;scale++){
  unsigned cols=40,rows=5,w=cols*8,h=rows*16;
  SDL_Surface *surface=SDL_CreateRGBSurfaceWithFormat(0,w*scale,h*scale,32,SDL_PIXELFORMAT_RGBA32);
  SDL_Renderer *r=SDL_CreateSoftwareRenderer(surface);assert(r);assert(!SDL_RenderSetLogicalSize(r,w,h));
  uint32_t data[400]={0};const char *text="Pocket | Stations N0ANT 144.390 MHz";
  for(unsigned i=0;text[i];i++){data[(cols+i)*2]=text[i];data[(cols+i)*2+1]=0xffff;}
  assert(!pocket_native_text_stage(data,400));SDL_SetRenderDrawColor(r,20,24,28,255);SDL_RenderClear(r);
  assert(!pocket_native_text_draw(r,w,h));SDL_RenderPresent(r);
  const char *directory=getenv("POCKET_TEXT_TEST_OUTPUT");
  if(directory){char name[1024];snprintf(name,sizeof(name),"%s/native-text-%ux.bmp",directory,scale);assert(!SDL_SaveBMP(surface,name));}
  unsigned white=0,partial=0;for(unsigned y=0;y<h*scale;y++)for(unsigned x=0;x<w*scale;x++){
   unsigned char *p=(unsigned char*)surface->pixels+y*surface->pitch+x*4;
   if(p[0]>245)white++;else if(p[0]>24)partial++;
  }
  assert(white&&partial);if(scale==2)assert(white!=previous_white*4||partial!=previous_partial*4);previous_white=white;previous_partial=partial;printf("%ux: white=%u antialias=%u\n",scale,white,partial);
  pocket_native_text_close();SDL_DestroyRenderer(r);SDL_FreeSurface(surface);
 }
 struct mark {uint32_t index,ch;uint64_t ink;} marks[]={{0,65,UINT64_C(0xffffff)<<24},{4,66,0}};
 uint32_t target[8]={0};
 assert(!pocket_native_text_marks(target,8,2,2,marks,1,1,1,2,2));assert(target[6]==65&&target[7]==65535);
 uint32_t before[8];memcpy(before,target,sizeof(target));
 assert(pocket_native_text_marks(target,8,2,2,marks,2,0,0,2,2)==-1);assert(!memcmp(before,target,sizeof(target)));
 uint32_t guarded[12]={7,7,65,0xffff,66,0xffff,67,0xffff,68,0xffff,8,8};
 assert(pocket_native_text_clear(guarded+2,8,2,2,-8,-16,16,32)==0);
 assert(guarded[0]==7&&guarded[1]==7&&guarded[10]==8&&guarded[11]==8);
 assert(guarded[2]==0&&guarded[4]==66&&guarded[6]==67);
 assert(pocket_native_text_clear(guarded+2,7,2,2,0,0,8,16)==-1);
 assert(pocket_native_text_clear(guarded+2,8,2,2,1,0,8,16)==-1);
 assert(pocket_native_text_stage(NULL,4)==-1);assert(pocket_native_text_stage(NULL,0)==0);
 return 0;
}
