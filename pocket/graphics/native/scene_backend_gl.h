/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Standard-GL implementation of shared scene primitives. Targets and sources
 * are tiled textures; only explicit capture/presentation reads pixels. Driver
 * internal materialization is a separate capability, never inferred here. */
#ifndef POCKET_SCENE_BACKEND_GL_H
#define POCKET_SCENE_BACKEND_GL_H
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <sys/resource.h>
#include "present.h"
#include <dlfcn.h>
#include "../driver/mbx/common/mbx_owned_surface.h"
static int (*scene_surface_begin)(void),(*scene_surface_end)(struct mbx_owned_surface *),(*scene_surface_copy)(const struct mbx_surface_sink *),(*scene_surface_release)(void);
static int (*scene_surface_dma_copy)(const struct mbx_surface_dma_sink *);
int pocket_window_dma_fd(void *);
static int scene_surface_api(void){
 if(scene_surface_begin&&scene_surface_end&&scene_surface_copy&&scene_surface_release)return 0;
 scene_surface_dma_copy=(int (*)(const struct mbx_surface_dma_sink *))dlsym(RTLD_DEFAULT,"n810_mbx_surface_dma_copy");
 scene_surface_begin=(int (*)(void))dlsym(RTLD_DEFAULT,"n810_mbx_surface_begin");
 scene_surface_end=(int (*)(struct mbx_owned_surface *))dlsym(RTLD_DEFAULT,"n810_mbx_surface_end");
 scene_surface_copy=(int (*)(const struct mbx_surface_sink *))dlsym(RTLD_DEFAULT,"n810_mbx_surface_copy");
 scene_surface_release=(int (*)(void))dlsym(RTLD_DEFAULT,"n810_mbx_surface_release");
 return scene_surface_begin&&scene_surface_end&&scene_surface_copy&&scene_surface_release?0:-1;
}
#ifndef GL_PACK_INVERT_MESA
#define GL_PACK_INVERT_MESA 0x8758
#endif
typedef struct {float x,y;} Scene_FPoint;
typedef struct {uint8_t r,g,b,a;} Scene_Color;
typedef struct {Scene_FPoint position;Scene_Color color;Scene_FPoint tex_coord;} Scene_Vertex;
typedef struct {int x,y,w,h;} Scene_Rect;
typedef int Scene_BlendMode;
enum {Scene_BLENDMODE_NONE,Scene_BLENDMODE_BLEND,Scene_BLENDMODE_PREMULT};
enum {Scene_PIXELFORMAT_ABGR8888,Scene_PIXELFORMAT_RGB565,Scene_TEXTUREACCESS_STATIC,Scene_TEXTUREACCESS_TARGET,Scene_TEXTUREACCESS_TARGET_DEPTH,Scene_ScaleModeNearest,Scene_RENDERER_ACCELERATED=16,Scene_BLENDFACTOR_ONE,Scene_BLENDFACTOR_ONE_MINUS_SRC_ALPHA,Scene_BLENDOPERATION_ADD};
struct scene_gl_tile {GLuint color,fbo,depth;unsigned x,y,w,h,pw,ph;};
typedef struct scene_texture_gl Scene_Texture;
struct scene_geometry;
static void scene_geometry_free(struct scene_geometry *);
struct scene_command {Scene_Texture *source;size_t first;int count,clipped;Scene_Rect clip;Scene_BlendMode blend;int dx,dy;struct scene_geometry *compiled;};
typedef int (*Scene_RoomRegion)(float,float,float,float,float,unsigned,unsigned,int,int,unsigned,unsigned,unsigned,int);
struct scene_texture_gl {int bounds_valid;float bounds[4];void *cache_owner;unsigned cache_pages;int damage_valid;Scene_Rect damage;int recorded_scene;Scene_RoomRegion room_region;int (*room_eye)(float);float room_state[6];unsigned w,h,n,format,refs;Scene_BlendMode blend;struct scene_gl_tile *tiles;struct scene_command *commands;size_t count,capacity,vertices,vertex_capacity;Scene_Vertex *stream;int clear_pending;uint64_t revision;Scene_Color clear;};
typedef struct {const char *name;unsigned flags;} Scene_RendererInfo;
int pocket_window_acquire(void *,struct mbx_surface *);
int pocket_window_prepare(void *,struct mbx_surface *);
typedef struct {int sink_deferred,matrix_valid,matrix_forward,matrix_x,matrix_y,matrix_dx,matrix_dy;unsigned matrix_w,matrix_h;int profile,draw_profile,dma_damage,damage_cull;unsigned window_pages;uint64_t page_candidates,damage_culled_batches,geometry_builds,geometry_replays,draw_cpu_ns,draw_calls,geometry_cpu_ns,finish_cpu_ns,sink_cpu_ns;int translate_x,translate_y,sink_forward,last_sink_forward;void *presented_pixels;int presented_stride;void *sink_pixels;int sink_stride,sink_dma,sink_fd;uint64_t sink_bytes,sink_jobs,dma_bytes,dma_jobs;float color_float[256];OSMesaContext context;Scene_Texture *target;Scene_Rect clip;int clipped;Scene_Color color;Scene_BlendMode blend;void *window;int pack_invert;unsigned tile_first,tile_end;uint16_t *capture_tile;size_t capture_capacity;Scene_Vertex *filtered;unsigned *filtered_indices;size_t filtered_capacity;Scene_Rect occlusion[8];unsigned occlusion_count;int presenting,previous_room_valid;Scene_Texture *preserved_room,*presented_target;Scene_Rect preserve_rect;Scene_Vertex previous_room_vertices[6];float previous_room_state[6];unsigned previous_room_width,previous_room_height;Scene_RoomRegion previous_room_draw;int (*previous_room_eye)(float);uint64_t presented_revision,preserved_frames;uint64_t owner_checks,owner_rejects,target_switches,readback_calls,readback_bytes,presentation_bytes;} Scene_Renderer;
static int Scene_SetError(const char *text,...){(void)text;return -1;}
static Scene_Renderer *scene_device(void *window){
 OSMesaContext c=OSMesaGetCurrentContext();if(!c)return NULL;
 Scene_Renderer *r=calloc(1,sizeof(*r));if(r){for(unsigned i=0;i<256;i++)r->color_float[i]=i/255.f;r->context=c;r->window=window;r->profile=getenv("POCKET_SCENE_PROFILE")&&!strcmp(getenv("POCKET_SCENE_PROFILE"),"1");r->damage_cull=getenv("POCKET_SCENE_DAMAGE_CULL")&&!strcmp(getenv("POCKET_SCENE_DAMAGE_CULL"),"1");r->dma_damage=getenv("POCKET_SCENE_DMA_DAMAGE")&&!strcmp(getenv("POCKET_SCENE_DMA_DAMAGE"),"1");r->draw_profile=r->profile&&getenv("POCKET_SCENE_DRAW_PROFILE")&&!strcmp(getenv("POCKET_SCENE_DRAW_PROFILE"),"1");const char *extensions=(const char*)glGetString(GL_EXTENSIONS);r->pack_invert=extensions&&strstr(extensions,"GL_MESA_pack_invert");}return r;
}
/* Coarse opt-in process CPU counters: no per-primitive clock calls/logging. */
static uint64_t scene_gl_cpu(const Scene_Renderer *r){struct rusage u;if(!r->profile||getrusage(RUSAGE_SELF,&u))return 0;return ((uint64_t)u.ru_utime.tv_sec+u.ru_stime.tv_sec)*1000000000ULL+((uint64_t)u.ru_utime.tv_usec+u.ru_stime.tv_usec)*1000ULL;}
static void scene_device_close(Scene_Renderer *r){if(r){if(r->profile)fprintf(stderr,"POCKET_SCENE_CPU geometry_ns=%llu finish_ns=%llu sink_ns=%llu compiled_builds=%llu compiled_replays=%llu culled_batches=%llu page_candidates=%llu draw_ns=%llu draw_calls=%llu\n",(unsigned long long)r->geometry_cpu_ns,(unsigned long long)r->finish_cpu_ns,(unsigned long long)r->sink_cpu_ns,(unsigned long long)r->geometry_builds,(unsigned long long)r->geometry_replays,(unsigned long long)r->damage_culled_batches,(unsigned long long)r->page_candidates,(unsigned long long)r->draw_cpu_ns,(unsigned long long)r->draw_calls);free(r->filtered);free(r->filtered_indices);free(r->capture_tile);}free(r);}
static void scene_gl_draw_arrays(Scene_Renderer *r,unsigned count){uint64_t start=r->draw_profile?scene_gl_cpu(r):0;glDrawArrays(GL_TRIANGLES,0,count);if(r->draw_profile)r->draw_cpu_ns+=scene_gl_cpu(r)-start;++r->draw_calls;}
static void scene_gl_draw_elements(Scene_Renderer *r,unsigned count,const unsigned *elements){uint64_t start=r->draw_profile?scene_gl_cpu(r):0;glDrawElements(GL_TRIANGLES,count,GL_UNSIGNED_INT,elements);if(r->draw_profile)r->draw_cpu_ns+=scene_gl_cpu(r)-start;++r->draw_calls;}
static int Scene_GetRendererInfo(Scene_Renderer *r,Scene_RendererInfo *i){
 if(!r||OSMesaGetCurrentContext()!=r->context)return -1;
 i->name=(const char*)glGetString(GL_RENDERER);i->flags=i->name&&strstr(i->name,"Nokia MBX")?Scene_RENDERER_ACCELERATED:0;return 0;
}
static int scene_gl_owner(Scene_Renderer *r){
 if(!r)return -1;
 ++r->owner_checks;
 if(OSMesaGetCurrentContext()!=r->context){++r->owner_rejects;return -1;}return 0;
}
static void scene_gl_bind(Scene_Renderer *r,GLuint fbo){
 GLint current;glGetIntegerv(GL_FRAMEBUFFER_BINDING,&current);
 if((GLuint)current!=fbo){glBindFramebuffer(GL_FRAMEBUFFER,fbo);++r->target_switches;}
}
static void Scene_DestroyTexture(Scene_Texture *t){if(!t||--t->refs)return;
 if(t->cache_owner)((Scene_Renderer *)t->cache_owner)->window_pages-=t->cache_pages;
 for(size_t i=0;i<t->count;i++){scene_geometry_free(t->commands[i].compiled);Scene_DestroyTexture(t->commands[i].source);}
 free(t->commands);free(t->stream);for(unsigned i=0;i<t->n;i++){glDeleteFramebuffers(1,&t->tiles[i].fbo);glDeleteRenderbuffers(1,&t->tiles[i].depth);glDeleteTextures(1,&t->tiles[i].color);}free(t->tiles);free(t);}
static Scene_Texture *Scene_CreateTexture(Scene_Renderer *r,unsigned format,unsigned access,unsigned w,unsigned h){
 if(!r||!w||!h||w>4096||h>4096)return NULL;
 Scene_Texture *t=calloc(1,sizeof(*t));if(!t)return NULL;t->w=w;t->h=h;t->format=format;t->refs=1;
 unsigned step=128,step_y=128; /* source textures retain their verified layout */
 const char *output_tile=getenv("POCKET_SCENE_OUTPUT_TILE");
 if(format==Scene_PIXELFORMAT_RGB565&&access==Scene_TEXTUREACCESS_TARGET&&output_tile){if(!strcmp(output_tile,"256"))step=256;else if(!strcmp(output_tile,"400"))step=400;else if(!strcmp(output_tile,"400x256")){step=400;step_y=256;}else if(!strcmp(output_tile,"256x256")){step=step_y=256;}else if(!strcmp(output_tile,"800x480")){step=800;step_y=480;}}
 t->n=((w+step-1)/step)*((h+step_y-1)/step_y);t->tiles=calloc(t->n,sizeof(*t->tiles));if(!t->tiles){free(t);return NULL;}
 unsigned at=0;for(unsigned y=0;y<h;y+=step_y)for(unsigned x=0;x<w;x+=step){struct scene_gl_tile *q=t->tiles+at++;q->x=x;q->y=y;q->w=w-x<step?w-x:step;q->h=h-y<step_y?h-y:step_y;q->pw=q->ph=16;while(q->pw<q->w)q->pw*=2;while(q->ph<q->h)q->ph*=2;if(format==Scene_PIXELFORMAT_RGB565){q->pw=step;q->ph=step_y;}else if(access==Scene_TEXTUREACCESS_TARGET&&getenv("POCKET_SCENE_WINDOW_IMAGES")&&!strcmp(getenv("POCKET_SCENE_WINDOW_IMAGES"),"1")){q->pw=q->ph=128;}
  glGenTextures(1,&q->color);glBindTexture(GL_TEXTURE_2D,q->color);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);glTexImage2D(GL_TEXTURE_2D,0,format==Scene_PIXELFORMAT_RGB565?GL_RGB565:GL_RGBA,q->pw,q->ph,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  if(access==Scene_TEXTUREACCESS_TARGET||access==Scene_TEXTUREACCESS_TARGET_DEPTH){glGenFramebuffers(1,&q->fbo);scene_gl_bind(r,q->fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,q->color,0);if(access==Scene_TEXTUREACCESS_TARGET_DEPTH){glGenRenderbuffers(1,&q->depth);glBindRenderbuffer(GL_RENDERBUFFER,q->depth);glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,q->pw,q->ph);glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,q->depth);}if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE)goto fail;t->clear_pending=1;t->clear=(Scene_Color){0,0,0,0};}
 }
 if(glGetError()!=GL_NO_ERROR)goto fail;
 return t;
 fail:Scene_DestroyTexture(t);return NULL;
}
static int Scene_UpdateTexture(Scene_Texture *t,const Scene_Rect *rect,const void *pixels,int stride){
 if(!t||t->refs!=1||rect||!pixels||stride<(int)t->w*(t->format==Scene_PIXELFORMAT_RGB565?2:4))return -1;
 GLint align,row;glGetIntegerv(GL_UNPACK_ALIGNMENT,&align);glGetIntegerv(GL_UNPACK_ROW_LENGTH,&row);unsigned bpp=t->format==Scene_PIXELFORMAT_RGB565?2:4;
 glPixelStorei(GL_UNPACK_ALIGNMENT,1);glPixelStorei(GL_UNPACK_ROW_LENGTH,stride/bpp);
 for(unsigned i=0;i<t->n;i++){struct scene_gl_tile *q=t->tiles+i;glBindTexture(GL_TEXTURE_2D,q->color);glTexSubImage2D(GL_TEXTURE_2D,0,0,0,q->w,q->h,bpp==2?GL_RGB:GL_RGBA,bpp==2?GL_UNSIGNED_SHORT_5_6_5:GL_UNSIGNED_BYTE,(const char*)pixels+q->y*stride+q->x*bpp);}
 glPixelStorei(GL_UNPACK_ALIGNMENT,align);glPixelStorei(GL_UNPACK_ROW_LENGTH,row);return glGetError()==GL_NO_ERROR?0:-1;
}
static int Scene_SetTextureBlendMode(Scene_Texture *t,Scene_BlendMode b){if(!t)return -1;t->blend=b;return 0;}
static int Scene_SetTextureScaleMode(Scene_Texture *t,int mode){return t&&mode==Scene_ScaleModeNearest?0:-1;}
static Scene_BlendMode Scene_ComposeCustomBlendMode(int a,int b,int c,int d,int e,int f){return a==Scene_BLENDFACTOR_ONE&&d==a&&b==Scene_BLENDFACTOR_ONE_MINUS_SRC_ALPHA&&e==b&&c==Scene_BLENDOPERATION_ADD&&f==c?Scene_BLENDMODE_PREMULT:-1;}
static int Scene_SetRenderTarget(Scene_Renderer *r,Scene_Texture *t){if(scene_gl_owner(r))return -1;r->target=t;return 0;}
static int Scene_RenderSetLogicalSize(Scene_Renderer *r,int w,int h){(void)w;(void)h;return r?0:-1;}
static int Scene_RenderSetScale(Scene_Renderer *r,float x,float y){return r&&x==1&&y==1?0:-1;}
static int Scene_RenderSetViewport(Scene_Renderer *r,const Scene_Rect *v){return r&&!v?0:-1;}
static int Scene_RenderSetClipRect(Scene_Renderer *r,const Scene_Rect *c){if(!r)return -1;r->clipped=!!c;if(c)r->clip=*c;return 0;}
static int Scene_SetRenderDrawColor(Scene_Renderer *r,uint8_t a,uint8_t b,uint8_t c,uint8_t d){if(!r)return -1;r->color=(Scene_Color){a,b,c,d};return 0;}
static int Scene_SetRenderDrawBlendMode(Scene_Renderer *r,Scene_BlendMode mode){if(!r)return -1;r->blend=mode;return 0;}
static int scene_gl_target(Scene_Renderer *r,struct scene_gl_tile *q){
 scene_gl_bind(r,q->fbo);glViewport(0,0,q->pw,q->ph);glEnable(GL_SCISSOR_TEST);
 int x=q->x,y=q->y,xx=x+q->w,yy=y+q->h;
 if(r->clipped){if(x<r->clip.x)x=r->clip.x;if(y<r->clip.y)y=r->clip.y;if(xx>r->clip.x+r->clip.w)xx=r->clip.x+r->clip.w;if(yy>r->clip.y+r->clip.h)yy=r->clip.y+r->clip.h;}
 /* A DMA presentation retains pixels outside damage. Its source is private
  * and complete only inside this scissor; sampled FBOs never use this path. */
 if(r->sink_dma&&r->dma_damage&&r->target->damage_valid){const Scene_Rect *d=&r->target->damage;
  if(x<d->x)x=d->x;
  if(y<d->y)y=d->y;
  if(xx>d->x+d->w)xx=d->x+d->w;
  if(yy>d->y+d->h)yy=d->y+d->h;
 }
 if(xx<=x||yy<=y)return 0;
 if(x==(int)q->x&&y==(int)q->y&&xx-x==(int)q->pw&&yy-y==(int)q->ph)glDisable(GL_SCISSOR_TEST);
 else glScissor(x-q->x,r->sink_forward?y-q->y:q->ph-(yy-q->y),xx-x,yy-y);
 int cached=getenv("POCKET_SCENE_MATRIX_CACHE")&&!strcmp(getenv("POCKET_SCENE_MATRIX_CACHE"),"1");
 int projection=cached&&r->matrix_valid&&r->matrix_forward==r->sink_forward&&r->matrix_x==(int)q->x&&r->matrix_y==(int)q->y&&r->matrix_w==q->pw&&r->matrix_h==q->ph;
 if(!projection){glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(q->x,q->x+q->pw,r->sink_forward?q->y:q->y+q->ph,r->sink_forward?q->y+q->ph:q->y,-1,1);glMatrixMode(GL_TEXTURE);glLoadIdentity();}
 if(!projection||r->matrix_dx!=r->translate_x||r->matrix_dy!=r->translate_y){glMatrixMode(GL_MODELVIEW);glLoadIdentity();if(r->translate_x||r->translate_y)glTranslatef(r->translate_x,r->translate_y,0);}
 glMatrixMode(GL_MODELVIEW);r->matrix_valid=1;r->matrix_forward=r->sink_forward;r->matrix_x=q->x;r->matrix_y=q->y;r->matrix_w=q->pw;r->matrix_h=q->ph;r->matrix_dx=r->translate_x;r->matrix_dy=r->translate_y;
 glDisable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_LIGHTING);glDisable(GL_CULL_FACE);glDisable(GL_DITHER);glDisable(GL_VERTEX_PROGRAM_ARB);glShadeModel(GL_SMOOTH);return 1;
}
static void scene_gl_blend(Scene_BlendMode mode){if(mode==Scene_BLENDMODE_NONE)glDisable(GL_BLEND);else{glEnable(GL_BLEND);glBlendFuncSeparate(mode==Scene_BLENDMODE_PREMULT?GL_ONE:GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA,GL_ONE,GL_ONE_MINUS_SRC_ALPHA);}}
static int Scene_RenderClear(Scene_Renderer *r){
 if(!r)return -1;
 if(!r->target)return 0;
 /* Whole-target clear starts a new immutable command list. Clipped clears
  * are not used by the scene API and must not discard earlier commands. */
 if(r->clipped||r->target->refs!=1)return -1;
 Scene_Texture *t=r->target;
 for(size_t i=0;i<t->count;i++){scene_geometry_free(t->commands[i].compiled);Scene_DestroyTexture(t->commands[i].source);}
 t->count=t->vertices=0;++t->revision;t->damage_valid=0;t->clear_pending=1;t->clear=r->color;return 0;
}
/* Fused opaque Room draw. The shared scene retains camera/geometry, not a
 * CPU image. The same depth target then accepts ordinary 2D overlays. */
static int scene_gl_room_now(Scene_Renderer *r,Scene_Texture *source,const Scene_Vertex *v,int n){
 if(n!=6||source->blend!=Scene_BLENDMODE_NONE)return -1;
 if(source==r->preserved_room)return 0;
 int x=(int)v[0].position.x,y=(int)v[0].position.y;
 if(v[0].position.x!=x||v[0].position.y!=y||v[2].position.x!=x+(int)source->w||v[2].position.y!=y+(int)source->h)return -1;
 for(unsigned ti=r->tile_first;ti<r->tile_end;ti++){
  struct scene_gl_tile *q=r->target->tiles+ti;if(!q->depth)return -1;
  if(!scene_gl_target(r,q))continue;
  int left=x>(int)q->x?x:(int)q->x,top=y>(int)q->y?y:(int)q->y;
  int right=x+(int)source->w<(int)(q->x+q->w)?x+(int)source->w:(int)(q->x+q->w),bottom=y+(int)source->h<(int)(q->y+q->h)?y+(int)source->h:(int)(q->y+q->h);
  if(r->clipped){if(left<r->clip.x)left=r->clip.x;if(top<r->clip.y)top=r->clip.y;if(right>r->clip.x+r->clip.w)right=r->clip.x+r->clip.w;if(bottom>r->clip.y+r->clip.h)bottom=r->clip.y+r->clip.h;}
  if(left>=right||top>=bottom)continue;
  glEnable(GL_SCISSOR_TEST);glScissor(left-q->x,q->ph-(bottom-q->y),right-left,bottom-top);
  /* Opaque Room background, without clearing unrelated desktop pixels. */
  GLfloat pos[]={x,y,0,x+(int)source->w,y,0,x+(int)source->w,y+(int)source->h,0,x,y,0,x+(int)source->w,y+(int)source->h,0,x,y+(int)source->h,0};
  glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);glDisableClientState(GL_TEXTURE_COORD_ARRAY);glEnableClientState(GL_VERTEX_ARRAY);glColor4f(0,0,0,1);glVertexPointer(3,GL_FLOAT,0,pos);glDrawArrays(GL_TRIANGLES,0,6);
  r->matrix_valid=0; /* Room owns and replaces all three matrices. */
  float *a=source->room_state;if(source->room_eye(a[5])||source->room_region(a[0],a[1],a[2],a[3],a[4],source->w,source->h,(int)q->x-x,(int)q->y-y,q->w,q->h,q->ph,1))return -1;
 }
 return glGetError()==GL_NO_ERROR?0:-1;
}
static int scene_gl_hidden(Scene_Renderer *r,float left,float top,float right,float bottom){
 if(r->sink_dma&&r->dma_damage&&r->target->damage_valid){const Scene_Rect *d=&r->target->damage;
  if(right<=d->x||bottom<=d->y||left>=d->x+d->w||top>=d->y+d->h)return 1;
 }
 for(unsigned i=0;i<r->occlusion_count;i++){const Scene_Rect *q=r->occlusion+i;if(left>=q->x&&top>=q->y&&right<=q->x+q->w&&bottom<=q->y+q->h)return 1;}return 0;
}
/* Immutable command-owned conversion. Positions stay in model coordinates;
 * destination/scissor/translation and occlusion are evaluated on every replay.
 * No framebuffer pixels or driver resource lifetimes are cached here. */
struct scene_primitive {float left,top,right,bottom;int page,uv_valid;float colors[12],uv[12];};
struct scene_array_vertex {float position[3],color[4],uv[4];};
struct scene_geometry {GLuint buffer;unsigned vertices;unsigned *page_offsets,*page_primitives;int white;struct scene_array_vertex *array;struct scene_primitive primitive[];};
static void scene_geometry_free(struct scene_geometry *g){if(g){if(g->buffer)glDeleteBuffers(1,&g->buffer);free(g->page_offsets);free(g->page_primitives);}free(g);}
static struct scene_geometry *scene_gl_compile(Scene_Renderer *r,Scene_Texture *source,const Scene_Vertex *v,int n){
 int arrays=(getenv("POCKET_SCENE_INDEXED")&&!strcmp(getenv("POCKET_SCENE_INDEXED"),"1"))||(getenv("POCKET_SCENE_VBO")&&!strcmp(getenv("POCKET_SCENE_VBO"),"1"));
 struct scene_geometry *g=calloc(1,sizeof(*g)+(size_t)(n/3)*sizeof(g->primitive[0])+(arrays?(size_t)n*sizeof(struct scene_array_vertex):0));if(!g)return NULL;
 g->array=arrays?(void *)(g->primitive+n/3):NULL;g->vertices=n;
 g->white=source!=NULL;
 for(int first=0;first<n;first+=3){struct scene_primitive *b=g->primitive+first/3;
  b->left=b->right=v[first].position.x;b->top=b->bottom=v[first].position.y;b->page=source?-1:0;b->uv_valid=1;
  for(unsigned k=0;k<3;k++){const Scene_Vertex *a=v+first+k;
   if(a->position.x<b->left)b->left=a->position.x;
   if(a->position.x>b->right)b->right=a->position.x;
   if(a->position.y<b->top)b->top=a->position.y;
   if(a->position.y>b->bottom)b->bottom=a->position.y;
   if(a->color.r!=255||a->color.g!=255||a->color.b!=255||a->color.a!=255)g->white=0;
   b->colors[k*4]=r->color_float[a->color.r];b->colors[k*4+1]=r->color_float[a->color.g];b->colors[k*4+2]=r->color_float[a->color.b];b->colors[k*4+3]=r->color_float[a->color.a];
  }
  if(source){float u=(v[first].tex_coord.x+v[first+1].tex_coord.x+v[first+2].tex_coord.x)*source->w/3,t=(v[first].tex_coord.y+v[first+1].tex_coord.y+v[first+2].tex_coord.y)*source->h/3;
   for(unsigned i=0;i<source->n;i++){struct scene_gl_tile *q=source->tiles+i;if(u<q->x||u>=q->x+q->w||t<q->y||t>=q->y+q->h)continue;b->page=i;
    for(unsigned k=0;k<3;k++){float x=v[first+k].tex_coord.x*source->w-q->x,y=v[first+k].tex_coord.y*source->h-q->y;
     if(x<-.01f||x>q->w+.01f||y<-.01f||y>q->h+.01f)b->uv_valid=0;
     b->uv[k*4]=x/q->pw;b->uv[k*4+1]=q->fbo?1-y/q->ph:y/q->ph;b->uv[k*4+2]=0;b->uv[k*4+3]=1;
    }break;
   }
  }
 }
 for(int i=0;g->array&&i<n;++i){struct scene_array_vertex *a=g->array+i;const struct scene_primitive *b=g->primitive+i/3;
  a->position[0]=v[i].position.x;a->position[1]=v[i].position.y;a->position[2]=0;
  memcpy(a->color,b->colors+(i%3)*4,sizeof(a->color));memcpy(a->uv,b->uv+(i%3)*4,sizeof(a->uv));
 }
 /* Stable page groups retain original primitive order within each sampler.
  * This replaces replay's atlas-page x triangle scan and vertex scratch copy.
  * The existing page-major draw order and exact active attributes are kept. */
 if(source&&source->n>1&&getenv("POCKET_SCENE_PAGE_GROUPS")&&!strcmp(getenv("POCKET_SCENE_PAGE_GROUPS"),"1")){
  g->page_offsets=calloc((size_t)source->n+1,sizeof(unsigned));
  g->page_primitives=malloc((size_t)(n/3+1)*sizeof(unsigned));
  unsigned *cursor=calloc(source->n,sizeof(unsigned));
  if(!g->page_offsets||!g->page_primitives||!cursor){free(cursor);scene_geometry_free(g);return NULL;}
  for(int i=0;i<n/3;i++){int page=g->primitive[i].page;if(page>=0)++g->page_offsets[page+1];}
  for(unsigned i=0;i<source->n;i++){g->page_offsets[i+1]+=g->page_offsets[i];cursor[i]=g->page_offsets[i];}
  for(int i=0;i<n/3;i++){int page=g->primitive[i].page;if(page>=0)g->page_primitives[cursor[page]++]=i;}
  free(cursor);
 }
 ++r->geometry_builds;return g;
}
static void scene_recorded_bounds(Scene_Texture *t){
 t->bounds_valid=0;if(!t->vertices)return;
 for(size_t i=0;i<t->count;i++)if(t->commands[i].dx||t->commands[i].dy||(t->commands[i].source&&(t->commands[i].source->recorded_scene||t->commands[i].source->room_region)))return;
 float left=t->stream[0].position.x,right=left,top=t->stream[0].position.y,bottom=top;
 for(size_t i=0;i<t->vertices;i++){float x=t->stream[i].position.x,y=t->stream[i].position.y;
  if(!isfinite(x)||!isfinite(y)||fabsf(x)>8192||fabsf(y)>8192)return;
  if(x<left)left=x;
  if(x>right)right=x;
  if(y<top)top=y;
  if(y>bottom)bottom=y;
 }
 t->bounds[0]=left;t->bounds[1]=top;t->bounds[2]=right;t->bounds[3]=bottom;t->bounds_valid=1;
}
static int scene_gl_geometry_now(Scene_Renderer *r,Scene_Texture *source,const Scene_Vertex *v,int n,const int *indices,int ni,struct scene_geometry **saved){
 if(!r||!r->target||r->target->refs!=1||n<0||n%3||indices||ni||source==r->target)return -1;
 if(source&&source->recorded_scene){
  /* At execution the DMA damage is final. Skip an immutable batch only
   * when its complete conservative bounds miss that destination damage. */
  if(r->damage_cull&&r->sink_dma&&r->dma_damage&&r->target->damage_valid&&source->bounds_valid){
   const Scene_Rect *d=&r->target->damage;
   if(source->bounds[2]+r->translate_x+1<=d->x||source->bounds[0]+r->translate_x-1>=d->x+d->w||
      source->bounds[3]+r->translate_y+1<=d->y||source->bounds[1]+r->translate_y-1>=d->y+d->h){++r->damage_culled_batches;return 0;}
  }
  Scene_Rect saved_clip=r->clip;int saved_clipped=r->clipped;Scene_BlendMode saved_blend=r->blend;int result=0;
  int saved_x=r->translate_x,saved_y=r->translate_y;
  for(size_t i=0;i<source->count&&!result;i++){struct scene_command *c=source->commands+i;r->translate_x=saved_x+c->dx;r->translate_y=saved_y+c->dy;r->clip=c->clip;r->clip.x+=r->translate_x;r->clip.y+=r->translate_y;r->clipped=c->clipped;r->blend=c->blend;result=scene_gl_geometry_now(r,c->source,source->stream+c->first,c->count,NULL,0,&c->compiled);}
  r->translate_x=saved_x;r->translate_y=saved_y;r->clip=saved_clip;r->clipped=saved_clipped;r->blend=saved_blend;return result;
 }
 if(source&&source->room_region)return scene_gl_room_now(r,source,v,n);
 struct scene_geometry *compiled=NULL;
 if(saved&&getenv("POCKET_SCENE_COMPILED")&&!strcmp(getenv("POCKET_SCENE_COMPILED"),"1")){if(!*saved)*saved=scene_gl_compile(r,source,v,n);if(!*saved)return -1;compiled=*saved;++r->geometry_replays;}
 int vbo=compiled&&compiled->array&&getenv("POCKET_SCENE_VBO")&&!strcmp(getenv("POCKET_SCENE_VBO"),"1");
 int indexed=vbo||(compiled&&compiled->array&&getenv("POCKET_SCENE_INDEXED")&&!strcmp(getenv("POCKET_SCENE_INDEXED"),"1"));
 if(vbo&&!compiled->buffer){glGenBuffers(1,&compiled->buffer);glBindBuffer(GL_ARRAY_BUFFER,compiled->buffer);glBufferData(GL_ARRAY_BUFFER,(size_t)compiled->vertices*sizeof(*compiled->array),compiled->array,GL_STATIC_DRAW);glBindBuffer(GL_ARRAY_BUFFER,0);if(glGetError()!=GL_NO_ERROR)return -1;}
 int white=compiled?compiled->white:source!=NULL;
 for(int i=0;!compiled&&white&&i<n;i++)white=v[i].color.r==255&&v[i].color.g==255&&v[i].color.b==255&&v[i].color.a==255;
 glEnableClientState(GL_VERTEX_ARRAY);if(white){glDisableClientState(GL_COLOR_ARRAY);glColor4f(1,1,1,1);}else glEnableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);
 for(unsigned ti=r->tile_first;ti<r->tile_end;ti++){if(!scene_gl_target(r,r->target->tiles+ti))continue;
  /* Cull to the destination once, before walking atlas pages. Retain scratch
   * storage across frames; no pixel materialization or per-page rescanning. */
  const Scene_Vertex *vertices=v;int vertex_count=n;
  if(source&&source->n>1&&!(compiled&&compiled->page_offsets)){
   if((size_t)n>r->filtered_capacity){Scene_Vertex *next=realloc(r->filtered,(size_t)n*sizeof(*next));if(!next)return -1;r->filtered=next;unsigned *ids=realloc(r->filtered_indices,(size_t)(n/3)*sizeof(*ids));if(!ids)return -1;r->filtered_indices=ids;r->filtered_capacity=n;}
   r->page_candidates+=(unsigned)n/3;
   vertex_count=0;struct scene_gl_tile *dest=r->target->tiles+ti;
   for(int first=0;first<n;first+=3){float left=v[first].position.x,right=left,top=v[first].position.y,bottom=top;
    if(compiled){const struct scene_primitive *b=compiled->primitive+first/3;left=b->left;right=b->right;top=b->top;bottom=b->bottom;}
    for(unsigned k=1;!compiled&&k<3;k++){float x=v[first+k].position.x,y=v[first+k].position.y;if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;}
    if(right+r->translate_x<=dest->x||left+r->translate_x>=dest->x+dest->w||bottom+r->translate_y<=dest->y||top+r->translate_y>=dest->y+dest->h||scene_gl_hidden(r,left+r->translate_x,top+r->translate_y,right+r->translate_x,bottom+r->translate_y))continue;
    r->filtered_indices[vertex_count/3]=first/3;memcpy(r->filtered+vertex_count,v+first,3*sizeof(*v));vertex_count+=3;
   }
   vertices=r->filtered;
  }
  for(unsigned si=0;si<(source?source->n:1);si++){
   if(compiled&&compiled->page_offsets&&compiled->page_offsets[si]==compiled->page_offsets[si+1])continue;
   struct scene_gl_tile *q=source?source->tiles+si:NULL;scene_gl_blend(source?source->blend:r->blend);
   if(source){glEnable(GL_TEXTURE_2D);glBindTexture(GL_TEXTURE_2D,q->color);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,white?GL_REPLACE:GL_MODULATE);glEnableClientState(GL_TEXTURE_COORD_ARRAY);}else{glDisable(GL_TEXTURE_2D);glDisableClientState(GL_TEXTURE_COORD_ARRAY);}
   /* Match the verified 256-triangle Mesa draw bound. */
   float positions[256*9],colors[256*12],uv[256*12];unsigned elements[256*3],used=0;
   if(indexed){
    glBindBuffer(GL_ARRAY_BUFFER,vbo?compiled->buffer:0);glBindBuffer(GL_ELEMENT_ARRAY_BUFFER,0);
    glVertexPointer(3,GL_FLOAT,sizeof(*compiled->array),vbo?(void *)0:compiled->array[0].position);
    glColorPointer(4,GL_FLOAT,sizeof(*compiled->array),vbo?(void *)(3*sizeof(float)):compiled->array[0].color);
    if(q)glTexCoordPointer(4,GL_FLOAT,sizeof(*compiled->array),vbo?(void *)(7*sizeof(float)):compiled->array[0].uv);
   }
   unsigned page_first=compiled&&compiled->page_offsets?compiled->page_offsets[si]:0;
   unsigned page_end=compiled&&compiled->page_offsets?compiled->page_offsets[si+1]:(unsigned)vertex_count/3;
   r->page_candidates+=page_end-page_first;
   for(unsigned entry=page_first;entry<page_end;entry++){
    unsigned first=compiled&&compiled->page_offsets?compiled->page_primitives[entry]*3:entry*3;
    struct scene_gl_tile *dest=r->target->tiles+ti;
    const struct scene_primitive *pre=compiled?compiled->primitive+(vertices==r->filtered?r->filtered_indices[first/3]:(unsigned)first/3):NULL;
    float left=vertices[first].position.x,right=left,top=vertices[first].position.y,bottom=top;
    if(pre){left=pre->left;right=pre->right;top=pre->top;bottom=pre->bottom;}
    for(unsigned k=1;!pre&&k<3;k++){float x=vertices[first+k].position.x,y=vertices[first+k].position.y;if(x<left)left=x;if(x>right)right=x;if(y<top)top=y;if(y>bottom)bottom=y;}
    if(right+r->translate_x<=dest->x||left+r->translate_x>=dest->x+dest->w||bottom+r->translate_y<=dest->y||top+r->translate_y>=dest->y+dest->h||scene_gl_hidden(r,left+r->translate_x,top+r->translate_y,right+r->translate_x,bottom+r->translate_y))continue;
    if(pre&&q&&pre->page!=(int)si)continue;
    if(!pre&&q){float u=(vertices[first].tex_coord.x+vertices[first+1].tex_coord.x+vertices[first+2].tex_coord.x)*source->w/3,tt=(vertices[first].tex_coord.y+vertices[first+1].tex_coord.y+vertices[first+2].tex_coord.y)*source->h/3;if(u<q->x||u>=q->x+q->w||tt<q->y||tt>=q->y+q->h)continue;}
    /* Cyclically rotate the first triangle of an exact shared-edge quad.
     * Winding and smooth interpolation stay identical; the MBX encoder can
     * then reuse the common edge instead of sending six complete tuples. */
    unsigned rotate=first+5<(unsigned)vertex_count&&!memcmp(vertices+first,vertices+first+3,sizeof(*vertices))&&!memcmp(vertices+first+2,vertices+first+4,sizeof(*vertices));
    if(indexed){
     if(q&&!pre->uv_valid)return -1;
     unsigned origin=(unsigned)(pre-compiled->primitive)*3;
     for(unsigned k=0;k<3;k++)elements[used*3+k]=origin+(rotate?(k+1)%3:k);
     if(++used==256){scene_gl_draw_elements(r,used*3,elements);used=0;}
     continue;
    }
    for(unsigned k=0;k<3;k++){unsigned vk=rotate?(k+1)%3:k;const Scene_Vertex *a=vertices+first+vk;if(pre){positions[used*9+k*3]=a->position.x;positions[used*9+k*3+1]=a->position.y;positions[used*9+k*3+2]=0;memcpy(colors+used*12+k*4,pre->colors+vk*4,4*sizeof(float));if(q){if(!pre->uv_valid)return -1;memcpy(uv+used*12+k*4,pre->uv+vk*4,4*sizeof(float));}continue;}positions[used*9+k*3]=a->position.x;positions[used*9+k*3+1]=a->position.y;positions[used*9+k*3+2]=0;colors[used*12+k*4]=r->color_float[a->color.r];colors[used*12+k*4+1]=r->color_float[a->color.g];colors[used*12+k*4+2]=r->color_float[a->color.b];colors[used*12+k*4+3]=r->color_float[a->color.a];
     if(q){float u=a->tex_coord.x*source->w-q->x,t=a->tex_coord.y*source->h-q->y;if(u<-.01f||u>q->w+.01f||t<-.01f||t>q->h+.01f)return -1;uv[used*12+k*4]=u/q->pw;uv[used*12+k*4+1]=q->fbo?1-t/q->ph:t/q->ph;uv[used*12+k*4+2]=0;uv[used*12+k*4+3]=1;}}
    ++used;
    if(used==256){glVertexPointer(3,GL_FLOAT,0,positions);glColorPointer(4,GL_FLOAT,0,colors);if(q)glTexCoordPointer(4,GL_FLOAT,0,uv);scene_gl_draw_arrays(r,used*3);used=0;}
   }
   if(used&&indexed)scene_gl_draw_elements(r,used*3,elements);
   else if(used){glVertexPointer(3,GL_FLOAT,0,positions);glColorPointer(4,GL_FLOAT,0,colors);if(q)glTexCoordPointer(4,GL_FLOAT,0,uv);scene_gl_draw_arrays(r,used*3);}
   if(indexed)glBindBuffer(GL_ARRAY_BUFFER,0);
  }
 }
 return glGetError()==GL_NO_ERROR?0:-1;
}
/* Only discard earlier draws when an exact, unblended rectangle overwrites
 * every visible pixel in this tile. Transparent and clipped partial draws
 * keep their dependencies. This also avoids uploading fully hidden layers. */
static int scene_gl_covers(const Scene_Texture *t,const struct scene_command *c,const struct scene_gl_tile *q){
 if(c->count!=6||(c->source?c->source->blend:c->blend)!=Scene_BLENDMODE_NONE)return 0;
 const Scene_Vertex *v=t->stream+c->first;
 float x=v[0].position.x,y=v[0].position.y,xx=v[2].position.x,yy=v[2].position.y;
 if(!(xx>x&&yy>y)||x>q->x||y>q->y||xx<q->x+q->w||yy<q->y+q->h)return 0;
 const unsigned corners[6]={0,1,2,0,2,3};
 for(unsigned i=0;i<6;i++){unsigned k=corners[i];if(v[i].position.x!=((k==1||k==2)?xx:x)||v[i].position.y!=(k>=2?yy:y))return 0;}
 if(c->clipped&&(c->clip.x>(int)q->x||c->clip.y>(int)q->y||c->clip.x+c->clip.w<(int)(q->x+q->w)||c->clip.y+c->clip.h<(int)(q->y+q->h)))return 0;
 return 1;
}
static int scene_gl_opaque_rect(const Scene_Texture *t,const struct scene_command *c,Scene_Rect *out){
 if(c->count!=6||(c->source?c->source->blend:c->blend)!=Scene_BLENDMODE_NONE)return 0;
 const Scene_Vertex *v=t->stream+c->first;float x=v[0].position.x,y=v[0].position.y,xx=v[2].position.x,yy=v[2].position.y;
 if(!(xx>x&&yy>y)||x!=floorf(x)||y!=floorf(y)||xx!=floorf(xx)||yy!=floorf(yy))return 0;
 const unsigned corners[6]={0,1,2,0,2,3};for(unsigned i=0;i<6;i++){unsigned k=corners[i];if(v[i].position.x!=((k==1||k==2)?xx:x)||v[i].position.y!=(k>=2?yy:y))return 0;}
 if(c->clipped){if(x<c->clip.x)x=c->clip.x;if(y<c->clip.y)y=c->clip.y;if(xx>c->clip.x+c->clip.w)xx=c->clip.x+c->clip.w;if(yy>c->clip.y+c->clip.h)yy=c->clip.y+c->clip.h;}
 if(xx<=x||yy<=y)return 0;
 *out=(Scene_Rect){x,y,xx-x,yy-y};return 1;
}
/* Submit a complete tile before visiting another target. This avoids
 * repeated FBO materialization and dependence on a four-target replay cache. */
static int scene_gl_damaged(const Scene_Texture *t,const struct scene_gl_tile *q){
 if(!t->damage_valid)return 1;
 const Scene_Rect *d=&t->damage;
 return d->x<(int)(q->x+q->w)&&d->y<(int)(q->y+q->h)&&d->x+d->w>(int)q->x&&d->y+d->h>(int)q->y;
}
static int scene_gl_flush(Scene_Renderer *r,Scene_Texture *t){
 if(!t||(!t->count&&!t->clear_pending))return 0;
 Scene_Texture *old=r->target;Scene_Rect clip=r->clip;int clipped=r->clipped;Scene_BlendMode blend=r->blend;
 unsigned first=r->tile_first,end=r->tile_end;int result=0;r->target=t;r->matrix_valid=0;
 unsigned rooms=0;for(size_t j=0;j<t->count;j++)if(t->commands[j].source&&t->commands[j].source->room_region)rooms++;
 if(rooms>1|| (rooms&&!t->clear_pending)){r->target=old;return -1;}
 if(r->sink_pixels){
  r->sink_forward=r->sink_dma&&!rooms&&getenv("POCKET_DMA_FORWARD")&&!strcmp(getenv("POCKET_DMA_FORWARD"),"1");
  if(r->last_sink_forward!=r->sink_forward)t->damage_valid=0;
  r->last_sink_forward=r->sink_forward;
 }
 if(rooms)for(unsigned i=0;i<t->n;i++){struct scene_gl_tile *q=t->tiles+i;if(!q->depth){scene_gl_bind(r,q->fbo);glGenRenderbuffers(1,&q->depth);glBindRenderbuffer(GL_RENDERBUFFER,q->depth);glRenderbufferStorage(GL_RENDERBUFFER,GL_DEPTH_COMPONENT24,q->pw,q->ph);glFramebufferRenderbuffer(GL_FRAMEBUFFER,GL_DEPTH_ATTACHMENT,GL_RENDERBUFFER,q->depth);if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE){r->target=old;return -1;}}}

 for(unsigned i=0;i<t->n&&!result;i++){
  if(!scene_gl_damaged(t,t->tiles+i))continue;
  uint64_t cpu_phase=scene_gl_cpu(r);
  r->tile_first=i;r->tile_end=i+1;r->clipped=0;
  if(t->clear_pending){scene_gl_target(r,t->tiles+i);glDisable(GL_SCISSOR_TEST);glDepthMask(GL_TRUE);glClearColor(t->clear.r/255.f,t->clear.g/255.f,t->clear.b/255.f,t->clear.a/255.f);glClear(GL_COLOR_BUFFER_BIT|(t->tiles[i].depth?GL_DEPTH_BUFFER_BIT:0));}
  size_t start=0;for(size_t j=0;j<t->count;j++)if(scene_gl_covers(t,t->commands+j,t->tiles+i))start=j;
  for(size_t j=start;j<t->count&&!result;j++){struct scene_command *c=t->commands+j;
   r->occlusion_count=0;for(size_t k=j+1;k<t->count&&r->occlusion_count<8;k++)if(scene_gl_opaque_rect(t,t->commands+k,r->occlusion+r->occlusion_count))++r->occlusion_count;
   r->translate_x=c->dx;r->translate_y=c->dy;r->clip=c->clip;r->clipped=c->clipped;r->blend=c->blend;
   result=scene_gl_geometry_now(r,c->source,c->count?t->stream+c->first:NULL,c->count,NULL,0,&c->compiled);
  }
  r->geometry_cpu_ns+=scene_gl_cpu(r)-cpu_phase;
  r->occlusion_count=0;
  if(!result&&r->sink_pixels){
   struct scene_gl_tile *q=t->tiles+i;struct mbx_surface_sink sink={0};
   if(scene_surface_begin())result=-1;
   else{
    cpu_phase=scene_gl_cpu(r);glFinish();r->finish_cpu_ns+=scene_gl_cpu(r)-cpu_phase;
    cpu_phase=scene_gl_cpu(r);
    if(glGetError()!=GL_NO_ERROR||scene_surface_end(&sink.surface))result=-1;
    else if(r->sink_deferred){
     struct mbx_surface acquired;
     if(pocket_window_acquire(r->window,&acquired))result=-1;
     else{r->sink_deferred=0;if(acquired.pixels!=r->sink_pixels||acquired.stride!=(size_t)r->sink_stride)result=-1;}
    }
    if(!result&&(sink.surface.format!=MBX_SURFACE_RGB565||sink.surface.width!=q->pw||sink.surface.height!=q->ph))result=-1;
    if(!result){
     sink.address=(uintptr_t)((char *)r->sink_pixels+q->y*r->sink_stride+q->x*2);
     sink.capacity=(uint64_t)(q->h-1)*r->sink_stride+q->w*2;sink.stride=r->sink_stride;
     sink.y=r->sink_forward?0:q->ph-q->h;sink.width=q->w;sink.height=q->h;sink.reverse_rows=!r->sink_forward;
     if(r->sink_dma){
      struct mbx_surface_dma_sink dma={.surface=sink.surface,.version=1,.fb_fd=r->sink_fd,
       .canvas_width=t->w,.canvas_height=t->h,.stride=r->sink_stride,
       .destination_x=q->x,.destination_y=q->y,.y=sink.y,.width=q->w,.height=q->h,.reverse_rows=!r->sink_forward};
      /* The destination retains the previous complete frame. Copy only the
       * intersection damaged by this frame; rendering still owns a complete
       * source image. A changed destination invalidates damage above. */
      if(t->damage_valid&&r->dma_damage){
       int x=q->x,y=q->y,xx=q->x+q->w,yy=q->y+q->h;
       if(x<t->damage.x)x=t->damage.x;
       if(y<t->damage.y)y=t->damage.y;
       if(xx>t->damage.x+t->damage.w)xx=t->damage.x+t->damage.w;
       if(yy>t->damage.y+t->damage.h)yy=t->damage.y+t->damage.h;
       if(xx<=x||yy<=y){result=-1;}
       else{dma.destination_x=x;dma.destination_y=y;dma.x=x-q->x;
        dma.y=r->sink_forward?y-q->y:q->ph-(yy-q->y);dma.width=xx-x;dma.height=yy-y;}
      }
      if(!result&&scene_surface_dma_copy(&dma))result=-1;
      else if(!result){r->dma_bytes+=(uint64_t)dma.width*dma.height*2;++r->dma_jobs;}
     }else if(scene_surface_copy(&sink))result=-1;
     else{r->sink_bytes+=(uint64_t)q->w*q->h*2;++r->sink_jobs;}
    }
    if(scene_surface_release())result=-1;
    r->sink_cpu_ns+=scene_gl_cpu(r)-cpu_phase;
   }
  }
 }
 r->translate_x=r->translate_y=0;r->target=old;r->clip=clip;r->clipped=clipped;r->blend=blend;r->tile_first=first;r->tile_end=end;
 if(result)return result;
 for(size_t j=0;j<t->count;j++){scene_geometry_free(t->commands[j].compiled);Scene_DestroyTexture(t->commands[j].source);}
 t->count=t->vertices=0;t->clear_pending=0;return 0;
}
static int Scene_RenderGeometry(Scene_Renderer *r,Scene_Texture *source,const Scene_Vertex *v,int n,const int *indices,int ni){
 if(!r||!r->target||r->target->refs!=1||n<0||n%3||indices||ni||source==r->target)return -1;
 if(source&&!source->room_region&&!source->recorded_scene&&scene_gl_flush(r,source))return -1;
 Scene_Texture *t=r->target;size_t need=t->vertices+(size_t)n;
 if(need>4*1024*1024||t->count>=65536)return -1;
 if(need>t->vertex_capacity){size_t capacity=need*2;Scene_Vertex *p=realloc(t->stream,capacity*sizeof(*p));if(!p)return -1;t->stream=p;t->vertex_capacity=capacity;}
 if(t->count==t->capacity){size_t capacity=t->capacity?t->capacity*2:16;struct scene_command *p=realloc(t->commands,capacity*sizeof(*p));if(!p)return -1;t->commands=p;t->capacity=capacity;}
 if(n)memcpy(t->stream+t->vertices,v,(size_t)n*sizeof(*v));
 ++t->revision;t->commands[t->count++]=(struct scene_command){source,t->vertices,n,r->clipped,r->clip,r->blend,0,0,NULL};t->vertices=need;if(source)++source->refs;return 0;
}
static int Scene_RenderCopy(Scene_Renderer *r,Scene_Texture *t,const Scene_Rect *src,const Scene_Rect *dst){
 if(!r||!t||src)return -1;
 if(!r->target)return 0;
 if(t->recorded_scene){if(dst||r->target->w!=t->w||r->target->h!=t->h)return -1;return Scene_RenderGeometry(r,t,NULL,0,NULL,0);}
 Scene_Rect d=dst?*dst:(Scene_Rect){0,0,(int)r->target->w,(int)r->target->h};
 for(unsigned i=0;i<(t->room_region?1:t->n);i++){struct scene_gl_tile full={.w=t->w,.h=t->h};struct scene_gl_tile *q=t->room_region?&full:t->tiles+i;Scene_Vertex v[6];const unsigned c[6]={0,1,2,0,2,3};for(unsigned j=0;j<6;j++){unsigned k=c[j];float x=q->x+((k==1||k==2)?q->w:0),y=q->y+(k>=2?q->h:0);v[j]=(Scene_Vertex){{d.x+x*d.w/t->w,d.y+y*d.h/t->h},{255,255,255,255},{x/t->w,y/t->h}};}if(Scene_RenderGeometry(r,t,v,6,NULL,0))return -1;}
 return 0;
}
static int Scene_RenderFillRect(Scene_Renderer *r,const Scene_Rect *rect){if(!r||!rect)return -1;Scene_Vertex v[6];const unsigned c[6]={0,1,2,0,2,3};for(unsigned i=0;i<6;i++)v[i]=(Scene_Vertex){{rect->x+((c[i]==1||c[i]==2)?rect->w:0),rect->y+(c[i]>=2?rect->h:0)},r->color,{0,0}};return Scene_RenderGeometry(r,NULL,v,6,NULL,0);}
static int Scene_RenderReadPixels(Scene_Renderer *r,const Scene_Rect *rect,unsigned format,void *out,int stride){
 if(!r||!r->target||r->target->room_region||r->target->recorded_scene||rect||format!=Scene_PIXELFORMAT_RGB565||!out||stride<(int)r->target->w*2)return -1;
 const char *owned=getenv("POCKET_OWNED_SINK");
 const char *dma=getenv("POCKET_DMA_SINK");int use_dma=dma&&!strcmp(dma,"1");
 if(use_dma||(owned&&!strcmp(owned,"1"))){
  if(!r->presenting||r->preserved_room||scene_surface_api()||(!r->target->count&&!r->target->clear_pending))return -1;
  if(use_dma&&(!scene_surface_dma_copy||(r->sink_fd=pocket_window_dma_fd(r->window))<0))return -1;
  r->sink_dma=use_dma;r->sink_pixels=out;r->sink_stride=stride;
  int result=scene_gl_flush(r,r->target);r->sink_pixels=NULL;r->sink_stride=0;r->sink_dma=0;r->sink_forward=0;
  return result;
 }
 if(scene_gl_flush(r,r->target))return -1;
 size_t needed=0;for(unsigned i=0;i<r->target->n;i++){size_t n=(size_t)r->target->tiles[i].pw*r->target->tiles[i].ph;if(n>needed)needed=n;}
 if(needed>800*480)return -1;
 if(needed>r->capture_capacity){uint16_t *p=realloc(r->capture_tile,needed*2);if(!p)return -1;r->capture_tile=p;r->capture_capacity=needed;}
 uint16_t *tile=r->capture_tile;const GLenum keys[]={GL_PACK_ALIGNMENT,GL_PACK_ROW_LENGTH,GL_PACK_SKIP_PIXELS,GL_PACK_SKIP_ROWS,GL_PACK_SWAP_BYTES,GL_PACK_INVERT_MESA};GLint saved[6];unsigned count=r->pack_invert?6:5;
 for(unsigned k=0;k<count;k++){glGetIntegerv(keys[k],saved+k);glPixelStorei(keys[k],k?0:2);}
 if(r->pack_invert){glPixelStorei(GL_PACK_ROW_LENGTH,stride/2);glPixelStorei(GL_PACK_INVERT_MESA,GL_TRUE);}
 for(unsigned i=0;i<r->target->n;i++){
  struct scene_gl_tile *q=r->target->tiles+i;
  if(r->presenting&&!scene_gl_damaged(r->target,q))continue;
  scene_gl_bind(r,q->fbo);
  Scene_Rect regions[4]={{q->x,q->y,q->w,q->h}};unsigned nr=1;
  if(r->presenting&&r->preserved_room){Scene_Rect keep=r->preserve_rect;int x=keep.x>(int)q->x?keep.x:(int)q->x,y=keep.y>(int)q->y?keep.y:(int)q->y;
   int xx=keep.x+keep.w<(int)(q->x+q->w)?keep.x+keep.w:(int)(q->x+q->w),yy=keep.y+keep.h<(int)(q->y+q->h)?keep.y+keep.h:(int)(q->y+q->h);
   if(xx>x&&yy>y){nr=0;
    if(y>(int)q->y)regions[nr++]=(Scene_Rect){q->x,q->y,q->w,y-q->y};
    if(yy<(int)(q->y+q->h))regions[nr++]=(Scene_Rect){q->x,yy,q->w,q->y+q->h-yy};
    if(x>(int)q->x)regions[nr++]=(Scene_Rect){q->x,y,x-q->x,yy-y};
    if(xx<(int)(q->x+q->w))regions[nr++]=(Scene_Rect){xx,y,q->x+q->w-xx,yy-y};
   }
  }
  for(unsigned j=0;j<nr;j++){Scene_Rect z=regions[j];void *destination=r->pack_invert?(char*)out+z.y*stride+z.x*2:(void*)tile;
   glReadPixels(z.x-q->x,q->ph-(z.y-q->y+z.h),z.w,z.h,GL_RGB,GL_UNSIGNED_SHORT_5_6_5,destination);++r->readback_calls;r->readback_bytes+=(uint64_t)z.w*z.h*2;
   if(!r->pack_invert)for(int y=0;y<z.h;y++)memcpy((char*)out+(z.y+y)*stride+z.x*2,tile+(z.h-1-y)*z.w,z.w*2);
  }
 }
 for(unsigned k=0;k<count;k++)glPixelStorei(keys[k],saved[k]);
 return glGetError()==GL_NO_ERROR?0:-1;
}
/* Platform presentation is supplied by the owner, never a hidden readback here. */
int pocket_window_acquire(void *,struct mbx_surface *);
int pocket_window_submit(void *);
int pocket_window_submit_region(void *,unsigned,unsigned,unsigned,unsigned);
int pocket_window_cancel(void *);
/* Reuse only an unchanged opaque Room which is the final scene command.
 * No overlay, move, clipping or camera change can pass the exact state match.
 * Pixels remain in the owned display buffer; they are never uploaded back. */
static int Scene_ReadPresented(Scene_Renderer *r,Scene_Texture *t,void *out,int stride){
 if(r->presented_target!=t||r->presented_revision!=t->revision||t->count||t->clear_pending)return 0;
 struct mbx_surface s;if(pocket_window_acquire(r->window,&s))return -1;
 if(s.width!=t->w||s.height!=t->h||stride<(int)t->w*2){pocket_window_cancel(r->window);return -1;}
 for(unsigned y=0;y<t->h;y++)memcpy((char*)out+y*stride,(char*)s.pixels+y*s.stride,t->w*2);
 return pocket_window_cancel(r->window)?-1:1;
}
static int Scene_PresentTarget(Scene_Renderer *r,Scene_Texture *target){
 if(!r||!target)return -1;
 struct mbx_surface destination;
 const char *overlap=getenv("POCKET_SCENE_OVERLAP"),*dma=getenv("POCKET_DMA_SINK");
 int deferred=overlap&&!strcmp(overlap,"1")&&dma&&!strcmp(dma,"1");
 if(deferred?pocket_window_prepare(r->window,&destination):pocket_window_acquire(r->window,&destination))return -1;
 r->sink_deferred=deferred;
 r->target=target;r->preserved_room=NULL;
 if(r->presented_target!=target||r->presented_pixels!=destination.pixels||r->presented_stride!=(int)destination.stride)target->damage_valid=0;
 Scene_Texture *room=NULL;Scene_Rect keep={0};Scene_Vertex vertices[6];float state[6];
 const char *damage=getenv("POCKET_SCENE_DAMAGE_ROOM");
 if(damage&&!strcmp(damage,"1")&&target->count){struct scene_command *last=target->commands+target->count-1;
  if(!last->clipped&&last->source&&last->source->room_region&&scene_gl_opaque_rect(target,last,&keep)){
   room=last->source;++room->refs;memcpy(vertices,target->stream+last->first,sizeof(vertices));memcpy(state,room->room_state,sizeof(state));
   if(r->previous_room_valid&&r->previous_room_draw==room->room_region&&r->previous_room_eye==room->room_eye&&r->previous_room_width==room->w&&r->previous_room_height==room->h&&
      !memcmp(vertices,r->previous_room_vertices,sizeof(vertices))&&!memcmp(state,r->previous_room_state,sizeof(state))&&!last->clipped){r->preserved_room=room;r->preserve_rect=keep;}
  }
 }
 r->presenting=1;uint64_t reads=r->readback_bytes+r->sink_bytes+r->dma_bytes;
 if(destination.width!=target->w||destination.height!=target->h||
    Scene_RenderReadPixels(r,NULL,Scene_PIXELFORMAT_RGB565,destination.pixels,destination.stride)){
  r->presenting=0;r->preserved_room=NULL;r->previous_room_valid=0;r->presented_target=NULL;if(!r->sink_deferred)pocket_window_cancel(r->window);r->sink_deferred=0;if(room)Scene_DestroyTexture(room);return -1;
 }
 if(r->sink_deferred){r->sink_deferred=0;r->presenting=0;if(room)Scene_DestroyTexture(room);return -1;}
 const char *partial=getenv("POCKET_SCENE_PARTIAL");
 Scene_Rect region=target->damage_valid?target->damage:(Scene_Rect){0,0,target->w,target->h};
 if(partial&&!strcmp(partial,"0"))region=(Scene_Rect){0,0,target->w,target->h};
 int result=pocket_window_submit_region(r->window,region.x,region.y,region.w,region.h);r->presenting=0;
 if(!result){r->presentation_bytes+=r->readback_bytes+r->sink_bytes+r->dma_bytes-reads;r->presented_target=target;r->presented_revision=target->revision;r->presented_pixels=destination.pixels;r->presented_stride=destination.stride;
  if(r->preserved_room)++r->preserved_frames;
  r->previous_room_valid=room!=NULL;
  if(room){memcpy(r->previous_room_vertices,vertices,sizeof(vertices));memcpy(r->previous_room_state,state,sizeof(state));r->previous_room_width=room->w;r->previous_room_height=room->h;r->previous_room_draw=room->room_region;r->previous_room_eye=room->room_eye;}
 }else{r->previous_room_valid=0;r->presented_target=NULL;}
 r->preserved_room=NULL;if(room)Scene_DestroyTexture(room);return result;
}
#endif
