#include "runtime_debug.h"
/* SPDX-License-Identifier: MIT */
/* Source texture transfer/packing only on CPU. Alpha replacement executes in
 * the physically validated two-texture GPU channel selector. */
#include <vector>
#include <stdexcept>
#include <cstring>
#include <unistd.h>
#include <sys/ioctl.h>
#include "channel_wire.c"
static unsigned sg_gpu_mask_texture(unsigned source,unsigned mask,unsigned flags){
 if(flags&~12U)throw std::runtime_error("GPU mask inversion/brush/upscale not admitted");
 const char *fdstr=std::getenv("N810_MBX_RENDER_FD");
 if(!fdstr)throw std::runtime_error("GPU mask needs inherited device descriptor");
 int fd=std::stoi(fdstr);unsigned info[4]={};
 if(ioctl(fd,0x80104d43,info)||info[0]!=1||info[1]!=1||info[2]!=1||info[3])throw std::runtime_error("GPU mask device identity");
 glFinish();
 for(GLenum state:{GL_PACK_ROW_LENGTH,GL_PACK_SKIP_PIXELS,GL_PACK_SKIP_ROWS,GL_UNPACK_ROW_LENGTH,GL_UNPACK_SKIP_PIXELS,GL_UNPACK_SKIP_ROWS}){
  GLint value=0;glGetIntegerv(state,&value);if(value)throw std::runtime_error("GPU mask nondefault pixel-transfer layout");
 }
 GLint active=0,binding=0,pack=0,unpack=0,pbo=0;
 glGetIntegerv(GL_PIXEL_PACK_BUFFER_BINDING,&pbo);if(pbo)throw std::runtime_error("GPU mask pack PBO unsupported");
 glGetIntegerv(GL_PIXEL_UNPACK_BUFFER_BINDING,&pbo);if(pbo)throw std::runtime_error("GPU mask unpack PBO unsupported");
 glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);
 glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);glGetIntegerv(GL_PACK_ALIGNMENT,&pack);glGetIntegerv(GL_UNPACK_ALIGNMENT,&unpack);
 struct restore {GLint active,binding,pack,unpack;~restore(){glBindTexture(GL_TEXTURE_2D,binding);glPixelStorei(GL_PACK_ALIGNMENT,pack);glPixelStorei(GL_UNPACK_ALIGNMENT,unpack);glActiveTexture(active);}} guard{active,binding,pack,unpack};
 const GLenum params[]={GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER,GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T};
 GLint states[2][4],sizes[2][2];std::vector<unsigned char> inputs[2];
 for(unsigned i=0;i<2;++i){
  glBindTexture(GL_TEXTURE_2D,i?mask:source);
  for(unsigned j=0;j<4;++j)glGetTexParameteriv(GL_TEXTURE_2D,params[j],&states[i][j]);
  for(unsigned j=0;j<(i?1U:3U);++j){const GLenum keys[]={GL_TEXTURE_SWIZZLE_R,GL_TEXTURE_SWIZZLE_G,GL_TEXTURE_SWIZZLE_B},values[]={GL_RED,GL_GREEN,GL_BLUE};GLint v=0;glGetTexParameteriv(GL_TEXTURE_2D,keys[j],&v);if(v!=GLint(values[j]))throw std::runtime_error("GPU mask nonidentity source channel");}
  glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&sizes[i][0]);glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&sizes[i][1]);
  if(sizes[i][0]<1||sizes[i][1]<1||sizes[i][0]>1024||sizes[i][1]>1024)throw std::runtime_error("GPU mask source size outside bounded region");
  if(states[i][0]!=GL_NEAREST||states[i][1]!=GL_NEAREST) {
   std::fprintf(stderr,"GPU_MASK_FILTER image=%u min=%d mag=%d\n",i,states[i][0],states[i][1]);
   throw std::runtime_error("GPU mask currently requires nearest sampling");
  }
  inputs[i].resize(size_t(sizes[i][0])*sizes[i][1]*4);
  glPixelStorei(GL_PACK_ALIGNMENT,1);glGetTexImage(GL_TEXTURE_2D,0,GL_BGRA,GL_UNSIGNED_BYTE,inputs[i].data());
  if(glGetError()!=GL_NO_ERROR)throw std::runtime_error("GPU mask source transfer failed");
 }
 if(std::memcmp(sizes[0],sizes[1],sizeof sizes[0])||std::memcmp(states[0],states[1],sizeof states[0]))throw std::runtime_error("GPU mask source sampler/size mismatch");
 unsigned w=sizes[0][0],h=sizes[0][1],jobs=0;
 // Reject unsupported threshold data before submitting any tile. This is a
 // value check, not alpha generation; all channel composition stays on GPU.
 if(flags&8U)for(size_t i=2;i<inputs[1].size();i+=4)
  if(inputs[1][i]!=0&&inputs[1][i]!=255)throw std::runtime_error("GPU mask nonbinary threshold not admitted");
 // Each independent pointwise channel-selection job retains the existing
 // 320x192 bound. No filtering across tile edges and no CPU composition.
 unsigned maxw=((w<320?w:320)+15)&~15U,maxh=((h<192?h:192)+15)&~15U;
 std::vector<unsigned char> a(maxw*maxh*4),b(a.size()),packet(80+2*a.size()),output(a.size());
 for(unsigned top=0;top<h;top+=192)for(unsigned left=0;left<w;left+=320){
  unsigned tw=w-left<320?w-left:320,th=h-top<192?h-top:192;
  unsigned pw=(tw+15)&~15U,ph=(th+15)&~15U,n=pw*ph*4;
  std::memset(a.data(),0,n);std::memset(b.data(),0,n);
  for(unsigned y=0;y<th;++y){
   size_t src=(size_t(top+y)*w+left)*4;
   std::memcpy(a.data()+y*pw*4,inputs[0].data()+src,tw*4);
   std::memcpy(b.data()+y*pw*4,inputs[1].data()+src,tw*4);
   for(unsigned x=0;x<tw;++x)b[(y*pw+x)*4+3]=inputs[1][src+x*4+2];
  }
  unsigned bytes=0;if(mbx_pack_channel_region(pw,ph,8,a.data(),n,b.data(),n,packet.data(),packet.size(),&bytes))throw std::runtime_error("GPU mask packet bounds");
  if(write(fd,packet.data(),bytes)!=ssize_t(bytes))throw std::runtime_error("GPU mask submit failed");
  size_t got=0;while(got<n){ssize_t count=read(fd,output.data()+got,n-got);if(count<=0)throw std::runtime_error("GPU mask readback failed");got+=count;}
  for(unsigned y=0;y<th;++y)std::memcpy(inputs[0].data()+(size_t(top+y)*w+left)*4,output.data()+y*pw*4,tw*4);
  ++jobs;
 }
 GLuint texture=0;glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
 for(unsigned j=0;j<4;++j)glTexParameteri(GL_TEXTURE_2D,params[j],states[0][j]);
 glPixelStorei(GL_UNPACK_ALIGNMENT,1);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_BGRA,GL_UNSIGNED_BYTE,inputs[0].data());
 if(glGetError()!=GL_NO_ERROR){glDeleteTextures(1,&texture);throw std::runtime_error("GPU mask texture upload failed");}
 if(n810_runtime_debug()) std::fprintf(stderr,"GPU_MASK_COMPOSE size=%u,%u jobs=%u CPU_blended_pixels=0\n",w,h,jobs);
 return texture;
}
