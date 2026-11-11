/* SPDX-License-Identifier: MIT. Actual ARM Mesa objects, fake kernel metadata.
 * NO GPU execution and NO physical-pixel/performance claim. No draws submitted.
 */
#define _GNU_SOURCE
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <assert.h>
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>
#include "mbx_window_export.h"
int main(int argc,char **argv){
 int native=argc==1||strcmp(argv[1],"small");char file[4096],lockfile[4096],fd[32];const char *tmp=getenv("TMPDIR");assert(tmp);
 snprintf(file,sizeof file,"%s/window-fake-device-XXXXXX",tmp);snprintf(lockfile,sizeof lockfile,"%s/window-job-lock-XXXXXX",tmp);
 int gpu=mkstemp(file),lock=mkstemp(lockfile);assert(gpu>=0&&lock>=0);unlink(file);unlink(lockfile);
 snprintf(fd,sizeof fd,"%d",gpu);setenv("N810_MBX_RENDER_FD",fd,1);
 snprintf(fd,sizeof fd,"%d",lock);setenv("N810_MBX_JOB_LOCK_FD",fd,1);
 setenv("N810_MBX_DEVICE","1",1);setenv("N810_MBX_GPU_VERTEX","1",1);setenv("N810_MBX_EXPERIMENTAL_2D","1",1);
 setenv("N810_MBX_WINDOW_IMAGES","1",1);setenv("N810_MBX_NATIVE_WINDOWS","1",1);
 setenv("N810_MBX_WINDOW_FIRST",native?"2":"0",1);setenv("N810_MBX_WINDOW_COUNT",native?"12":"2",1);
 int (*get_layout)(struct mbx_window_layout*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_get_layout");
 int (*import_image)(unsigned,const struct mbx_window_image*)=dlsym(RTLD_DEFAULT,"n810_mbx_window_import");
 int (*forget)(unsigned)=dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");assert(get_layout&&import_image&&forget);
 struct mbx_window_layout caps;assert(!get_layout(&caps)&&caps.version==2&&caps.arena_bytes==2084864);
 OSMesaContext ctx=OSMesaCreateContextExt(OSMESA_RGBA,0,0,0,NULL);assert(ctx);unsigned char pixels[16*16*4];
 assert(OSMesaMakeCurrent(ctx,pixels,GL_UNSIGNED_BYTE,16,16));
 GLuint texture,fbo;unsigned width=native?240:128,height=native?320:128;
 glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
 glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAX_LEVEL,0);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
 glGenFramebuffers(1,&fbo);glBindFramebuffer(GL_FRAMEBUFFER,fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,texture,0);
 assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);
 struct mbx_window_image image={.version=2,.width=width,.height=height,.format=1,.token={7,11,native?0U:2U},.stride_bytes=width*4};
 int result=import_image(texture,&image);if(result)fprintf(stderr,"real Mesa import returned %d (native=%d)\n",result,native);assert(!result);
 assert(!forget(texture));image.stride_bytes+=4;assert(import_image(texture,&image)==-EINVAL);
 glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&fbo);glDeleteTextures(1,&texture);OSMesaDestroyContext(ctx);
 struct stat st;assert(!fstat(gpu,&st)&&st.st_size==0);close(gpu);close(lock);
 printf("ARM actual Mesa %ux%u import/forget: dimensions/stride/GL storage checked; fake metadata only; GPU writes=0\n",width,height);
}
