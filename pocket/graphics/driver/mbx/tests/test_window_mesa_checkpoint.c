/* SPDX-License-Identifier: MIT. Actual ARM Mesa, fake service metadata/writes.
 * Exercises command-history lifecycle only; no GPU rendering or FPS claim. */
#define _GNU_SOURCE
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <assert.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "mbx_vgp_wire.h"
#include "mbx_wire_resources.h"
int main(void){
 char file[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/checkpoint-fake-device-XXXXXX",tmp);int gpu=mkstemp(file);assert(gpu>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);
 snprintf(file,sizeof file,"%s/checkpoint-job-lock-XXXXXX",tmp);int lock=mkstemp(file);assert(lock>=0);unlink(file);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 const char *enabled[]={"N810_MBX_DEVICE","N810_MBX_GPU_VERTEX","N810_MBX_EXPERIMENTAL_2D","N810_MBX_WINDOW_IMAGES","N810_MBX_NATIVE_WINDOWS","N810_MBX_LINEAR_TEXTURE","N810_MBX_MULTI_TEXTURE","MBX_TEST_CHECKPOINT"};
 for(unsigned i=0;i<sizeof enabled/sizeof *enabled;i++)setenv(enabled[i],"1",1);
 setenv("N810_MBX_WINDOW_FIRST","0",1);setenv("N810_MBX_WINDOW_COUNT","6",1);
 setenv("N810_MBX_SURFACE_CHECKPOINT","0",1);setenv("N810_MBX_SEPARATE_ALPHA","0",1);
 unsetenv("N810_MBX_RESOURCE_REFERENCES");
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char pixels[16*16*4];assert(OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16));
 GLuint texture[2],fbo[2];glGenTextures(2,texture);glGenFramebuffers(2,fbo);
 for(unsigned i=0;i<2;i++){
  glBindTexture(GL_TEXTURE_2D,texture[i]);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,i?128:240,i?128:320,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  glBindFramebuffer(GL_FRAMEBUFFER,fbo[i]);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture[i],0);
  assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);glViewport(0,0,i?128:240,i?128:320);
  glClearColor(.2,.3,.4,.5);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 }
 for(unsigned round=0;round<64;round++)for(unsigned i=0;i<2;i++)for(unsigned repeat=0;repeat<2;repeat++){
  glBindFramebuffer(GL_FRAMEBUFFER,fbo[i]);glViewport(0,0,i?128:240,i?128:320);
  glColor4f(.8,.4,.2,.7);glRectf(-.25,-.25,.25,.25);glFinish();assert(glGetError()==GL_NO_ERROR);
  /* A second finish must submit no additional GPU job. */
  off_t at=lseek(gpu,0,SEEK_CUR);glFinish();assert(lseek(gpu,0,SEEK_CUR)==at);
 }
 glClearColor(.1,.2,.3,.4);glClear(GL_COLOR_BUFFER_BIT);glFinish();
 off_t size=lseek(gpu,0,SEEK_END);assert(size>0);lseek(gpu,0,SEEK_SET);
 unsigned total=0,replays=0,merges=0,maxdraws=0,legacy=0;
 while(lseek(gpu,0,SEEK_CUR)<size){
  unsigned raw[16384];assert(read(gpu,raw,48)==48);struct mbx_vgp_wire_frame *f=(void*)raw;
  assert(f->bytes>=64&&f->bytes<=sizeof raw);assert(read(gpu,raw+12,f->bytes-48)==f->bytes-48);
  struct mbx_wire_resources r;assert(!mbx_wire_resources_parse(raw,f->bytes,&r));
  for(unsigned j=0;j<r.count;j++){assert(r.item[j].version!=10);if(r.item[j].version==14)replays++;if(r.item[j].version==11)merges++;if(r.item[j].version==13)legacy++;}
  if(f->draws>maxdraws)maxdraws=f->draws;total++;
 }
 assert(total==3+256*3&&replays==256*2&&merges==256&&maxdraws<=2&&!legacy);
 /* Destroy while still bound: no accidental materialization/readback. */
 OSMesaDestroyContext(ctx);close(gpu);close(lock);
 printf("ARM actual Mesa checkpoint lifecycle: %u jobs; 256 incremental updates with same-target reuse and switches, explicit clear; max_draws=%u; 512 v14 scratch reads; 256 merges; repeated finish idle; legacy flag=0; fake service only, no GPU execution\n",total,maxdraws);
}
