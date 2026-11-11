// SPDX-License-Identifier: MIT
// Actual Mesa dispatch; optional untimed hardware pixel comparison.
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <GL/glext.h>
#include <dlfcn.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <unistd.h>
#include "fixed_sprite.h"
static unsigned begins,arrays;
extern "C" void glBegin(GLenum mode){++begins;using Fn=void(*)(GLenum);static auto real=(Fn)dlsym(RTLD_NEXT,"glBegin");assert(real);real(mode);}
extern "C" void glDrawArrays(GLenum mode,GLint first,GLsizei count){++arrays;using Fn=void(*)(GLenum,GLint,GLsizei);static auto real=(Fn)dlsym(RTLD_NEXT,"glDrawArrays");assert(real);real(mode,first,count);}
static GLuint texture(unsigned w,unsigned h,const void *pixels){GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);return t;}
int main(int argc,char **argv){
 const bool pixels=argc>1&&!std::strcmp(argv[1],"pixels");const unsigned height=pixels?304:320;
 if(!pixels){char path[4096],fd[32];snprintf(path,sizeof path,"%s/batch-gpu-XXXXXX",getenv("TMPDIR"));int gpu=mkstemp(path);assert(gpu>=0);unlink(path);snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);snprintf(path,sizeof path,"%s/batch-lock-XXXXXX",getenv("TMPDIR"));int lock=mkstemp(path);assert(lock>=0);unlink(path);snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);}
 auto ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,nullptr);unsigned char dummy[1024];assert(ctx&&OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 unsigned char data[8*8*4];for(unsigned i=0;i<64;i++){data[4*i]=i*3;data[4*i+1]=255-i*3;data[4*i+2]=i*2;data[4*i+3]=255;}
 GLuint source=texture(8,8,data),target=texture(240,height,nullptr),fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);glViewport(0,0,240,height);glDisable(GL_BLEND);glDisable(GL_DEPTH_TEST);
 std::vector<unsigned char> reference(240*height*4),actual(reference.size());unsigned control_calls=0,batched_calls=0;
 for(unsigned pass=0;pass<2;pass++){
  glDisable(GL_SCISSOR_TEST);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
  begins=arrays=0;setenv("N810_SYMBIAN_SPRITE_BATCH",pass?"1":"0",1);sg_sprite_batch_mode(1);
  for(unsigned i=0;i<64;i++){
   sg_sprite s{};s.texture=source;s.projection[0]=2.f/240;s.projection[5]=-2.f/height;s.projection[10]=-1;s.projection[12]=-1;s.projection[13]=1;s.projection[15]=1;
   s.model[0]=s.model[5]=16;s.model[10]=s.model[15]=1;s.model[12]=float((i%12)*9);s.model[13]=float((i/12)*9);for(float &c:s.color)c=1;
   const float uv[]={0,1,0,1,1,0,1,0,0,0,0,0,1,1,1,1};std::memcpy(s.xyuv,uv,sizeof uv);
   glEnable(GL_SCISSOR_TEST);glScissor((i/8)%2?3:0,0,200,250);
   assert(!sg_sprite_draw(&s));
  }
  assert(!sg_sprite_batch_flush());sg_sprite_batch_mode(0);glFinish();assert(glGetError()==GL_NO_ERROR);
  unsigned count=begins+arrays;if(!pass){control_calls=count;assert(begins==64&&!arrays);}else{batched_calls=count;assert(arrays==8&&!begins);}
  if(pixels){glReadPixels(0,0,240,height,GL_RGBA,GL_UNSIGNED_BYTE,(pass?actual:reference).data());assert(glGetError()==GL_NO_ERROR);}
 }
 if(pixels){assert(reference==actual);bool nonzero=false;for(unsigned i=0;i<reference.size();i+=4)nonzero|=reference[i]||reference[i+1]||reference[i+2];assert(nonzero);}
 std::printf("sprite_batch control_draws=%u batched_draws=%u clip_changes=8 pixels_verified=%u\n",control_calls,batched_calls,pixels?240*height:0);
 glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);GLuint names[]={source,target};glDeleteTextures(2,names);OSMesaDestroyContext(ctx);
}
