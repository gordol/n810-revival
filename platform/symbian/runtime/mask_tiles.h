/* SPDX-License-Identifier: MIT. Geometry/UV transport; no pixel processing. */
#pragma once
#include "fixed_sprite.h"
#include <algorithm>
#include <cmath>
#include <stdexcept>
namespace sg {
struct mask_tile {unsigned x,y,width,height;sg_sprite sprite;};
template<class Emit> void mask_tiles(const sg_sprite &source,unsigned width,unsigned height,Emit emit){
 if(!width||!height||width>1024||height>1024)throw std::runtime_error("Mask dimensions outside supported region");
 const auto *v=source.xyuv;const float u0=v[10],u1=v[6],v0=v[11],v1=v[3];
 const float expected_xy[]={0,1,1,0,0,0,1,1};
 for(unsigned i=0;i<4;i++){
  if(v[4*i]!=expected_xy[2*i]||v[4*i+1]!=expected_xy[2*i+1]||
     !std::isfinite(v[4*i+2])||!std::isfinite(v[4*i+3])||v[4*i+2]<0||v[4*i+2]>1||v[4*i+3]<0||v[4*i+3]>1)
   throw std::runtime_error("Mask sprite requires bounded affine UVs");
 }
 if(v[2]!=u0||v[14]!=u1||v[7]!=v0||v[15]!=v1)throw std::runtime_error("Mask sprite UV layout mismatch");
 if(width<=128&&height<=128){
  mask_tile tile{0,0,width,height,source};
  for(unsigned i=0;i<4;i++){tile.sprite.xyuv[4*i+2]*=float(width)/128;tile.sprite.xyuv[4*i+3]*=float(height)/128;}
  emit(tile);return;
 }
 if(u0==u1||v0==v1)throw std::runtime_error("Degenerate tiled mask UVs unsupported");
 const double a=u0*double(width),b=u1*double(width),c=v0*double(height),d=v1*double(height);
 for(unsigned y=0;y<height;y+=128)for(unsigned x=0;x<width;x+=128){
  unsigned w=std::min(128U,width-x),h=std::min(128U,height-y);
  double left=std::max(std::min(a,b),double(x)),right=std::min(std::max(a,b),double(x+w));
  double top=std::max(std::min(c,d),double(y)),bottom=std::min(std::max(c,d),double(y+h));
  if(left>=right||top>=bottom)continue;
  float x0=(float)((a<b?left-a:right-a)/(b-a)),x1=(float)((a<b?right-a:left-a)/(b-a));
  float y0=(float)((c<d?top-c:bottom-c)/(d-c)),y1=(float)((c<d?bottom-c:top-c)/(d-c));
  float tu0=float((a+(b-a)*x0-x)/128),tu1=float((a+(b-a)*x1-x)/128);
  float tv0=float((c+(d-c)*y0-y)/128),tv1=float((c+(d-c)*y1-y)/128);
  mask_tile tile{x,y,w,h,source};
  const float xyuv[]={x0,y1,tu0,tv1,x1,y0,tu1,tv0,x0,y0,tu0,tv0,x1,y1,tu1,tv1};
  std::copy(xyuv,xyuv+16,tile.sprite.xyuv);emit(tile);
 }
}
}
