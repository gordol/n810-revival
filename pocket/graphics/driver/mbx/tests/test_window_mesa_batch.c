/* SPDX-License-Identifier: MIT. Actual ARM Mesa / fake service, no GPU pixels. */
#define main checkpoint_fixture_main
#include "test_window_mesa_checkpoint.c"
#undef main
#include "mbx_window_export.h"
#include <errno.h>
#include <dlfcn.h>
static GLuint texture(unsigned w,unsigned h,const void *data){
 GLuint t;glGenTextures(1,&t);glBindTexture(GL_TEXTURE_2D,t);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,w,h,0,GL_RGBA,GL_UNSIGNED_BYTE,data);return t;
}
int main(int argc,char **argv){
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/batch-gpu-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);setenv("MBX_TEST_FORBID_GPU_READ","1",1);
 snprintf(file,sizeof file,"%s/batch-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_CHECKPOINT"};
 for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);
 setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);
 unsigned char dummy[16*16*4];assert(OSMesaMakeCurrent(ctx,dummy,GL_UNSIGNED_BYTE,16,16));
 unsigned char *data=malloc(1024*1024*4);assert(data);
 for(unsigned i=0;i<1024*1024;i++){data[4*i]=i&1?255:0;data[4*i+1]=37;data[4*i+2]=73;data[4*i+3]=i%256;}
 GLuint source=texture(1024,1024,data),mask=texture(1024,1024,data),out=texture(128,128,NULL);glFinish();
 int (*batch)(unsigned,const struct mbx_window_channel_item*,unsigned,struct mbx_window_view*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_batch");
 int (*export_image)(unsigned,struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export");
 int (*release)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_export_release");
 int (*begin)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_transaction_begin"),(*end)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_transaction_end");assert(batch&&export_image&&release&&begin&&end);
 struct mbx_window_channel_item items[64];for(unsigned i=0;i<64;i++)items[i]=(struct mbx_window_channel_item){source,mask,(i*13)%1008,(i*17)%1008,16,16,(i%8)*16,(i/8)*16,i%3};
 GLint active,binding,after;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 off_t before=lseek(gpu,0,SEEK_CUR);struct mbx_window_view view;
 assert(!begin()&&!batch(out,items,64,&view)&&!end());assert(lseek(gpu,0,SEEK_CUR)-before==131152);
 assert(view.width==128&&view.height==128&&view.storage_width==128&&view.storage_height==128);
 glGetIntegerv(GL_ACTIVE_TEXTURE,&after);assert(active==after);glGetIntegerv(GL_TEXTURE_BINDING_2D,&after);assert(binding==after);
 struct mbx_window_image image;assert(!export_image(out,&image)&&image.token.slot==2);
 before=lseek(gpu,0,SEEK_CUR);assert(batch(out,items,64,&view)==-EBUSY&&lseek(gpu,0,SEEK_CUR)==before);assert(!release(out,&image));
 if(argc>1&&!strcmp(argv[1],"readback")){unsigned char pixels[65536];glBindTexture(GL_TEXTURE_2D,out);glGetTexImage(GL_TEXTURE_2D,0,GL_RGBA,GL_UNSIGNED_BYTE,pixels);assert(!"GPU batch cannot expose a CPU shadow");}
 for(unsigned mutation=0;mutation<9;mutation++){
  struct mbx_window_channel_item saved=items[63];struct mbx_window_view untouched={37,38,39,40};
  if(mutation==0)items[63].dx=0,items[63].dy=0;
  if(mutation==1)items[63].sx=~0U;
  if(mutation==2)items[63].width=0;
  if(mutation==3)items[63].mode=3;
  if(mutation==4)items[63].source=out;
  if(mutation==5)items[63].dy=~0U;
  if(mutation==6)items[63].source=0;
  if(mutation==7)items[63].sy=1024;
  if(mutation==8)items[63].height=129;
  before=lseek(gpu,0,SEEK_CUR);assert(batch(out,items,64,&untouched)==-EINVAL);
  assert(lseek(gpu,0,SEEK_CUR)==before&&untouched.width==37&&untouched.height==38&&untouched.storage_width==39&&untouched.storage_height==40);
  items[63]=saved;
 }
 struct mbx_window_image unchanged;assert(!export_image(out,&unchanged)&&!memcmp(&image.token,&unchanged.token,sizeof image.token));assert(!release(out,&unchanged));
 before=lseek(gpu,0,SEEK_CUR);assert(batch(out,items,0,&view)==-EINVAL&&batch(out,items,65,&view)==-EINVAL&&batch(out,NULL,1,&view)==-EINVAL&&batch(out,items,1,NULL)==-EINVAL&&lseek(gpu,0,SEEK_CUR)==before);
 glBindTexture(GL_TEXTURE_2D,mask);unsigned char nonbinary[4]={127,37,73,255};
 glTexSubImage2D(GL_TEXTURE_2D,0,items[63].sx,items[63].sy,1,1,GL_RGBA,GL_UNSIGNED_BYTE,nonbinary);glFinish();items[63].mode=2;
 before=lseek(gpu,0,SEEK_CUR);assert(batch(out,items,64,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==before);
 glTexSubImage2D(GL_TEXTURE_2D,0,items[63].sx,items[63].sy,1,1,GL_RGBA,GL_UNSIGNED_BYTE,data+4*(items[63].sy*1024+items[63].sx));items[63].mode=0;glFinish();
 glBindTexture(GL_TEXTURE_2D,source);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_LINEAR);glFinish();before=lseek(gpu,0,SEEK_CUR);assert(batch(out,items,1,&view)==-ENOTSUP&&lseek(gpu,0,SEEK_CUR)==before);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
 items[0].dx=127;items[0].dy=127;items[0].sx=1023;items[0].sy=1023;items[0].width=1;items[0].height=1;
 before=lseek(gpu,0,SEEK_CUR);assert(!batch(out,items,1,&view)&&lseek(gpu,0,SEEK_CUR)-before==131152&&view.width==128&&view.height==128);
 free(data);OSMesaDestroyContext(ctx);close(gpu);close(lock);
 puts("ARM Mesa atlas:64 items ->one131152-byte write; exact bounds/token/pinning, nested transaction and GL-state preservation; late invalid list leaves target/view untouched; no GPU readback (fake service only)");
}
