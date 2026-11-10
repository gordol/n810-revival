/* SPDX-License-Identifier: MIT */
#pragma once
#include "fixed_sprite.h"
#include "clip_union.h"
#include <cmath>
namespace sg {
/* Only the exact integer, axis-aligned, unit-viewport UI path is admitted.
 * Unknown transforms keep every draw. Two pixels of conservative padding keep
 * decisions away from floating-point viewport/raster edge rounding. This is
 * object rejection only; vertices, texture coordinates and scissors are intact. */
inline bool unit_sprite_bounds(const sg_sprite &s,const int vp[4],bool binding,box &out){
 if(vp[0]||vp[1]||vp[2]<=0||vp[3]<=0||vp[2]>512||vp[3]>512)return false;
 float expected[16]={};expected[0]=2.0f/vp[2];expected[5]=(binding?-2.0f:2.0f)/vp[3];
 expected[10]=-1;expected[12]=-1;expected[13]=binding?1:-1;expected[15]=1;
 for(unsigned i=0;i<16;++i)if(s.projection[i]!=expected[i])return false;
 for(unsigned i=0;i<16;++i){
  if(i==0||i==5||i==12||i==13)continue;
  if(s.model[i]!=(i==10||i==15?1.0f:0.0f))return false;
 }
 const float unit[8]={0,1,1,0,0,0,1,1};
 for(unsigned i=0;i<4;++i)for(unsigned k=0;k<2;++k)if(s.xyuv[4*i+k]!=unit[2*i+k])return false;
 for(unsigned i:{0U,5U,12U,13U})if(!std::isfinite(s.model[i])||std::floor(s.model[i])!=s.model[i]||std::fabs(s.model[i])>1024)return false;
 if(s.model[0]<=0||s.model[5]<=0)return false;
 int x=(int)s.model[12],y=(int)s.model[13],w=(int)s.model[0],h=(int)s.model[5];
 if(!binding)y=vp[3]-y-h;
 out={x-2,y-2,x+w+2,y+h+2};return true;
}
}
