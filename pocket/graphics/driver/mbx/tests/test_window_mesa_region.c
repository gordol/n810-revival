/* SPDX-License-Identifier: MIT. Actual ARM Mesa / fake service; no GPU pixels. */
#define main checkpoint_fixture_main
#include "test_window_mesa_checkpoint.c"
#undef main
#include "mbx_window_export.h"
#include <errno.h>
#include <dlfcn.h>
static GLuint texture(unsigned w,unsigned h,const void *data){
 GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data);assert(glGetError()==GL_NO_ERROR);return t;
}
int main(void){
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/region-gpu-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);setenv("MBX_TEST_FORBID_GPU_READ","1",1);
 snprintf(file,sizeof file,"%s/region-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_CHECKPOINT"};for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char dummy[16*16*4];assert(OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 unsigned char *data=malloc(1024*1024*4);assert(data);for(unsigned i=0;i<1024*1024;i++){data[4*i]=i&1?255:0;data[4*i+1]=i%251;data[4*i+2]=i%253;data[4*i+3]=i%256;}
 GLuint source=texture(1024,1024,data),mask=texture(1024,1024,data),out=texture(128,128,NULL);
 int (*region)(unsigned,unsigned,unsigned,const struct mbx_window_rect*,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_region");assert(region);glFinish();
 const struct mbx_window_rect cases[]={{0,0,128,128},{896,896,128,128},{1023,1023,1,1},{13,457,7,11}};
 for(unsigned i=0;i<4;i++){
  struct mbx_window_view view={0};off_t before=lseek(gpu,0,SEEK_CUR);assert(!region(source,mask,out,cases+i,MBX_WINDOW_BINARY_RED_ALPHA,&view));
  unsigned pitch=(cases[i].width+17U)&~15U,bytes=436+pitch*(cases[i].height+2U)*4;
  assert(lseek(gpu,0,SEEK_CUR)-before==(off_t)(bytes*2+80));assert(view.width==cases[i].width&&view.height==cases[i].height&&view.storage_width==128&&view.storage_height==128);
 }
 struct mbx_window_rect invalid[]={{0,0,0,1},{0,0,129,1},{1023,0,2,1},{0,1024,1,1},{~0U,0,1,1}};
 for(unsigned i=0;i<5;i++){off_t before=lseek(gpu,0,SEEK_CUR);struct mbx_window_view view={37,38,39,40};assert(region(source,mask,out,invalid+i,1,&view)==-EINVAL&&view.width==37&&lseek(gpu,0,SEEK_CUR)==before);}
 GLuint masksmall=texture(128,128,NULL),other=texture(128,128,NULL);glFinish();struct mbx_window_rect crop={1,1,7,11};struct mbx_window_view view;
 off_t before=lseek(gpu,0,SEEK_CUR);assert(region(out,masksmall,other,&crop,MBX_WINDOW_RED_ALPHA,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==before);
 assert(region(source,mask,out,NULL,1,&view)==-EINVAL);assert(region(source,mask,source,&crop,1,&view)==-EINVAL);free(data);OSMesaDestroyContext(ctx);close(gpu);close(lock);
 puts("ARM Mesa regions:1024x1024 uploads, four corner/interior crops including1x1; exact crop-only transfer sizes, overflow/zero/alias/resident rejection before submit; no GPU readback (fake service only)");
}
