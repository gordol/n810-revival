/* SPDX-License-Identifier: MIT. Actual ARM Mesa with a fake render service.
 * Bounded command admission only; no GPU pixel or performance claim. */
#define main checkpoint_fixture_main
#include "test_window_mesa_checkpoint.c"
#undef main
#include <dlfcn.h>
#include "mbx_owned_surface.h"
int main(int argc,char **argv){
 int native=argc>1&&!strcmp(argv[1],"native");
 unsigned width=argc>1&&!strcmp(argv[1],"wide")?800:400,height=width==800?480:256;if(native){width=240;height=320;}
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/desktop-fake-device-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);
 snprintf(file,sizeof file,"%s/desktop-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_EXPERIMENTAL_SCISSOR","N810_MBX_MULTI_TEXTURE","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","MBX_TEST_DESKTOP"};
 for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);
 setenv("N810_MBX_WINDOW_FIRST",native?"0":"6",1);setenv("N810_MBX_WINDOW_COUNT",native?"6":"8",1);
 if(native)setenv("MBX_TEST_CHECKPOINT","1",1);
 setenv("N810_MBX_SURFACE_CHECKPOINT","0",1);setenv("N810_MBX_DRAW_BATCH",argc>1&&!strcmp(argv[1],"baseline")?"0":"1",1);
 if(width==800){setenv("MBX_TEST_DESKTOP_WIDE","1",1);setenv("N810_MBX_DESKTOP_TARGET","1",1);}
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char pixels[16*16*4];assert(OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16));
 GLuint texture,fbo;glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
 glTexImage2D(GL_TEXTURE_2D,0,native?GL_RGBA8:GL_RGB565,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
 glViewport(0,0,width,height);glClearColor(.2,.3,.4,1);glClear(GL_COLOR_BUFFER_BIT);glEnable(GL_SCISSOR_TEST);
 const GLfloat quad[24]={-.5,-.5,0,1,.5,-.5,0,1,-.5,.5,0,1,.5,-.5,0,1,.5,.5,0,1,-.5,.5,0,1};
 glEnableClientState(GL_VERTEX_ARRAY);glVertexPointer(4,GL_FLOAT,0,quad);
 for(unsigned group=0;group<(native?80U:40U);group++){
  glScissor(group%2?8:0,group%2?8:0,native?224:384,240);glColor4f(.7,.3,.1,1);
  for(unsigned i=0;i<16;i++)glDrawArrays(GL_TRIANGLES,0,6);
 }
 if(native){
  glFinish();assert(glGetError()==GL_NO_ERROR);off_t size=lseek(gpu,0,SEEK_END);assert(size>0);lseek(gpu,0,SEEK_SET);
  unsigned jobs=0,tokens=0,merges=0;
  while(lseek(gpu,0,SEEK_CUR)<size){
   unsigned raw[262144];assert(read(gpu,raw,48)==48);struct mbx_vgp_wire_frame *f=(void*)raw;
   assert(f->bytes>=64&&f->bytes<=sizeof raw);assert(read(gpu,raw+12,f->bytes-48)==f->bytes-48);
   struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(raw,f->bytes,&r));
   for(unsigned j=0;j<r.count;j++){assert(r.item[j].version!=10);tokens+=r.item[j].version==14;merges+=r.item[j].version==11;}jobs++;
  }
  assert(jobs>=4&&jobs<=16&&tokens>=2&&merges>=1);
  printf("ARM actual Mesa native240x320 pressure:1280 quads/80 clip changes -> %u bounded jobs; version14 checkpoints, scratch merge, legacy flag0; fake service only\n",jobs);
  OSMesaDestroyContext(ctx);close(gpu);close(lock);return 0;
 }
 int (*begin)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_surface_begin");int (*end)(struct mbx_owned_surface*)=dlsym(RTLD_DEFAULT,"n810_mbx_surface_end");int (*release)(void)=dlsym(RTLD_DEFAULT,"n810_mbx_surface_release");assert(begin&&end&&release);
 assert(!begin());glFinish();assert(glGetError()==GL_NO_ERROR);struct mbx_owned_surface image;assert(!end(&image));assert(image.width==width&&image.height==height);assert(!release());
 off_t bytes=lseek(gpu,0,SEEK_END);assert(bytes>0&&bytes<1048576);lseek(gpu,0,SEEK_SET);unsigned *wire=malloc(bytes);assert(wire&&read(gpu,wire,bytes)==bytes);
 struct mbx_vgp_wire_frame *f=(void*)wire;assert(f->version==9&&f->bytes==bytes&&f->draws<=80);
 struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(wire,bytes,&r));unsigned masks=0,offset=r.draw_offset,triangles=0;
 for(unsigned i=0;i<f->draws;i++){struct mbx_vgp_wire_draw *d=(void*)((unsigned char*)wire+offset);masks+=!!(d->reserved&128);triangles+=d->triangles;assert(d->triangles<=256);offset+=d->bytes;}
 assert(offset==f->bytes&&masks>=40&&triangles==1280);
 printf("ARM actual Mesa desktop%ux%u: 640 quads / 40 changed clips -> %u draws, %u bytes; one final owned export; no checkpoint/global token/readback (fake service only)\n",width,height,f->draws,f->bytes);
 free(wire);OSMesaDestroyContext(ctx);close(gpu);close(lock);
}
