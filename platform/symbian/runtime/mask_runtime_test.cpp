// SPDX-License-Identifier: MIT. Actual ARM Mesa with a fake GPU service.
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <GL/glext.h>
#include <cassert>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <unistd.h>
#include <vector>
#include "fixed_sprite.h"
#include "graphics_command_profile.h"
#include <set>
static std::set<unsigned> pending;static unsigned allocations;
int sg_sprite_batch_flush(){pending.clear();return 0;}
static void checked_delete(GLsizei n,const GLuint *names){for(GLsizei i=0;i<n;i++)assert(!pending.count(names[i]));glDeleteTextures(n,names);}
static void checked_storage(GLenum t,GLint l,GLint f,GLsizei w,GLsizei h,GLint b,GLenum format,GLenum type,const void *data){assert(!data);++allocations;glTexImage2D(t,l,f,w,h,b,format,type,data);}
#define glDeleteTextures checked_delete
#define glTexImage2D checked_storage
#define glGetTexImage(...) assert(!"Runtime texture readback")
#define glReadPixels(...) assert(!"Runtime pixel readback")
#include "gpu_mask_texture.h"
#include "mask_cache_runtime.h"
#undef glDeleteTextures
#undef glTexImage2D
#undef glGetTexImage
#undef glReadPixels
static unsigned last_texture,draws;static bool render_consumer;
static int consume(const sg_sprite *s,void*){
 ++draws;last_texture=s->texture;mbx_window_image image{};
 if(!render_consumer){assert(!n810_mbx_window_export(s->texture,&image));assert(image.token.slot>=2&&image.token.slot<6);assert(!n810_mbx_window_export_release(s->texture,&image));}
 else {glBindTexture(GL_TEXTURE_2D,s->texture);glEnable(GL_TEXTURE_2D);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_REPLACE);glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glVertexPointer(2,GL_FLOAT,4*sizeof(float),s->xyuv);glTexCoordPointer(2,GL_FLOAT,4*sizeof(float),s->xyuv+2);const unsigned indices[]={0,1,2,0,3,1};glDrawElements(GL_TRIANGLES,6,GL_UNSIGNED_INT,indices);}
 pending.insert(s->texture);return 0;
}
static GLuint texture(unsigned w,unsigned h,const void *data){
 GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data);assert(!glGetError());return t;
}
int main(int argc,char **argv){
 render_consumer=argc>1&&!std::strcmp(argv[1],"render");
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/runtime-gpu-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);
 snprintf(file,sizeof file,"%s/runtime-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 for(auto name:{"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_CHECKPOINT","MBX_TEST_FORBID_GPU_READ","N810_SYMBIAN_MASK_CACHE","N810_MBX_SEPARATE_ALPHA","N810_MBX_LINEAR_TEXTURE","N810_MBX_EXPERIMENTAL_SCISSOR","N810_MBX_EXPERIMENTAL_TEXTURE"})setenv(name,"1",1);
 setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 auto ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,nullptr);unsigned char dummy[16*16*4];assert(OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 GLuint target=0,fbo=0;
 if(render_consumer){
  target=texture(240,320,nullptr);glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,target,0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
  glViewport(0,0,240,320);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,1,0,1,-1,1);glMatrixMode(GL_MODELVIEW);glLoadIdentity();glClearColor(0,0,0,1);glClear(GL_COLOR_BUFFER_BIT);
  unsigned char white[]={255,255,255,255};GLuint t=texture(1,1,white);float quad[]={0,0,1,0,0,1,0,1,1,0,1,1};glEnable(GL_TEXTURE_2D);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_REPLACE);glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);glVertexPointer(2,GL_FLOAT,0,quad);glTexCoordPointer(2,GL_FLOAT,0,quad);glDrawArrays(GL_TRIANGLES,0,6);glFinish();glDeleteTextures(1,&t);
 }
 sg_sprite sprite{};float uv[]={0,1,0,1,1,0,1,0,0,0,0,0,1,1,1,1};std::copy(uv,uv+16,sprite.xyuv);
 std::vector<unsigned char> data(1024*1024*4,255);std::vector<GLuint> names;
 GLuint mask=texture(7,11,data.data());names.push_back(mask);
 sg_mask_source m{2,1,mask,7,11,1},src{};
 for(unsigned i=0;i<12;i++){
  auto t=texture(7,11,data.data());names.push_back(t);src={100+i,1,t,7,11,1};
  assert(!sg_mask_sprite_draw(&sprite,&src,&m,8,consume,nullptr));assert(mask_cache_state_.cache->size()<=3);
  unsigned previous=last_texture;off_t position=lseek(gpu,0,SEEK_CUR);
  assert(!sg_mask_sprite_draw(&sprite,&src,&m,8,consume,nullptr));assert(last_texture==previous&&lseek(gpu,0,SEEK_CUR)==position);
 }
 // Repeated small crops from a larger canonical atlas share the tile result.
 GLuint atlas=texture(257,131,data.data()),atlas_mask=texture(257,131,data.data());names.push_back(atlas);names.push_back(atlas_mask);
 src={450,1,atlas,257,131,1};m={451,1,atlas_mask,257,131,1};
 sg_sprite cropped=sprite;for(unsigned i=0;i<4;i++){cropped.xyuv[4*i+2]=.1f+.3f*sprite.xyuv[4*i+2];cropped.xyuv[4*i+3]=.1f+.6f*sprite.xyuv[4*i+3];}
 assert(!sg_mask_sprite_draw(&cropped,&src,&m,8,consume,nullptr));unsigned tile_texture=last_texture;off_t tile_position=lseek(gpu,0,SEEK_CUR);
 for(unsigned i=0;i<10;i++){assert(!sg_mask_sprite_draw(&cropped,&src,&m,8,consume,nullptr));assert(last_texture==tile_texture&&lseek(gpu,0,SEEK_CUR)==tile_position);}
 sg_sprite next_crop=cropped;for(unsigned i=0;i<4;i++)next_crop.xyuv[4*i+2]+=.5f;
 assert(!sg_mask_sprite_draw(&next_crop,&src,&m,8,consume,nullptr));assert(last_texture!=tile_texture&&lseek(gpu,0,SEEK_CUR)>tile_position);
 sg_mask_source_retire(src.lifetime);assert(!mask_cache_state_.cache->references(src.lifetime));
 GLuint full=texture(128,128,data.data()),reserved=texture(128,128,nullptr);names.push_back(full);names.push_back(reserved);
 glFinish();mbx_window_view held{};assert(!n810_mbx_window_channels(full,full,reserved,MBX_WINDOW_RED_ALPHA,&held));
 GLuint large=texture(240,320,data.data()),large_mask=texture(240,320,data.data());names.push_back(large);names.push_back(large_mask);
 src={500,1,large,240,320,1};m={501,1,large_mask,240,320,1};unsigned before=draws,allocated=allocations;
 assert(!sg_mask_sprite_draw(&sprite,&src,&m,8,consume,nullptr));assert(draws-before==6&&allocations-allocated==1);
 assert(mask_cache_state_.cache->size()<=2);
 GLuint maximum=texture(1024,1024,data.data());names.push_back(maximum);src={600,1,maximum,1024,1024,1};m=src;before=draws;allocated=allocations;
 assert(!sg_mask_sprite_draw(&sprite,&src,&m,8,consume,nullptr));assert(draws-before==64&&allocations-allocated==1);
 off_t unchanged=lseek(gpu,0,SEEK_CUR);assert(sg_mask_sprite_draw(&sprite,&src,&m,128,consume,nullptr)==-1&&lseek(gpu,0,SEEK_CUR)==unchanged);
 auto count=mask_cache_state_.cache->size();sg_mask_source_retire(999999);assert(mask_cache_state_.cache->size()==count);
 sg_mask_cache_close();assert(!mask_cache_state_.cache);glDeleteTextures(names.size(),names.data());if(render_consumer){glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);glDeleteTextures(1,&target);}OSMesaDestroyContext(ctx);close(gpu);close(lock);
 std::puts("Resident runtime: padded hits/misses, 12-key eviction, six-tile native-size and64-tile maximum-size stream; all outputs slots2..5; deferred-consumer deletion and read/upload tripwires active (fake service, not pixels)");
}
