// SPDX-License-Identifier: MIT
#include "mask_batch_plan.h"
#include <cassert>
#include <cstring>
#include <vector>
int main(){
 for(unsigned w=1;w<=126;w++)for(unsigned h=1;h<=126;h++){
  sg::mask_shelf shelf;std::vector<sg::mask_placement> placed;sg::mask_placement next;
  for(unsigned i=0;i<64&&shelf.place(w,h,next);i++){
   assert(next.x>=1&&next.y>=1&&next.x+w<128&&next.y+h<128);
   for(auto p:placed)assert(next.x>=p.x+w+2||p.x>=next.x+w+2||next.y>=p.y+h+2||p.y>=next.y+h+2);
   placed.push_back(next);
  }
  assert(!placed.empty());auto original=next;bool a=shelf.place(w,h,next),b=shelf.place(w,h,next);if(!a)assert(!b);
  (void)original;
 }
 for(bool reverse:{false,true}){
  sg_sprite s{};s.model[0]=7;s.color[2]=.37f;float a=16.f/512,b=32.f/512,c=8.f/512,d=24.f/512;if(reverse){std::swap(a,b);std::swap(c,d);}
  const float v[]={0,1,a,d,1,0,b,c,0,0,a,c,1,1,b,d};std::copy(v,v+16,s.xyuv);
  sg::mask_crop crop;assert(sg::mask_batch_crop(s,512,512,crop));assert(crop.x==16&&crop.y==8&&crop.width==16&&crop.height==16);
  auto out=sg::mask_batch_sprite(s,512,512,crop,{23,41},9);assert(out.texture==9&&!std::memcmp(s.model,out.model,sizeof s.model)&&!std::memcmp(s.color,out.color,sizeof s.color));
  for(unsigned i=0;i<4;i++){assert(out.xyuv[4*i+2]*128-23+16==s.xyuv[4*i+2]*512);assert(out.xyuv[4*i+3]*128-41+8==s.xyuv[4*i+3]*512);}
  s.xyuv[2]=.17f;assert(!sg::mask_batch_crop(s,512,512,crop));
 }
}
