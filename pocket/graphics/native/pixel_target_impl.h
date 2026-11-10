/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef POCKET_PIXEL_TARGET_IMPL_H
#define POCKET_PIXEL_TARGET_IMPL_H
#include "pixel_target.h"
/* One owner-thread target shared by native scenes and GPU cell output.
 * GL remains the drawing API. The presenter receives top-down RGB565 pixels.
 * Direct readback is opt-in until Nokia pixel and timing acceptance. */
#ifndef GL_PACK_INVERT_MESA
#define GL_PACK_INVERT_MESA 0x8758
#endif
struct pocket_pixel_target {
 OSMesaContext owner;
 GLint previous;
 uint16_t *legacy;
 int active,direct;
};
static struct pocket_pixel_target pocket_target;
static void pocket_target_close(void){
 struct pocket_pixel_target *t=&pocket_target;
 if(t->owner&&t->owner==OSMesaGetCurrentContext()){
  if(t->active)glBindFramebuffer(GL_FRAMEBUFFER,t->previous);
 }
 memset(t,0,sizeof(*t));
}
int pocket_target_begin(void){
 struct pocket_pixel_target *t=&pocket_target;
 OSMesaContext owner=OSMesaGetCurrentContext();
 GLint width,height,format;void *buffer;
 if(!owner||t->active||(t->owner&&t->owner!=owner))return -1;
 if(!OSMesaGetColorBuffer(owner,&width,&height,&format,&buffer)||width!=400||height!=400||format!=OSMESA_RGB_565)return -1;
 const char *mode=getenv("POCKET_GL_TARGET");
 if(mode&&strcmp(mode,"legacy")&&strcmp(mode,"direct"))return -1;
 int direct=mode&&!strcmp(mode,"direct");
 if(direct){
  const char *extensions=(const char *)glGetString(GL_EXTENSIONS);
  if(!extensions||!strstr(extensions,"GL_MESA_pack_invert"))return -1;
 }
 t->owner=owner;t->legacy=buffer;t->direct=direct;
 glGetIntegerv(GL_FRAMEBUFFER_BINDING,&t->previous);
 /* Keep the default target's viewport orientation and rasterization identical.
  * A new FBO reverses Mesa's Y viewport scale on this backend. */
 glBindFramebuffer(GL_FRAMEBUFFER,0);
 t->active=1;return 0;
}
void pocket_target_end(void){
 if(pocket_target.active&&pocket_target.owner==OSMesaGetCurrentContext()){glBindFramebuffer(GL_FRAMEBUFFER,pocket_target.previous);pocket_target.active=0;}
}
int pocket_target_read(uint16_t *out,size_t capacity,unsigned stride,unsigned width,unsigned height){
 struct pocket_pixel_target *t=&pocket_target;
 if(!t->active||t->owner!=OSMesaGetCurrentContext()||!out||!width||width>400||!height||height>400||stride<width||stride>4096||capacity<((size_t)(height-1)*stride+width)*2)return -1;
 if(t->direct){
  GLint row,alignment,invert,skip_rows,skip_pixels,swap;
  glGetIntegerv(GL_PACK_ROW_LENGTH,&row);glGetIntegerv(GL_PACK_ALIGNMENT,&alignment);
  glGetIntegerv(GL_PACK_INVERT_MESA,&invert);glGetIntegerv(GL_PACK_SKIP_ROWS,&skip_rows);
  glGetIntegerv(GL_PACK_SKIP_PIXELS,&skip_pixels);glGetIntegerv(GL_PACK_SWAP_BYTES,&swap);
  glPixelStorei(GL_PACK_ROW_LENGTH,stride);glPixelStorei(GL_PACK_ALIGNMENT,2);
  glPixelStorei(GL_PACK_INVERT_MESA,GL_TRUE);glPixelStorei(GL_PACK_SKIP_ROWS,0);
  glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SWAP_BYTES,GL_FALSE);
  /* Synchronous read completes this target: no redundant glFinish or row copy. */
  glReadPixels(0,400-height,width,height,GL_RGB,GL_UNSIGNED_SHORT_5_6_5,out);
  GLenum error=glGetError();
  glPixelStorei(GL_PACK_ROW_LENGTH,row);glPixelStorei(GL_PACK_ALIGNMENT,alignment);
  glPixelStorei(GL_PACK_INVERT_MESA,invert);glPixelStorei(GL_PACK_SKIP_ROWS,skip_rows);
  glPixelStorei(GL_PACK_SKIP_PIXELS,skip_pixels);glPixelStorei(GL_PACK_SWAP_BYTES,swap);
  return error==GL_NO_ERROR?0:-1;
 }
 glFinish();if(glGetError()!=GL_NO_ERROR)return -1;
 for(unsigned y=0;y<height;++y)memcpy(out+y*stride,t->legacy+y*400,width*2);
 return 0;
}
#endif
