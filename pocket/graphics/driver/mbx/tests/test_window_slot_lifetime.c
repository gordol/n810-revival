/* SPDX-License-Identifier: MIT. Actual ARM Mesa / fake service, no GPU pixels. */
#define main checkpoint_fixture_main
#include "test_window_mesa_checkpoint.c"
#undef main
#include <dlfcn.h>
#include "mbx_window_export.h"
int main(int argc,char **argv){
 (void)argv;char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/slot-fake-device-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);
 snprintf(file,sizeof file,"%s/slot-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_CHECKPOINT"};
 for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);
 setenv("N810_MBX_WINDOW_FIRST","6",1);setenv("N810_MBX_WINDOW_COUNT","8",1);setenv("N810_MBX_SURFACE_CHECKPOINT","0",1);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char pixels[16*16*4];assert(OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16));
 int (*export_image)(unsigned,struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export");
 int (*release)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export_release");assert(export_image&&release);
 GLuint texture[9],fbo[9];glGenTextures(9,texture);glGenFramebuffers(9,fbo);unsigned mask=0;
 for(unsigned i=0;i<8;i++){
  glBindTexture(GL_TEXTURE_2D,texture[i]);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,128,128,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  glBindFramebuffer(GL_FRAMEBUFFER,fbo[i]);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture[i],0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
  glViewport(0,0,128,128);glClearColor(.2,.3,.4,.5);glClear(GL_COLOR_BUFFER_BIT);glFinish();
  struct mbx_window_image image;assert(!export_image(texture[i],&image));assert(image.token.slot>=6&&image.token.slot<14&&!(mask&(1U<<image.token.slot)));mask|=1U<<image.token.slot;assert(!release(texture[i],&image));
 }
 assert(mask==0x3fc0);
 if(argc==1){glDeleteFramebuffers(1,fbo);glDeleteTextures(1,texture);}
 glBindTexture(GL_TEXTURE_2D,texture[8]);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,128,128,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glBindFramebuffer(GL_FRAMEBUFFER,fbo[8]);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture[8],0);assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
 glClearColor(.1,.2,.3,.4);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 assert(argc==1);struct mbx_window_image image;assert(!export_image(texture[8],&image)&&image.token.slot==6);assert(!release(texture[8],&image));
 OSMesaDestroyContext(ctx);close(gpu);close(lock);
 puts("ARM Mesa slot lifetime: exactly eight live128x128 images in6..13; deleted image's slot6 reused; producer0..5 untouched (fake service only)");
}
