#include "runtime_debug.h"
#include "graphics_command_profile.h"
/* SPDX-License-Identifier: MIT */
#define GL_GLEXT_PROTOTYPES
#include <GL/gl.h>
#include "fixed_sprite.h"
#include "affine_filter.h"
#include "sprite_region_bounds.h"
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <algorithm>
static int sg_sprite_draw_impl(const struct sg_sprite *s,const int *clips,unsigned count,const sg_sprite *many=nullptr,unsigned many_count=0){
 if(!s||count>512||(!clips&&count))return -1;
 if(clips)for(unsigned i=0;i<count;++i)if(clips[4*i+2]<=0||clips[4*i+3]<=0)return -1;
 n810_command_profile::scope setup_profile(80);
 GLint program,vao,active,matrix;glGetIntegerv(GL_CURRENT_PROGRAM,&program);glGetIntegerv(GL_VERTEX_ARRAY_BINDING,&vao);glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glGetIntegerv(GL_MATRIX_MODE,&matrix);
 glPushAttrib(GL_ENABLE_BIT|GL_TEXTURE_BIT|GL_CURRENT_BIT|GL_LIGHTING_BIT|GL_TRANSFORM_BIT|GL_SCISSOR_BIT);
 if(!many&&!clips&&std::getenv("N810_SYMBIAN_REDUNDANT_SCISSOR")&&glIsEnabled(GL_SCISSOR_TEST)){
  GLint vp[4],clip[4],fb=0;glGetIntegerv(GL_VIEWPORT,vp);glGetIntegerv(GL_SCISSOR_BOX,clip);glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&fb);
  GLint polygon[2];glGetIntegerv(GL_POLYGON_MODE,polygon);
  sg::box bounds{};
  if(polygon[0]==GL_FILL&&polygon[1]==GL_FILL&&sg::unit_sprite_bounds(*s,vp,fb!=0,bounds)&&clip[2]>=0&&clip[3]>=0&&
     bounds.x0>=clip[0]&&bounds.y0>=clip[1]&&
     (long long)bounds.x1<=(long long)clip[0]+clip[2]&&(long long)bounds.y1<=(long long)clip[1]+clip[3]){
   // Geometry and UVs are untouched. The proven bounds include two pixels
   // of rounding margin. GL_ENABLE_BIT restores the caller's scissor state.
   glDisable(GL_SCISSOR_TEST);
   static unsigned saved=0;++saved;
   if(saved==1||saved%128==0)if(n810_runtime_debug()) std::fprintf(stderr,"GPU_REDUNDANT_SCISSOR omitted=%u CPU_raster_pixels=0\n",saved);
  }
 }
 if(many&&!clips)glDisable(GL_SCISSOR_TEST);
 glUseProgram(0);glBindVertexArray(0);glActiveTexture(GL_TEXTURE1);glDisable(GL_TEXTURE_2D);glActiveTexture(GL_TEXTURE0);
 glDisable(GL_LIGHTING);glDisable(GL_FOG);glDisable(GL_ALPHA_TEST);glDisable(GL_TEXTURE_GEN_S);glDisable(GL_TEXTURE_GEN_T);glShadeModel(GL_SMOOTH);
 if(s->texture){glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,s->texture);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,(s->color[0]==1&&s->color[1]==1&&s->color[2]==1&&s->color[3]==1)?GL_REPLACE:GL_MODULATE);}else {
  glDisable(GL_TEXTURE_2D);
  /* Keep color as a VGP output rather than a constant-only fragment program:
   * the accepted MBX path consumes one interpolated color varying. Ambient
   * white with no lights is exactly the original uniform brush color. */
  glEnable(GL_LIGHTING);glDisable(GL_COLOR_MATERIAL);
  for(unsigned i=0;i<8;++i)glDisable(GL_LIGHT0+i);
  const GLfloat white[]={1,1,1,1},black[]={0,0,0,1};
  glLightModelfv(GL_LIGHT_MODEL_AMBIENT,white);glLightModeli(GL_LIGHT_MODEL_TWO_SIDE,GL_FALSE);
  glMaterialfv(GL_FRONT_AND_BACK,GL_AMBIENT_AND_DIFFUSE,s->color);
  glMaterialfv(GL_FRONT_AND_BACK,GL_EMISSION,black);glMaterialfv(GL_FRONT_AND_BACK,GL_SPECULAR,black);
 }
 glMatrixMode(GL_TEXTURE);glPushMatrix();glLoadIdentity();glMatrixMode(GL_PROJECTION);glPushMatrix();float projection[16];for(unsigned i=0;i<16;++i)projection[i]=(i%4==1)?-s->projection[i]:s->projection[i];glLoadMatrixf(projection);glMatrixMode(GL_MODELVIEW);glPushMatrix();glLoadMatrixf(s->model);
 GLint min_filter=0,mag_filter=0,width=0,height=0,viewport[4]={0};
 bool adjust_filter=false;
 if(s->texture&&std::getenv("N810_SYMBIAN_AFFINE_FILTER")){
  glGetTexParameteriv(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,&min_filter);
  glGetTexParameteriv(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,&mag_filter);
  adjust_filter=min_filter==GL_LINEAR&&mag_filter==GL_NEAREST;
  if(adjust_filter){glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&width);glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&height);glGetIntegerv(GL_VIEWPORT,viewport);}
 }
 glColor4fv(s->color);
 /* Same original sprite diagonal and index order; no tessellation change. */
 static const unsigned indices[]={0,1,2,0,3,1};
 setup_profile.finish();
 n810_command_profile::scope emit_profile(81);
 // One actual GL primitive batch for integer axis-aligned UI quads. The
 // input rectangles already contain these pixel coordinates; do not force
 // Mesa to validate an identical pipeline once per glyph merely to translate
 // and scale a unit quad. Projection, rasterization and sampling stay on GPU.
 bool joined=many && many_count>1 && count<=1 && s->texture;
 bool joined_magnified=false;
 if(joined){
  if(width<=0)glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_WIDTH,&width);
  if(height<=0)glGetTexLevelParameteriv(GL_TEXTURE_2D,0,GL_TEXTURE_HEIGHT,&height);
  if(width<=0||height<=0)joined=false;
  GLint vp[4];glGetIntegerv(GL_VIEWPORT,vp);
  for(unsigned item=0;item<many_count;++item){
   const auto &q=many[item];sg::box bounds;
   for(unsigned v=0;v<4;++v)for(unsigned a=2;a<4;++a)if(!(q.xyuv[4*v+a]>=0&&q.xyuv[4*v+a]<=1))joined=false;
   if(!joined)break;
   if(!sg::unit_sprite_bounds(q,vp,q.projection[5]<0,bounds)){joined=false;break;}
   bool magnified=adjust_filter&&width>0&&height>0&&sg_affine_magnified(projection,q.model,q.xyuv,viewport,width,height);
   if(item && magnified!=joined_magnified){joined=false;break;}
   joined_magnified=magnified;
  }
 }
 if(joined){
  glMatrixMode(GL_MODELVIEW);glLoadIdentity();
  if(joined_magnified)glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
  if(clips){glEnable(GL_SCISSOR_TEST);glScissor(clips[0],clips[1],clips[2],clips[3]);}
  for(unsigned first=0;first<many_count;){
   unsigned end=first;double low[2]={1,1},high[2]={0,0};
   unsigned long long individual_area=0;
   if(width<=320&&height<=320)end=many_count;
   for(;end<many_count;++end){
    double next_low[2]={low[0],low[1]},next_high[2]={high[0],high[1]};
    double own_low[2]={1,1},own_high[2]={0,0};
    for(unsigned v=0;v<4;++v)for(unsigned a=0;a<2;++a){double q=many[end].xyuv[4*v+2+a];
     own_low[a]=std::min(own_low[a],q);own_high[a]=std::max(own_high[a],q);
     next_low[a]=std::min(next_low[a],q);next_high[a]=std::max(next_high[a],q);
    }
    double cw=std::ceil(next_high[0]*width)-std::floor(next_low[0]*width)+2;
    double ch=std::ceil(next_high[1]*height)-std::floor(next_low[1]*height)+2;
    double ow=std::ceil(own_high[0]*width)-std::floor(own_low[0]*width)+2;
    double oh=std::ceil(own_high[1]*height)-std::floor(own_low[1]*height)+2;
    auto next_area=individual_area+static_cast<unsigned long long>(ow*oh);
    if(end>first&&(width>320||height>320)&&(cw>320||ch>320||cw*ch>4.0*next_area))break;
    individual_area=next_area;for(unsigned a=0;a<2;++a){low[a]=next_low[a];high[a]=next_high[a];}
   }
   // DrawArrays establishes a real driver draw boundary. Immediate-mode
   // glEnd/glBegin pairs may be merged by Mesa, re-expanding the atlas crop.
   float vertices[64*6*4];unsigned cursor=0;
   for(unsigned item=first;item<end;++item){const auto &q=many[item];
    for(unsigned i=0;i<6;++i){const float *v=q.xyuv+4*indices[i];
     vertices[cursor++]=v[0]*q.model[0]+q.model[12];
     vertices[cursor++]=v[1]*q.model[5]+q.model[13];
     vertices[cursor++]=v[2];vertices[cursor++]=v[3];
    }
   }
   GLint old_array=0;glGetIntegerv(GL_ARRAY_BUFFER_BINDING,&old_array);
   glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT);glClientActiveTexture(GL_TEXTURE0);
   glBindBuffer(GL_ARRAY_BUFFER,0);
   glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);
   glDisableClientState(GL_NORMAL_ARRAY);glDisableClientState(GL_COLOR_ARRAY);
   glDisableClientState(GL_SECONDARY_COLOR_ARRAY);glDisableClientState(GL_FOG_COORD_ARRAY);
   glDisableClientState(GL_INDEX_ARRAY);glDisableClientState(GL_EDGE_FLAG_ARRAY);
   glVertexPointer(2,GL_FLOAT,4*sizeof(float),vertices);
   glTexCoordPointer(2,GL_FLOAT,4*sizeof(float),vertices+2);
   glDrawArrays(GL_TRIANGLES,0,(end-first)*6);
   glPopClientAttrib();glBindBuffer(GL_ARRAY_BUFFER,old_array);
   first=end;
  }
  if(joined_magnified)glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,min_filter);
 }
 for(unsigned item=0;!joined&&item<(many?many_count:1);++item){
  if(many){s=many+item;glMatrixMode(GL_MODELVIEW);glLoadMatrixf(s->model);}
 GLint restore_min_filter=0;
 if(adjust_filter){
   int magnified=width>0&&height>0&&sg_affine_magnified(projection,s->model,s->xyuv,viewport,width,height);
   static unsigned reports=0;
   if(reports++<16)if(n810_runtime_debug()) std::fprintf(stderr,"GPU_SPRITE_SAMPLER texture=%u size=%d,%d magnification_proven=%d min=%d mag=%d\n",s->texture,width,height,magnified,min_filter,mag_filter);
   if(magnified){restore_min_filter=min_filter;glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);}
 }
 for(unsigned pass=0;pass<(clips?count:1);++pass){
  if(clips){glEnable(GL_SCISSOR_TEST);glScissor(clips[4*pass],clips[4*pass+1],clips[4*pass+2],clips[4*pass+3]);}
  glBegin(GL_TRIANGLES);for(unsigned i=0;i<6;++i){const float *v=s->xyuv+4*indices[i];glTexCoord2f(v[2],v[3]);glVertex2f(v[0],v[1]);}glEnd();
 }
 if(restore_min_filter)glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,restore_min_filter);
 }
 emit_profile.finish();
 n810_command_profile::scope restore_profile(82);
 { n810_command_profile::scope matrices_profile(84);
 glPopMatrix();glMatrixMode(GL_PROJECTION);glPopMatrix();glMatrixMode(GL_TEXTURE);glPopMatrix(); }
 { n810_command_profile::scope attributes_profile(85);glPopAttrib(); }
 { n810_command_profile::scope bindings_profile(86);
 glMatrixMode(matrix);glActiveTexture(active);glBindVertexArray(vao);glUseProgram(program); }
 return glGetError()==GL_NO_ERROR?0:-1;
}

/* Queue only inside the graphics dispatcher's bitmap run. No texture or
 * framebuffer mutation may cross sg_sprite_batch_flush(). Only admitted integer
 * UI rectangles share a model transform; all other sprites retain their matrices. */
static thread_local sg_sprite pending_sprites[64];
static thread_local unsigned pending_count;
static thread_local int pending_clip[4];
static thread_local bool pending_scissor;
static thread_local bool bitmap_run;
extern "C" void sg_sprite_batch_mode(int enabled){bitmap_run=enabled!=0;}
static bool batch_enabled(){const char *v=std::getenv("N810_SYMBIAN_SPRITE_BATCH");return bitmap_run&&v&&!std::strcmp(v,"1");}
extern "C" int sg_sprite_batch_flush(){
 if(!pending_count)return 0;
 unsigned count=pending_count;pending_count=0;
 int result=sg_sprite_draw_impl(pending_sprites,pending_scissor?pending_clip:nullptr,pending_scissor?1:0,pending_sprites,count);
 static unsigned batches=0,items=0;static unsigned long long saved=0;
 ++batches;items+=count;saved+=count-1;
 if(batches==1||batches%64==0)if(n810_runtime_debug()) std::fprintf(stderr,"GPU_SPRITE_BATCH batches=%u items=%u saved_setup=%llu max_items=64\n",batches,items,saved);
 return result;
}
static int enqueue_sprite(const sg_sprite *s,const int *clip,bool scissor){
 if(!s)return -1;
 bool compatible=!pending_count||(pending_sprites[0].texture==s->texture&&
  !std::memcmp(pending_sprites[0].projection,s->projection,sizeof s->projection)&&
  !std::memcmp(pending_sprites[0].color,s->color,sizeof s->color)&&pending_scissor==scissor&&
  (!scissor||!std::memcmp(pending_clip,clip,sizeof pending_clip)));
 if((!compatible||pending_count==64)&&sg_sprite_batch_flush())return -1;
 if(!pending_count){pending_scissor=scissor;if(scissor)std::memcpy(pending_clip,clip,sizeof pending_clip);}
 pending_sprites[pending_count++]=*s;return 0;
}
extern "C" int sg_sprite_draw(const sg_sprite *s){
 if(!batch_enabled())return sg_sprite_draw_impl(s,nullptr,0);
 int clip[4];bool enabled=glIsEnabled(GL_SCISSOR_TEST);if(enabled)glGetIntegerv(GL_SCISSOR_BOX,clip);
 return enqueue_sprite(s,clip,enabled);
}
extern "C" int sg_sprite_draw_regions(const sg_sprite *s,const int *clips,unsigned count){
 if(!count)return 0;if(!clips||count>512)return -1;
 if(!batch_enabled())return sg_sprite_draw_impl(s,clips,count);
 for(unsigned i=0;i<count;++i){if(clips[4*i+2]<=0||clips[4*i+3]<=0||enqueue_sprite(s,clips+4*i,true))return -1;}return 0;
}
#ifndef SG_SPRITE_TEST
#include "gpu_mask_texture.h"

#include "mask_cache_runtime.h"

#endif
