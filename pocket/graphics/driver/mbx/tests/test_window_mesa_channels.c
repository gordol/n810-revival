/* SPDX-License-Identifier: MIT. Actual ARM Mesa, fake service; no GPU pixels. */
#define main checkpoint_fixture_main
#include "test_window_mesa_checkpoint.c"
#undef main
#include "mbx_window_export.h"
#include <errno.h>
#include <dlfcn.h>
static GLuint texture(unsigned w,unsigned h,const void *data){
 GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data);assert(glGetError()==GL_NO_ERROR);return t;
}
int main(int argc,char **argv){
 int native=argc>1&&!strcmp(argv[1],"native"),readback=argc>1&&!strcmp(argv[1],"readback");
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/channels-fake-device-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);setenv("MBX_TEST_FORBID_GPU_READ","1",1);
 snprintf(file,sizeof file,"%s/channels-job-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_CHECKPOINT"};
 for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char dummy[16*16*4];assert(OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 int full=argc>1&&!strcmp(argv[1],"full"),medium=argc>1&&!strcmp(argv[1],"medium");
 unsigned w=native?240:full?128:medium?64:7,h=native?320:full?128:medium?64:11,sw=native?240:128,sh=native?320:128;unsigned char *data=malloc(w*h*4);
 for(unsigned i=0;i<w*h;i++){data[4*i]=i&1?255:0;data[4*i+1]=37;data[4*i+2]=73;data[4*i+3]=i%256;}
 GLuint source=texture(w,h,data),mask=texture(w,h,data),out=texture(sw,sh,NULL);
 int (*combine)(unsigned,unsigned,unsigned,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels");
 int (*export_image)(unsigned,struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export");int (*release)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export_release");assert(combine&&export_image&&release);
 glFinish();GLint active,binding,after;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 off_t submitted=lseek(gpu,0,SEEK_CUR);
 struct mbx_window_view view={0};assert(!combine(source,mask,out,MBX_WINDOW_BINARY_RED_ALPHA,&view));assert(view.width==w&&view.height==h&&view.storage_width==sw&&view.storage_height==sh);
 if(getenv("N810_MBX_CHANNEL_UPLOAD_MERGE")){
  unsigned compact=2U*(436U+((w+17U)&~15U)*(h+2U)*4U)+80U,dense=80U+sw*sh*8U;
  assert(lseek(gpu,0,SEEK_CUR)-submitted==(dense<=compact?dense:compact));
 }
 glGetIntegerv(GL_ACTIVE_TEXTURE,&after);assert(after==active);glGetIntegerv(GL_TEXTURE_BINDING_2D,&after);assert(after==binding);
 struct mbx_window_image image;assert(!export_image(out,&image)&&image.token.slot==(native?0U:2U));off_t held=lseek(gpu,0,SEEK_CUR);assert(combine(source,mask,out,0,&view)==-EBUSY&&lseek(gpu,0,SEEK_CUR)==held);assert(!release(out,&image));
 glBindTexture(GL_TEXTURE_2D,source);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);held=lseek(gpu,0,SEEK_CUR);assert(combine(source,mask,out,0,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==held);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
 if(readback){unsigned char pixels[128*128*4];glBindTexture(GL_TEXTURE_2D,out);glGetTexImage(GL_TEXTURE_2D,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);assert(!"GPU output must not expose a stale CPU shadow");}
 GLuint out2=texture(sw,sh,NULL);glFinish();assert(!combine(native?out:source,mask,out2,MBX_WINDOW_ALPHA,&view));
 off_t before=lseek(gpu,0,SEEK_CUR);assert(combine(source,out,out2,MBX_WINDOW_RED_ALPHA,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==before);
 if(!native){
  GLuint out3=texture(sw,sh,NULL);glFinish();before=lseek(gpu,0,SEEK_CUR);assert(!combine(out,out2,out3,MBX_WINDOW_ALPHA,&view));assert(lseek(gpu,0,SEEK_CUR)-before==80); /* resident+resident: merge only */
  GLuint out4=texture(sw,sh,NULL);glFinish();assert(!combine(source,mask,out4,MBX_WINDOW_RED_ALPHA,&view));
  GLuint out5=texture(sw,sh,NULL);glFinish();before=lseek(gpu,0,SEEK_CUR);assert(combine(source,mask,out5,MBX_WINDOW_ALPHA,&view)==-ENOSPC&&lseek(gpu,0,SEEK_CUR)==before);
 }
 /* Rejection does not overwrite an already composed output or submit jobs. */
 glBindTexture(GL_TEXTURE_2D,mask);data[0]=127;glTexSubImage2D(GL_TEXTURE_2D,0,0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,data);glFinish();before=lseek(gpu,0,SEEK_CUR);
 assert(combine(source,mask,out,MBX_WINDOW_BINARY_RED_ALPHA,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==before);
 assert(combine(source,mask,source,0,&view)==-EINVAL);free(data);OSMesaDestroyContext(ctx);close(gpu);close(lock);
 printf("ARM actual Mesa channels:%ux%u logical ->%ux%u retained; CPU/resident input paths, no GPU read/output upload, GL state preserved, capacity/alias/binary rejection clean (fake service only)\n",w,h,sw,sh);
}
