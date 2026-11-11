// SPDX-License-Identifier: MIT
#pragma once
#include "fixed_sprite.h"
#include <algorithm>
#include <cmath>
namespace sg {
struct mask_crop {unsigned x=0,y=0,width=0,height=0;};
struct mask_placement {unsigned x=0,y=0;};
// Conservative admission: exact texel-boundary crops only. Other draws retain
// the resident region path with its original geometry and sampling.
inline bool mask_batch_crop(const sg_sprite &s,unsigned width,unsigned height,mask_crop &out){
 if(!width||!height||width>1024||height>1024)return false;
 const float xy[]={0,1,1,0,0,0,1,1};double low[2]={1,1},high[2]={0,0};
 for(unsigned i=0;i<4;i++){
  if(s.xyuv[i*4]!=xy[i*2]||s.xyuv[i*4+1]!=xy[i*2+1])return false;
  for(unsigned a=0;a<2;a++){double v=s.xyuv[i*4+2+a];if(!std::isfinite(v)||v<0||v>1)return false;low[a]=std::min(low[a],v);high[a]=std::max(high[a],v);}
 }
 if(s.xyuv[2]!=s.xyuv[10]||s.xyuv[6]!=s.xyuv[14]||s.xyuv[3]!=s.xyuv[15]||s.xyuv[7]!=s.xyuv[11])return false;
 const unsigned size[]={width,height};unsigned first[2],last[2];
 for(unsigned a=0;a<2;a++){
  double l=low[a]*size[a],h=high[a]*size[a];if(l==h||std::floor(l)!=l||std::floor(h)!=h)return false;
  first[a]=unsigned(l);last[a]=unsigned(h);if(last[a]-first[a]>126)return false;
 }
 out={first[0],first[1],last[0]-first[0],last[1]-first[1]};
 // A page must be able to hold more than one such image. Preserve the larger
 // image cache instead of replacing a reusable single image with a page.
 return out.width+2<=64||out.height+2<=64;
}
class mask_shelf {
 unsigned x_=0,y_=0,row_=0;
public:
 void reset(){x_=y_=row_=0;}
 bool place(unsigned width,unsigned height,mask_placement &out){
  if(!width||!height||width>126||height>126)return false;
  unsigned x=x_,y=y_,row=row_,w=width+2,h=height+2;
  if(x+w>128){x=0;y+=row;row=0;}
  if(y+h>128)return false;
  out={x+1,y+1};x_=x+w;y_=y;row_=std::max(row,h);return true;
 }
};
inline sg_sprite mask_batch_sprite(const sg_sprite &source,unsigned width,unsigned height,const mask_crop &crop,const mask_placement &place,unsigned texture){
 sg_sprite out=source;out.texture=texture;
 for(unsigned i=0;i<4;i++){
  out.xyuv[4*i+2]=float((double(source.xyuv[4*i+2])*width-crop.x+place.x)/128);
  out.xyuv[4*i+3]=float((double(source.xyuv[4*i+3])*height-crop.y+place.y)/128);
 }
 return out;
}
}
