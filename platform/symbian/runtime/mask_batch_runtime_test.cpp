// SPDX-License-Identifier: MIT
// Actual runtime queue + Mesa. Fake service by default; optional GPU pixel parity.
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <GL/glext.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <unistd.h>
#include "fixed_sprite.cpp"
static GLuint make_texture(unsigned w,unsigned h,const void *data){GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);return t;}
static int consume(const sg_sprite *s,void*){return sg_sprite_draw(s);}
int main(int argc,char **argv){
 const bool pixels=argc>1&&!std::strcmp(argv[1],"pixels");const unsigned height=320;
 int gpu=-1;
 if(!pixels){char path[4096],fd[32];snprintf(path,sizeof path,"%s/page-gpu-XXXXXX",getenv("TMPDIR"));gpu=mkstemp(path);assert(gpu>=0);unlink(path);snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);snprintf(path,sizeof path,"%s/page-lock-XXXXXX",getenv("TMPDIR"));int lock=mkstemp(path);assert(lock>=0);unlink(path);snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);}
 for(auto name:{"N810_SYMBIAN_SPRITE_BATCH","N810_SYMBIAN_MASK_CACHE","N810_MBX_CHANNEL_UPLOAD_MERGE"})setenv(name,"1",1);
 auto ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,nullptr);unsigned char dummy[1024];assert(ctx&&OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 GLuint target=make_texture(240,height,nullptr),fbo;glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);glViewport(0,0,240,height);glDisable(GL_DEPTH_TEST);glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
 std::vector<GLuint> sources,masks,big_sources,big_masks;
 for(unsigned item=0;item<12;item++){
  unsigned char a[7*11*4],b[sizeof a];for(unsigned i=0;i<7*11;i++){a[4*i]=31+item*17;a[4*i+1]=19+i*3;a[4*i+2]=233-item*13;a[4*i+3]=255;b[4*i]=(item&1)?(i%3?255:0):(i%3?128:0);b[4*i+1]=b[4*i+2]=0;b[4*i+3]=255;}
  sources.push_back(make_texture(7,11,a));masks.push_back(make_texture(7,11,b));
  std::vector<unsigned char> aa(31*31*4),bb(aa.size());for(unsigned i=0;i<31*31;i++){for(unsigned c=0;c<4;c++){aa[4*i+c]=a[4*(i%(7*11))+c];bb[4*i+c]=b[4*(i%(7*11))+c];}}
  big_sources.push_back(make_texture(31,31,aa.data()));big_masks.push_back(make_texture(31,31,bb.data()));
 }
 GLuint capture=0,capture_fbo=0;if(pixels){capture=make_texture(240,304,nullptr);glGenFramebuffers(1,&capture_fbo);glBindFramebuffer(GL_FRAMEBUFFER,capture_fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,capture,0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);}
 std::vector<unsigned char> reference(240*height*4),actual(reference.size());
 for(unsigned scene=0;scene<3U;scene++)for(unsigned pass=pixels?0:1;pass<2;pass++){
  glBindFramebuffer(GL_FRAMEBUFFER,fbo);glViewport(0,0,240,height);glEnable(GL_BLEND);
  setenv("N810_SYMBIAN_MASK_BATCH",pass?"1":"0",1);glDisable(GL_SCISSOR_TEST);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);sg_sprite_batch_mode(1);
  unsigned long long pages=mask_page_.pages;
  for(unsigned i=0;i<(scene==2?80U:40U);i++){
   unsigned item=i%12;sg_sprite s{};s.projection[0]=2.f/240;s.projection[5]=-2.f/height;s.projection[10]=-1;s.projection[12]=-1;s.projection[13]=1;s.projection[15]=1;
   s.model[0]=14;s.model[5]=22;s.model[10]=s.model[15]=1;s.model[12]=float((i%10)*13);s.model[13]=float((i/10)*17);for(float &c:s.color)c=1;
   float u0=(i&2)?1:0,u1=1-u0;const float uv[]={0,1,u0,1,1,0,u1,0,0,0,u0,0,1,1,u1,1};std::memcpy(s.xyuv,uv,sizeof uv);
   glEnable(GL_SCISSOR_TEST);glScissor(scene&&((i/8)&1)?3:0,0,200,250);
   unsigned side=scene==2?31:7,rows=scene==2?31:11;
   sg_mask_source a{(scene==2?1000U:100U)+item,1,(scene==2?big_sources:sources)[item],side,rows,1},b{(scene==2?2000U:200U)+item,1,(scene==2?big_masks:masks)[item],side,rows,1};
   assert(!sg_mask_sprite_draw(&s,&a,&b,(item&1)?8:0,consume,nullptr));
   // The producer's command storage can disappear before the eventual flush.
   std::memset(&s,0x5a,sizeof s);std::memset(&a,0,sizeof a);std::memset(&b,0,sizeof b);
  }
  if(!scene&&pass){assert(mask_page_.count==12&&pending_count==40&&!mask_page_.composed);}
  assert(!sg_sprite_batch_flush());sg_sprite_batch_mode(0);glFinish();assert(glGetError()==GL_NO_ERROR);
  if(!scene&&pass)assert(mask_page_.pages-pages==1);if(scene==2&&pass)assert(mask_page_.pages-pages>1);
  if(pixels){
   // Native alpha history stays on GPU. Snapshot into the supported ordinary
   // capture target in bands; these explicit reads are untimed test work.
   glBindFramebuffer(GL_FRAMEBUFFER,capture_fbo);glViewport(0,0,240,304);glDisable(GL_BLEND);glDisable(GL_SCISSOR_TEST);
   for(unsigned row=0;row<height;row+=304){unsigned rows=std::min(304U,height-row);glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
    sg_sprite copy{};copy.texture=target;copy.projection[0]=2.f/240;copy.projection[5]=-2.f/304;copy.projection[10]=-1;copy.projection[12]=-1;copy.projection[13]=1;copy.projection[15]=1;copy.model[0]=240;copy.model[5]=rows;copy.model[10]=copy.model[15]=1;for(float &c:copy.color)c=1;
    float v0=float(row)/height,v1=float(row+rows)/height;const float uv[]={0,1,0,v1,1,0,1,v0,0,0,0,v0,1,1,1,v1};std::memcpy(copy.xyuv,uv,sizeof uv);assert(!sg_sprite_draw(&copy));glFinish();
    glReadPixels(0,0,240,rows,GL_RGBA,GL_UNSIGNED_BYTE,(pass?actual:reference).data()+row*240*4);assert(glGetError()==GL_NO_ERROR);
   }
   if(pass){assert(reference==actual);unsigned coloured=0;for(unsigned i=0;i<reference.size();i+=4)coloured+=(reference[i]||reference[i+1]||reference[i+2]);assert(coloured>500);}
  }
  sg_mask_cache_close();
 }
 if(!pixels){
  // An upload/destruction barrier must consume pending references first.
  setenv("N810_SYMBIAN_MASK_BATCH","1",1);sg_sprite_batch_mode(1);sg_sprite s{};s.projection[0]=2.f/240;s.projection[5]=-2.f/height;s.projection[10]=-1;s.projection[12]=-1;s.projection[13]=1;s.projection[15]=1;s.model[0]=14;s.model[5]=22;s.model[10]=s.model[15]=1;for(float &c:s.color)c=1;const float uv[]={0,1,0,1,1,0,1,0,0,0,0,0,1,1,1,1};std::memcpy(s.xyuv,uv,sizeof uv);
  sg_mask_source a{100,1,sources[0],7,11,1},b{200,1,masks[0],7,11,1};assert(!sg_mask_sprite_draw(&s,&a,&b,0,consume,nullptr));assert(mask_page_.count==1);sg_mask_source_retire(100);assert(!mask_page_.count&&!pending_count);sg_mask_cache_close();sg_sprite_batch_mode(0);
 }
 glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);glDeleteTextures(1,&target);if(pixels){glDeleteFramebuffers(1,&capture_fbo);glDeleteTextures(1,&capture);}glDeleteTextures(sources.size(),sources.data());glDeleteTextures(masks.size(),masks.data());glDeleteTextures(big_sources.size(),big_sources.data());glDeleteTextures(big_masks.size(),big_masks.data());OSMesaDestroyContext(ctx);
 std::printf("mask_page forty sprites/twelve inputs/one composition; clip/order/retirement checks; pixels=%u\n",pixels?240*height*3:0);
}
