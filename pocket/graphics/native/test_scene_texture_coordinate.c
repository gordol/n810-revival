/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "scene_texture_coordinate.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 unsigned cases=0;float result;
 for(unsigned image=1;image<=4096;image++)for(unsigned origin=0;origin<image;origin+=128){
  unsigned extent=image-origin<128?image-origin:128;
  for(int flip=0;flip<=1;flip++){
   assert(scene_texture_coordinate((float)origin/image,image,origin,extent,128,flip,&result));
   assert(result>=0&&result<=1&&fabsf(result-(flip?1:0))<0.00001f);
   assert(scene_texture_coordinate((float)(origin+extent)/image,image,origin,extent,128,flip,&result));
   assert(result>=0&&result<=1&&fabsf(result-(flip?1-extent/128.f:extent/128.f))<0.00001f);
   assert(!scene_texture_coordinate((float)((int)origin-1)/image,image,origin,extent,128,flip,&result));
   assert(!scene_texture_coordinate((float)(origin+extent+1)/image,image,origin,extent,128,flip,&result));
   cases+=4;
  }
 }
 assert(!scene_texture_coordinate(NAN,800,128,128,128,0,&result));
 assert(!scene_texture_coordinate(INFINITY,800,128,128,128,0,&result));
 assert(scene_texture_coordinate(.25f,800,128,128,128,0,&result)&&result==.5625f);
 printf("PASS: %u tile-edge and outside-tile cases; interior unchanged; nonfinite rejected\n",cases);
}
