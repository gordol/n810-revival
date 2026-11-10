/* SPDX-License-Identifier: MIT. Resident GPU channel composition only. */
#pragma once
#include <mbx_window_export.h>
#include <dlfcn.h>
#include <cerrno>
#include <stdexcept>
#include <string>
struct sg_mask_image {unsigned texture=0;mbx_window_view view{};};
static int sg_gpu_mask_region(unsigned source,unsigned mask,unsigned target,unsigned flags,
 unsigned x,unsigned y,unsigned w,unsigned h,mbx_window_view *view){
 using region_fn=int(*)(unsigned,unsigned,unsigned,const mbx_window_rect*,unsigned,mbx_window_view*);
 using whole_fn=int(*)(unsigned,unsigned,unsigned,unsigned,mbx_window_view*);
 if(flags&~12U)return -EINVAL;
 const unsigned mode=flags&8U?MBX_WINDOW_BINARY_RED_ALPHA:MBX_WINDOW_RED_ALPHA;
 auto region=reinterpret_cast<region_fn>(dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_region"));
 if(region){const mbx_window_rect rect{x,y,w,h};return region(source,mask,target,&rect,mode,view);}
 auto whole=reinterpret_cast<whole_fn>(dlsym(RTLD_DEFAULT,"n810_mbx_window_channels"));
 if(!whole||x||y)return -ENOTSUP;
 GLint old=0,sw=0,sh=0;glGetIntegerv(GL_TEXTURE_BINDING_2D,&old);glBindTexture(GL_TEXTURE_2D,source);
 glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&sw);glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&sh);glBindTexture(GL_TEXTURE_2D,old);
 if(w!=unsigned(sw)||h!=unsigned(sh))return -ENOTSUP;
 return whole(source,mask,target,mode,view);
}
static sg_mask_image sg_gpu_mask_allocate(){
 GLint active=0,binding=0;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 sg_mask_image result;glGenTextures(1,&result.texture);glBindTexture(GL_TEXTURE_2D,result.texture);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,128,128,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);
 const auto error=glGetError();glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);
 if(error){glDeleteTextures(1,&result.texture);throw std::runtime_error("Resident mask storage allocation failed");}
 return result;
}
