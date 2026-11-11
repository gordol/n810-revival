/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include <math.h>
#include <stdint.h>
#include <string.h>
#ifdef POCKET_SCENE_GL
#include "scene_backend_gl.h"
#include "../driver/mbx/common/mbx_window_export.h"
#else
#include "scene_backend_sdl.h"
#endif
struct scene_texture {Scene_Texture *texture;unsigned width,height;int image_cache,x,y;unsigned replays;};
struct scene_mark {uint32_t index,glyph;uint64_t ink;};
struct scene_text_run {Scene_Texture *texture;unsigned count;uint32_t text[128];};
struct gpu_scene {
 uint32_t *font_pixels;struct scene_text_run runs[32];unsigned next_run;uint64_t run_hits,run_builds,run_bytes;
 struct window *window;Scene_Renderer *device;Scene_Texture *base,*canvas,*font;uint32_t *codes;Scene_Rect *glyph_rects;
 unsigned width,height,count,atlas_width,atlas_height;Scene_Vertex *vertices;size_t capacity;
 uint64_t frames,map_builds,line_segments,readbacks,uploads;
 Scene_Vertex *flux_vertices;size_t flux_capacity;unsigned flux_count;double flux_key[6];int flux_valid;uint64_t flux_builds,flux_replays,flux_control_points;
#ifdef POCKET_SCENE_GL
 size_t batch_commands,batch_vertices;int batch_active;
 int (*room_draw)(float,float,float,float,float,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,int);
 Scene_RoomRegion room_region;
 int (*room_eye)(float);
 unsigned window_budget;int window_budget_ready;
#endif
};
static Scene_Color scene_rgb(uint32_t v){return (Scene_Color){(v>>16)&255,(v>>8)&255,v&255,255};}
static uint32_t scene_565(uint32_t v){return (((((v>>11)&31)*255+15)/31)<<16)|(((((v>>5)&63)*255+31)/63)<<8)|(((v&31)*255+15)/31);}
static int scene_target(struct gpu_scene *s,Scene_Texture *target){
 if(Scene_SetRenderTarget(s->device,target)||Scene_RenderSetLogicalSize(s->device,0,0)||Scene_RenderSetScale(s->device,1,1)||Scene_RenderSetViewport(s->device,NULL)||Scene_RenderSetClipRect(s->device,NULL))return -1;
 return 0;
}
static int scene_capacity(struct gpu_scene *s,size_t n){
 if(n>6000000)return -1;
 if(n<=s->capacity)return 0;
 Scene_Vertex *v=realloc(s->vertices,n*sizeof(*v));if(!v)return -1;s->vertices=v;s->capacity=n;return 0;
}
static void scene_quad(Scene_Vertex *v,float x,float y,float w,float h,Scene_Color color,float u,float t,float uw,float th){
 const unsigned corner[6]={0,1,2,0,2,3};for(unsigned i=0;i<6;i++){unsigned c=corner[i];v[i].position=(Scene_FPoint){x+((c==1||c==2)?w:0),y+(c>=2?h:0)};v[i].color=color;v[i].tex_coord=(Scene_FPoint){u+((c==1||c==2)?uw:0),t+(c>=2?th:0)};}
}
static int scene_glyph(struct gpu_scene *s,uint32_t code){unsigned lo=0,hi=s->count;while(lo<hi){unsigned m=(lo+hi)/2;if(s->codes[m]<code)lo=m+1;else hi=m;}return lo<s->count&&s->codes[lo]==code?(int)lo:-1;}
static void scene_glyph_quad(struct gpu_scene *s,Scene_Vertex *v,int at,float x,float y,Scene_Color color){unsigned columns=s->atlas_width/8,gx=(unsigned)at%columns*8,gy=(unsigned)at/columns*16;scene_quad(v,x,y,8,16,color,(float)gx/s->atlas_width,(float)gy/s->atlas_height,8.f/s->atlas_width,16.f/s->atlas_height);}
void *pocket_scene_open(void *window,int require_gpu){
 if(!window)return NULL;
 struct window *w=window;Scene_Renderer *device=scene_device(window);Scene_RendererInfo info;if(!device)return NULL;if(Scene_GetRendererInfo(device,&info)){scene_device_close(device);return NULL;}
 if(require_gpu&&!(info.flags&Scene_RENDERER_ACCELERATED)){Scene_SetError("Accelerated native scene renderer required");scene_device_close(device);return NULL;}
 struct gpu_scene *s=calloc(1,sizeof(*s));if(s){s->window=w;s->device=device;}else scene_device_close(device);return s;
}
const char *pocket_scene_backend(void *ptr){struct gpu_scene *s=ptr;Scene_RendererInfo i;if(!s||Scene_GetRendererInfo(s->device,&i))return "unavailable";return i.name;}
int pocket_scene_font(void *ptr,const uint32_t *codes,const unsigned char *bits,unsigned count,const uint32_t *aa_codes,const unsigned char *coverage,unsigned aa_count){
 struct gpu_scene *s=ptr;if(!s||!codes||!bits||!count||count>32768)return -1;unsigned columns=16;while(((count+columns-1)/columns)*16>4096)columns*=2;s->atlas_width=columns*8;s->atlas_height=((count+columns-1)/columns)*16;
 size_t n=(size_t)s->atlas_width*s->atlas_height;uint32_t *pixels=calloc(n,4);if(!pixels)return -1;
 for(unsigned i=0;i<count;i++){int aa=-1;for(unsigned k=0;k<aa_count;k++)if(aa_codes[k]==codes[i]){aa=(int)k;break;}
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<8;x++){unsigned alpha=aa>=0?coverage[(unsigned)aa*128+y*8+x]:(bits[i*16+y]&(128>>x)?255:0);pixels[((i/columns)*16+y)*s->atlas_width+(i%columns)*8+x]=0xffffffu|(alpha<<24);}}
 /* Prove rectangle glyphs from actual coverage, not Unicode assumptions.
  * Exact opaque blocks need no sampler; antialiased/irregular glyphs retain
  * the atlas path. This applies equally to both native scene backends. */
 Scene_Rect *rects=calloc(count,sizeof(*rects));if(!rects){free(pixels);return -1;}
 for(unsigned i=0;i<count;i++){unsigned left=8,top=16,right=0,bottom=0,filled=0;int opaque=1;
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<8;x++){unsigned alpha=pixels[((i/columns)*16+y)*s->atlas_width+(i%columns)*8+x]>>24;
   if(alpha&&alpha!=255)opaque=0;
   if(alpha){if(x<left)left=x;if(y<top)top=y;if(x+1>right)right=x+1;if(y+1>bottom)bottom=y+1;filled++;}
  }
  if(opaque&&filled&&filled==(right-left)*(bottom-top))rects[i]=(Scene_Rect){left,top,right-left,bottom-top};
 }
 Scene_Texture *font=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_STATIC,s->atlas_width,s->atlas_height);
 int result=font?Scene_UpdateTexture(font,NULL,pixels,s->atlas_width*4):-1;if(result){free(pixels);free(rects);if(font)Scene_DestroyTexture(font);return -1;}Scene_SetTextureBlendMode(font,Scene_BLENDMODE_BLEND);Scene_SetTextureScaleMode(font,Scene_ScaleModeNearest);
 uint32_t *copy=malloc(count*4);if(!copy){free(pixels);free(rects);Scene_DestroyTexture(font);return -1;}
 for(unsigned i=0;i<32;i++){if(s->runs[i].texture)Scene_DestroyTexture(s->runs[i].texture);memset(s->runs+i,0,sizeof(s->runs[i]));}
 free(s->font_pixels);s->font_pixels=NULL;
 if(getenv("POCKET_SCENE_TEXT_RUNS")&&!strcmp(getenv("POCKET_SCENE_TEXT_RUNS"),"1"))s->font_pixels=pixels;else free(pixels);
 memcpy(copy,codes,count*4);free(s->codes);free(s->glyph_rects);s->glyph_rects=rects;s->codes=copy;s->count=count;if(s->font)Scene_DestroyTexture(s->font);s->font=font;s->uploads+=n*4;return 0;
}
int pocket_scene_size(void *ptr,unsigned width,unsigned height){
 struct gpu_scene *s=ptr;if(!s||!width||!height||width>4096||height>4096)return -1;if(width==s->width&&height==s->height)return 0;
 unsigned format=Scene_PIXELFORMAT_ABGR8888;
#ifdef POCKET_SCENE_GL
 const char *opaque=getenv("POCKET_SCENE_OPAQUE_TARGETS");if(opaque&&!strcmp(opaque,"1"))format=Scene_PIXELFORMAT_RGB565;
#endif
 Scene_Texture *base=NULL,*canvas=Scene_CreateTexture(s->device,format,Scene_TEXTUREACCESS_TARGET,width,height);
#ifdef POCKET_SCENE_GL
 const char *recorded=getenv("POCKET_SCENE_DIRECT_BASE");
 if(recorded&&!strcmp(recorded,"1")){base=calloc(1,sizeof(*base));if(base){base->w=width;base->h=height;base->refs=1;base->format=format;base->recorded_scene=1;}}
 else
#endif
 base=Scene_CreateTexture(s->device,format,Scene_TEXTUREACCESS_TARGET,width,height);
 if(!base||!canvas){if(base)Scene_DestroyTexture(base);if(canvas)Scene_DestroyTexture(canvas);return -1;}
#ifdef POCKET_SCENE_GL
 s->device->presented_target=NULL;s->device->previous_room_valid=0;
#endif
 if(s->base){Scene_DestroyTexture(s->base);}if(s->canvas){Scene_DestroyTexture(s->canvas);}s->base=base;s->canvas=canvas;s->width=width;s->height=height;return 0;
}
/* Pixel-native entry points: layout coordinates and glyph runs, never a
 * full-screen cell plane. Both the SDL and MBX backends consume these commands. */
int pocket_scene_begin_pixels(void *ptr,uint32_t rgb){
 struct gpu_scene *s=ptr;if(!s||!s->canvas||scene_target(s,s->canvas))return -1;
 Scene_Color c=scene_rgb(rgb);
 return Scene_SetRenderDrawColor(s->device,c.r,c.g,c.b,255)||Scene_RenderClear(s->device)?-1:0;
}
/* Damage bounds select whole output tiles, not scissored blending. Each
 * selected tile is rebuilt from the complete scene, including old locations,
 * shadows and translucent layers. Other tiles retain their existing pixels. */
int pocket_scene_damage(void *ptr,int x,int y,unsigned width,unsigned height){
 struct gpu_scene *s=ptr;if(!s||!s->canvas||width>s->width||height>s->height||x<0||y<0||(unsigned)x>s->width||(unsigned)y>s->height||width>s->width-(unsigned)x||height>s->height-(unsigned)y)return -1;
#ifdef POCKET_SCENE_GL
 s->canvas->damage=(Scene_Rect){x,y,width,height};s->canvas->damage_valid=1;
#else
 (void)x;(void)y; /* SDL retains the full-frame path. */
#endif
 return 0;
}
/* Retain the existing native command representation for one unchanged
 * window/background/panel. No texture materialization or pixel copy. */
int pocket_scene_batch_supported(void){
#ifdef POCKET_SCENE_GL
 return 1;
#else
 return 0;
#endif
}
int pocket_scene_batch_begin(void *ptr){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;if(!s||!s->canvas||s->batch_active)return -1;
 s->batch_commands=s->canvas->count;s->batch_vertices=s->canvas->vertices;s->batch_active=1;return 0;
#else
 (void)ptr;return -1;
#endif
}
void *pocket_scene_batch_end(void *ptr){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;if(!s||!s->batch_active)return NULL;Scene_Texture *t=s->canvas;
 size_t count=t->count-s->batch_commands,n=t->vertices-s->batch_vertices;
 struct scene_texture *image=calloc(1,sizeof(*image));Scene_Texture *batch=calloc(1,sizeof(*batch));
 if(!image||!batch){free(image);free(batch);return NULL;}
 batch->commands=malloc((count?count:1)*sizeof(*batch->commands));batch->stream=malloc((n?n:1)*sizeof(*batch->stream));
 if(!batch->commands||!batch->stream){free(batch->commands);free(batch->stream);free(batch);free(image);return NULL;}
 if(count)memcpy(batch->commands,t->commands+s->batch_commands,count*sizeof(*batch->commands));
 if(n)memcpy(batch->stream,t->stream+s->batch_vertices,n*sizeof(*batch->stream));
 for(size_t i=0;i<count;i++)batch->commands[i].first-=s->batch_vertices;
 batch->refs=1;batch->recorded_scene=1;batch->w=s->width;batch->h=s->height;batch->count=batch->capacity=count;batch->vertices=batch->vertex_capacity=n;
 scene_recorded_bounds(batch);
 image->texture=batch;image->width=s->width;image->height=s->height;
 /* Transfer the commands' source references, rather than duplicating them. */
 t->count=s->batch_commands;t->vertices=s->batch_vertices;s->batch_active=0;return image;
#else
 (void)ptr;return NULL;
#endif
}
int pocket_scene_batch_abort(void *ptr){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;if(!s||!s->batch_active)return -1;
 for(size_t i=s->batch_commands;i<s->canvas->count;i++){free(s->canvas->commands[i].compiled);Scene_DestroyTexture(s->canvas->commands[i].source);}
 s->canvas->count=s->batch_commands;s->canvas->vertices=s->batch_vertices;s->batch_active=0;return 0;
#else
 (void)ptr;return -1;
#endif
}
#ifdef POCKET_SCENE_GL
static unsigned scene_window_budget(struct gpu_scene *s){
 if(s->window_budget_ready)return s->window_budget;
 s->window_budget_ready=1;
 int (*layout_query)(struct mbx_window_layout *)=(int (*)(struct mbx_window_layout *))dlsym(RTLD_DEFAULT,"n810_mbx_window_get_layout");
 struct mbx_window_layout layout;
 if(!layout_query||layout_query(&layout)||!mbx_window_layout_valid(&layout))return 0;
 const char *f=getenv("N810_MBX_WINDOW_FIRST"),*n=getenv("N810_MBX_WINDOW_COUNT");
 unsigned first=f?(unsigned)strtoul(f,NULL,10):0,count=n?(unsigned)strtoul(n,NULL,10):14;
 if(!mbx_window_range_valid(first,count))return 0;
 for(unsigned i=first;i<first+count;i++)
  if((layout.client_mask&(1U<<i))&&!(layout.native_mask&(1U<<i)))++s->window_budget;
 return s->window_budget;
}
static void scene_window_image_admit(struct gpu_scene *s,struct scene_texture *image){
 if(image->image_cache||!image->texture->recorded_scene||image->texture->refs!=1)return;
 const char *warm=getenv("POCKET_SCENE_WINDOW_WARMUP");unsigned threshold=warm?(unsigned)strtoul(warm,NULL,10):8;
 if(image->replays++<threshold)return;
 Scene_Texture *batch=image->texture;size_t n=batch->vertices,count=batch->count;
 const char *cached=getenv("POCKET_SCENE_WINDOW_IMAGES");
 if(n&&cached&&!strcmp(cached,"1")){
  if(!batch->bounds_valid)return;
  float left=batch->bounds[0],top=batch->bounds[1],right=batch->bounds[2],bottom=batch->bounds[3];int eligible=1;
  int x=(int)floorf(left),y=(int)floorf(top),w=(int)ceilf(right)-x,h=(int)ceilf(bottom)-y;
  unsigned pages=w>0&&h>0?((unsigned)w+127)/128*(((unsigned)h+127)/128):0;
  /* Small window images only. Large/background batches retain geometry;
   * leave the two driver scratch images outside this budget. */
  const char *wide=getenv("POCKET_SCENE_WIDE_CACHE");unsigned max_pages=wide&&!strcmp(wide,"1")?8:4;
  if(eligible&&pages&&pages<=max_pages&&s->device->window_pages+pages<=scene_window_budget(s)){
   Scene_Texture *pixels=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_TARGET,w,h);
   if(!pixels)return;
   pixels->commands=batch->commands;pixels->count=pixels->capacity=count;pixels->stream=batch->stream;pixels->vertices=pixels->vertex_capacity=n;
   for(size_t i=0;i<n;i++){pixels->stream[i].position.x-=x;pixels->stream[i].position.y-=y;}
   for(size_t i=0;i<count;i++){scene_geometry_free(pixels->commands[i].compiled);pixels->commands[i].compiled=NULL;pixels->commands[i].clip.x-=x;pixels->commands[i].clip.y-=y;}
   pixels->blend=Scene_BLENDMODE_PREMULT;pixels->cache_owner=s->device;pixels->cache_pages=pages;s->device->window_pages+=pages;
   free(batch);image->texture=pixels;image->image_cache=1;image->x=x;image->y=y;
  }
 }
 }
#endif
int pocket_scene_batch_replay(void *ptr,void *batch){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;struct scene_texture *image=batch;
 if(!s||!image||!image->texture||image->width!=s->width||image->height!=s->height||scene_target(s,s->canvas))return -1;
 scene_window_image_admit(s,image);
 if(image->image_cache){Scene_Rect dst={image->x,image->y,image->texture->w,image->texture->h};return Scene_RenderCopy(s->device,image->texture,NULL,&dst);}
 if(!image->texture->recorded_scene)return -1;
 return Scene_RenderCopy(s->device,image->texture,NULL,NULL);
#else
 (void)ptr;(void)batch;return -1;
#endif
}
/* Move retained window geometry with a GPU model-view translation. */
int pocket_scene_batch_replay_offset(void *ptr,void *batch,int dx,int dy){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;struct scene_texture *image=batch;
 if(!s||!image||!image->texture||dx<-8192||dx>8192||dy<-8192||dy>8192)return -1;
 scene_window_image_admit(s,image);
 if(image->image_cache){if(scene_target(s,s->canvas))return -1;Scene_Rect dst={image->x+dx,image->y+dy,image->texture->w,image->texture->h};return Scene_RenderCopy(s->device,image->texture,NULL,&dst);}
 if(!image->texture->recorded_scene)return -1;
 for(size_t i=0;i<image->texture->count;i++){Scene_Texture *q=image->texture->commands[i].source;if(q&&(q->room_region||q->recorded_scene))return -1;}
 if(scene_target(s,s->canvas)||Scene_RenderCopy(s->device,image->texture,NULL,NULL))return -1;
 struct scene_command *c=s->canvas->commands+s->canvas->count-1;c->dx=dx;c->dy=dy;return 0;
#else
 (void)ptr;(void)batch;(void)dx;(void)dy;return -1;
#endif
}
int pocket_scene_index_bounds(const uint32_t *indices,unsigned count,unsigned width,unsigned height,uint32_t *bounds){
 if(!bounds||!width||!height||width>4096||height>4096||count>width*height||(count&&!indices))return -1;
 unsigned left=width,top=height,right=0,bottom=0;
 for(unsigned i=0;i<count;i++){unsigned n=indices[i];if(n>=width*height)return -1;unsigned x=n%width,y=n/width;if(x<left)left=x;if(y<top)top=y;if(x+1>right)right=x+1;if(y+1>bottom)bottom=y+1;}
 bounds[0]=count?left:0;bounds[1]=count?top:0;bounds[2]=count?right-left:0;bounds[3]=count?bottom-top:0;return 0;
}
int pocket_scene_rect(void *ptr,float x,float y,float width,float height,uint32_t rgba){
 struct gpu_scene *s=ptr;if(!s||!isfinite(x)||!isfinite(y)||!isfinite(width)||!isfinite(height)||width<0||height<0||scene_target(s,s->canvas)||scene_capacity(s,6))return -1;
 Scene_Color c=scene_rgb(rgba>>8);c.a=rgba&255;
 scene_quad(s->vertices,x,y,width,height,c,0,0,0,0);
 if(Scene_SetRenderDrawBlendMode(s->device,c.a==255?Scene_BLENDMODE_NONE:Scene_BLENDMODE_BLEND))return -1;
 return Scene_RenderGeometry(s->device,NULL,s->vertices,6,NULL,0);
}
/* Immutable glyph-run sources. Copy the installed coverage only when the
 * text changes; GPU sampling/blending still performs composition. Cache keys
 * compare every code point and are reset when the font changes. */
static int scene_text_run(struct gpu_scene *s,float x,float y,const uint32_t *text,unsigned count,Scene_Color color){
 if(!s->font_pixels||count>128)return -1;
 while(count&&text[0]==32){++text;--count;x+=8;}
 while(count&&text[count-1]==32)--count;
 if(!count)return 0;
 struct scene_text_run *run=NULL;
 for(unsigned i=0;i<32;i++)if(s->runs[i].texture&&s->runs[i].count==count&&!memcmp(s->runs[i].text,text,count*4)){run=s->runs+i;++s->run_hits;break;}
 /* Power-of-two normalization keeps 128-pixel page boundaries exact in
  * float. Arbitrary widths can round a boundary slightly below zero after
  * page rebasing; the strict MBX sampler correctly rejects that stream. */
 unsigned width=count*8,texture_width=1;while(texture_width<width)texture_width*=2;
 if(!run){
  uint32_t *pixels=malloc((size_t)texture_width*16*4);if(!pixels)return -1;
  for(unsigned i=0;i<texture_width*16;i++)pixels[i]=0x00ffffff;
  for(unsigned i=0;i<count;i++){if(text[i]==32)continue;int at=scene_glyph(s,text[i]);if(at<0){free(pixels);return -1;}
   unsigned columns=s->atlas_width/8,gx=(unsigned)at%columns*8,gy=(unsigned)at/columns*16;
   for(unsigned row=0;row<16;row++)memcpy(pixels+row*texture_width+i*8,s->font_pixels+(gy+row)*s->atlas_width+gx,8*4);
  }
  Scene_Texture *texture=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_STATIC,texture_width,16);
  int error=texture?Scene_UpdateTexture(texture,NULL,pixels,texture_width*4):-1;free(pixels);if(error){if(texture)Scene_DestroyTexture(texture);return -1;}
  Scene_SetTextureBlendMode(texture,Scene_BLENDMODE_BLEND);Scene_SetTextureScaleMode(texture,Scene_ScaleModeNearest);
  run=s->runs+s->next_run;s->next_run=(s->next_run+1)%32;
  if(run->texture)Scene_DestroyTexture(run->texture);
  run->texture=texture;run->count=count;memcpy(run->text,text,count*4);++s->run_builds;s->run_bytes+=(uint64_t)texture_width*16*4;
 }
 Scene_Vertex vertices[8*6];unsigned n=0;
 /* Split at the backend's established 128-pixel source-page boundaries. */
 for(unsigned left=0;left<width;left+=128){unsigned w=width-left<128?width-left:128;
  scene_quad(vertices+n*6,x+left,y,w,16,color,(float)left/texture_width,0,(float)w/texture_width,1);++n;
 }
 return Scene_RenderGeometry(s->device,run->texture,vertices,n*6,NULL,0);
}
int pocket_scene_text(void *ptr,float x,float y,const uint32_t *text,unsigned count,uint32_t rgb){
 struct gpu_scene *s=ptr;if(!s||!text||count>65536||!isfinite(x)||!isfinite(y)||scene_capacity(s,(size_t)count*6)||scene_target(s,s->canvas))return -1;
 unsigned n=0;Scene_Color color=scene_rgb(rgb);
 if(s->font_pixels){for(unsigned i=0;i<count;i+=128){unsigned run=count-i<128?count-i:128;if(scene_text_run(s,x+i*8,y,text+i,run,color))return -1;}return 0;}
 for(unsigned i=0;i<count;i++){if(text[i]==32)continue;int at=scene_glyph(s,text[i]);if(at<0)return -1;scene_glyph_quad(s,s->vertices+n*6,at,x+i*8,y,color);n++;}
 return n?Scene_RenderGeometry(s->device,s->font,s->vertices,(int)n*6,NULL,0):0;
}
/* A pixel Flux scene keeps the Clifford sample budget and controls. CPU
 * work is bounded attractor control points; the GPU draws continuous paths
 * and interpolated glow. No glyph density grid or cell framebuffer exists. */
int pocket_scene_flux_pixels(void *ptr,double step,double density,double glow,unsigned arms){
 struct gpu_scene *s=ptr;if(!s||!isfinite(step)||!isfinite(density)||!isfinite(glow)||density<.5||density>4||glow<0||glow>1||arms>4)return -1;
 double key[6]={step,density,glow,arms,s->width,s->height};
 if(scene_target(s,s->canvas)||Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_BLEND))return -1;
 if(s->flux_valid&&!memcmp(key,s->flux_key,sizeof(key))){++s->flux_replays;return Scene_RenderGeometry(s->device,NULL,s->flux_vertices,(int)s->flux_count,NULL,0);}
 unsigned budget=s->width/8*(s->height/16)/8;if(budget<64)budget=64;if(budget>768)budget=768;budget=(unsigned)lrint(budget*density);
 if(scene_capacity(s,(size_t)budget*30)||scene_target(s,s->canvas)||Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_BLEND))return -1;
 double t=step/90,a=-1.4+.12*sin(t),b=1.6,c=1+.15*cos(t*.7),d=.7,x=.1,y=.1;unsigned n=0;
 for(unsigned i=0;i<budget+32;i++){
  double xx=sin(a*y)+c*cos(a*x),yy=sin(b*x)+d*cos(b*y);x=xx;y=yy;if(i<32)continue;
  float px=(x+2.2)/4.4*s->width,py=(y+2)/4*s->height;
  double phase=(x+2.2)/4.4*2.4+(y+2)/4*1.7+t*.12;
  Scene_Color color={(uint8_t)(65+85*(.5+.5*sin(phase))),(uint8_t)(65+85*(.5+.5*sin(phase+2.1))),(uint8_t)(65+85*(.5+.5*sin(phase+4.2))),255};
  if(glow>0){
   float radius=2+8*glow;Scene_Color center=color;center.a=(uint8_t)(glow*180);Scene_Color edge=color;edge.a=0;
   Scene_FPoint corner[4]={{px-radius,py-radius},{px+radius,py-radius},{px+radius,py+radius},{px-radius,py+radius}};
   for(unsigned k=0;k<4;k++){s->vertices[n++]=(Scene_Vertex){{px,py},center,{0,0}};s->vertices[n++]=(Scene_Vertex){corner[k],edge,{0,0}};s->vertices[n++]=(Scene_Vertex){corner[(k+1)%4],edge,{0,0}};}
  }
  if(arms){
   double angle=sin((x+2.2)/4.4*5+t*.3)+(y+2)/4*3;float dx=cos(angle)*arms*3,dy=sin(angle)*arms*3;
   Scene_FPoint tail[4]={{px-.5f,py-.5f},{px+.5f,py+.5f},{px-dx+.5f,py-dy+.5f},{px-dx-.5f,py-dy-.5f}};
   const unsigned order[6]={0,1,2,0,2,3};for(unsigned k=0;k<6;k++){Scene_Color fade=color;if(order[k]>=2)fade.a=0;s->vertices[n++]=(Scene_Vertex){tail[order[k]],fade,{0,0}};}
  }
  scene_quad(s->vertices+n,px-1,py-1,2,2,color,0,0,0,0);n+=6;
 }
 if(n>s->flux_capacity){Scene_Vertex *next=realloc(s->flux_vertices,(size_t)n*sizeof(*next));if(!next)return -1;s->flux_vertices=next;s->flux_capacity=n;}
 memcpy(s->flux_vertices,s->vertices,(size_t)n*sizeof(*s->vertices));memcpy(s->flux_key,key,sizeof(key));s->flux_count=n;s->flux_valid=1;++s->flux_builds;s->flux_control_points+=budget+32;
 return n?Scene_RenderGeometry(s->device,NULL,s->flux_vertices,(int)n,NULL,0):0;
}
int pocket_scene_pixel_stats(void *ptr,uint64_t out[3]){struct gpu_scene *s=ptr;if(!s||!out)return -1;out[0]=s->flux_builds;out[1]=s->flux_replays;out[2]=s->flux_control_points;return 0;}
int pocket_scene_cells(void *ptr,const uint32_t *cells,unsigned cols,unsigned rows,int defer){
 struct gpu_scene *s=ptr;size_t count=(size_t)cols*rows;if(!s||!cells||cols*8!=s->width||rows*16!=s->height||!s->font||scene_capacity(s,count*6)||scene_target(s,s->base))return -1;
#ifdef POCKET_SCENE_GL
 if(Scene_SetRenderDrawColor(s->device,0,0,0,255)||Scene_RenderClear(s->device))return -1;
#endif
 if(Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_NONE))return -1;
 unsigned n=0;
 for(size_t i=0;i<count;){unsigned run=1,color=cells[i*2+1]>>16;
  while(i+run<count&&(i+run)%cols&&(cells[(i+run)*2+1]>>16)==color)run++;
  scene_quad(s->vertices+n++*6,(float)(i%cols)*8,(float)(i/cols)*16,run*8,16,scene_rgb(scene_565(color)),0,0,0,0);i+=run;
 }
 if(n&&Scene_RenderGeometry(s->device,NULL,s->vertices,(int)(n*6),NULL,0))return -1;
 n=0;
 for(size_t i=0;i<count;i++){uint32_t code=cells[i*2];if(code==32||(defer&&code>=32&&code<127))continue;int at=scene_glyph(s,code);if(at<0)return -1;Scene_Rect q=s->glyph_rects[at];if(!q.w)continue;
  unsigned run=1,color=cells[i*2+1]&65535;
  if(q.x==0&&q.w==8)while(i+run<count&&(i+run)%cols&&cells[(i+run)*2]==code&&(cells[(i+run)*2+1]&65535)==color)run++;
  scene_quad(s->vertices+n++*6,(float)(i%cols)*8+q.x,(float)(i/cols)*16+q.y,q.w*run,q.h,scene_rgb(scene_565(color)),0,0,0,0);i+=run-1;
 }
 if(n&&Scene_RenderGeometry(s->device,NULL,s->vertices,(int)(n*6),NULL,0))return -1;
 n=0;
 for(size_t i=0;i<count;i++){uint32_t code=cells[i*2];if(code==32||(defer&&code>=32&&code<127))continue;int at=scene_glyph(s,code);if(at<0)return -1;if(s->glyph_rects[at].w)continue;scene_glyph_quad(s,s->vertices+n*6,at,(float)(i%cols)*8,(float)(i/cols)*16,scene_rgb(scene_565(cells[i*2+1]&65535)));n++;}
 return n?Scene_RenderGeometry(s->device,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_begin(void *ptr){struct gpu_scene *s=ptr;if(!s||scene_target(s,s->canvas))return -1;
#ifdef POCKET_SCENE_GL
 if(Scene_SetRenderDrawColor(s->device,0,0,0,255)||Scene_RenderClear(s->device))return -1;
#endif
 return Scene_RenderCopy(s->device,s->base,NULL,NULL);
}
void *pocket_scene_map(void *ptr,const uint32_t *colors,unsigned cols,unsigned rows,unsigned sample_width,unsigned sample_height){
 struct gpu_scene *s=ptr;if(!s||!colors||!cols||!rows||cols>512||rows>256||!sample_width||!sample_height||sample_width>4096||sample_height>4096)return NULL;struct scene_texture *image=calloc(1,sizeof(*image));if(!image)return NULL;image->width=cols*8;image->height=rows*16;
 image->texture=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_TARGET,image->width,image->height);Scene_Texture *samples=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_STATIC,sample_width,sample_height);
 uint32_t *rgba=malloc((size_t)sample_width*sample_height*4);if(!image->texture||!samples||!rgba)goto fail;
 for(size_t i=0;i<(size_t)sample_width*sample_height;i++){uint32_t c=colors[i];rgba[i]=((c&255)<<16)|(c&0xff00)|((c>>16)&255)|0xff000000u;}
 if(Scene_UpdateTexture(samples,NULL,rgba,sample_width*4)||Scene_SetTextureScaleMode(samples,Scene_ScaleModeNearest)||scene_target(s,image->texture)||Scene_RenderCopy(s->device,samples,NULL,NULL))goto fail;
 free(rgba);Scene_DestroyTexture(samples);s->uploads+=(uint64_t)sample_width*sample_height*4;s->map_builds++;return image;
 fail:free(rgba);if(samples)Scene_DestroyTexture(samples);if(image->texture)Scene_DestroyTexture(image->texture);free(image);return NULL;
}
static int scene_clip(double *x,double *y,double *xx,double *yy,unsigned w,unsigned h){
 double dx=*xx-*x,dy=*yy-*y,low=0,high=1,p[4]={-dx,dx,-dy,dy},q[4]={*x,w-*x,*y,h-*y};
 for(unsigned i=0;i<4;i++){if(!p[i]){if(q[i]<0)return 0;continue;}double t=q[i]/p[i];if(p[i]<0){if(t>high)return 0;if(t>low)low=t;}else{if(t<low)return 0;if(t<high)high=t;}}
 *xx=*x+high*dx;*yy=*y+high*dy;*x+=low*dx;*y+=low*dy;return 1;
}
int pocket_scene_lines(void *ptr,void *target,const double *points,unsigned count,uint32_t color){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||count>250000||(count&&!points)||scene_capacity(s,(size_t)count*6)||scene_target(s,image->texture))return -1;
 unsigned n=0;
 for(unsigned i=0;i<count;i++){double x=points[i*4],y=points[i*4+1],xx=points[i*4+2],yy=points[i*4+3];if(!isfinite(x)||!isfinite(y)||!isfinite(xx)||!isfinite(yy))return -1;if(!scene_clip(&x,&y,&xx,&yy,image->width,image->height))continue;
  double dx=xx-x,dy=yy-y,length=hypot(dx,dy);if(length<1e-9){scene_quad(s->vertices+n*6,(float)x-.5f,(float)y-.5f,1,1,scene_rgb(color),0,0,0,0);n++;continue;}
  float nx=(float)(-.5*dy/length),ny=(float)(.5*dx/length),tx=(float)(.5*dx/length),ty=(float)(.5*dy/length);Scene_FPoint corners[4]={{(float)x-tx+nx,(float)y-ty+ny},{(float)xx+tx+nx,(float)yy+ty+ny},{(float)xx+tx-nx,(float)yy+ty-ny},{(float)x-tx-nx,(float)y-ty-ny}};const unsigned order[6]={0,1,2,0,2,3};
  for(unsigned k=0;k<6;k++)s->vertices[n*6+k]=(Scene_Vertex){corners[order[k]],scene_rgb(color),{0,0}};
  n++;}
 s->line_segments+=n;return n?Scene_RenderGeometry(s->device,NULL,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_marks(void *ptr,void *target,const struct scene_mark *marks,unsigned count,int defer){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||(count&&!marks)||scene_capacity(s,(size_t)count*6)||scene_target(s,image->texture))return -1;unsigned cols=image->width/8,rows=image->height/16;
 for(unsigned i=0;i<count;i++){if(marks[i].index>=cols*rows)return -1;scene_quad(s->vertices+i*6,(marks[i].index%cols)*8,(marks[i].index/cols)*16,8,16,scene_rgb((uint32_t)marks[i].ink&0xffffff),0,0,0,0);}
 if(count&&Scene_RenderGeometry(s->device,NULL,s->vertices,(int)(count*6),NULL,0))return -1;
 unsigned n=0;
 for(unsigned i=0;i<count;i++){uint32_t ch=marks[i].glyph;if(ch==32||(defer&&ch>=32&&ch<127))continue;int at=scene_glyph(s,ch);if(at<0)return -1;scene_glyph_quad(s,s->vertices+n*6,at,(marks[i].index%cols)*8,(marks[i].index/cols)*16,scene_rgb((uint32_t)(marks[i].ink>>24)&0xffffff));n++;}
 return n?Scene_RenderGeometry(s->device,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
/* Imported GPU images use ordinary scene placement/chrome, with no CPU pixels.
 * The window transport validates the same bounds before calling this boundary. */
struct scene_retained_image {uint32_t x,y,w,h,image[8];};
int pocket_scene_retained_supported(void){
#ifdef POCKET_SCENE_GL
 return dlsym(RTLD_DEFAULT,"n810_mbx_window_import")&&dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");
#else
 return 0;
#endif
}
int pocket_scene_retained_forget(void *target){
#ifdef POCKET_SCENE_GL
 struct scene_texture *image=target;if(!image||!image->texture)return -1;
 int (*forget)(unsigned)=(int (*)(unsigned))dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");
 if(!forget)return -1;
 glFinish();
 for(unsigned i=0;i<image->texture->n;i++)if(forget(image->texture->tiles[i].color))return -1;
 return 0;
#else
 (void)target;return -1;
#endif
}
int pocket_scene_retained_rebind(void *target,const struct scene_retained_image *images,unsigned count){
#ifdef POCKET_SCENE_GL
 struct scene_texture *image=target;
 int (*bind)(unsigned,const void *)=(int (*)(unsigned,const void *))dlsym(RTLD_DEFAULT,"n810_mbx_window_import");
 int (*forget)(unsigned)=(int (*)(unsigned))dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");
 if(!image||!images||!bind||!forget||count!=image->texture->n)return -1;
 for(unsigned i=0;i<count;i++){
  const struct scene_gl_tile *q=image->texture->tiles+i;const struct scene_retained_image *p=images+i;
  if(q->x!=p->x||q->y!=p->y||q->w!=p->w||q->h!=p->h||q->pw!=p->image[1]||q->ph!=p->image[2])return -1;
 }
 glFinish();
 for(unsigned i=0;i<count;i++)if(bind(image->texture->tiles[i].color,images[i].image)){
  for(unsigned j=0;j<i;j++)forget(image->texture->tiles[j].color);
  return -1;
 }
 ++image->texture->revision;return 0;
#else
 (void)target;(void)images;(void)count;return -1;
#endif
}
void *pocket_scene_retained(void *ptr,unsigned width,unsigned height,const struct scene_retained_image *images,unsigned count){
#ifdef POCKET_SCENE_GL
 struct gpu_scene *s=ptr;unsigned area=0,slots=0;
 int (*import_image)(unsigned,const void *)=(int (*)(unsigned,const void *))dlsym(RTLD_DEFAULT,"n810_mbx_window_import");
 int (*forget)(unsigned)=(int (*)(unsigned))dlsym(RTLD_DEFAULT,"n810_mbx_window_forget");
 if(!s||scene_gl_owner(s->device)||!import_image||!forget||!images||!count||count>14||!width||!height||width>800||height>480)return NULL;
 for(unsigned i=0;i<count;i++){
  const struct scene_retained_image *p=images+i;const uint32_t *d=p->image;
  if(!p->w||!p->h||p->x>width||p->y>height||p->w>width-p->x||p->h>height-p->y||!d[0]||d[1]<p->w||d[2]<p->h||d[1]>800||d[2]>480||d[3]!=1||!d[4]||!d[5]||d[6]>=14||(slots&(1U<<d[6])))return NULL;
  if(d[0]==1){if(d[1]!=128||d[2]!=128||d[7])return NULL;}
  else if(d[0]==2){if(d[7]!=d[1]*4U||(d[6]<2?(d[1]!=240||d[2]!=320):(d[1]!=128||d[2]!=128)))return NULL;}
  else return NULL;
  slots|=1U<<d[6];area+=p->w*p->h;
  for(unsigned j=0;j<i;j++){const struct scene_retained_image *q=images+j;if(p->x<q->x+q->w&&q->x<p->x+p->w&&p->y<q->y+q->h&&q->y<p->y+p->h)return NULL;}
 }
 if(area!=width*height)return NULL;
 struct scene_texture *result=calloc(1,sizeof(*result));Scene_Texture *t=calloc(1,sizeof(*t));
 if(!result||!t){free(result);free(t);return NULL;}
 t->w=width;t->h=height;t->refs=1;t->n=count;t->format=Scene_PIXELFORMAT_ABGR8888;t->blend=Scene_BLENDMODE_NONE;
 t->tiles=calloc(count,sizeof(*t->tiles));if(!t->tiles){free(t);free(result);return NULL;}
 GLint old_fbo,old_texture;glGetIntegerv(GL_FRAMEBUFFER_BINDING,&old_fbo);glGetIntegerv(GL_TEXTURE_BINDING_2D,&old_texture);glFinish();unsigned imported=0;
 for(unsigned i=0;i<count;i++){
  const struct scene_retained_image *p=images+i;struct scene_gl_tile *q=t->tiles+i;
  q->x=p->x;q->y=p->y;q->w=p->w;q->h=p->h;q->pw=p->image[1];q->ph=p->image[2];
  glGenTextures(1,&q->color);glBindTexture(GL_TEXTURE_2D,q->color);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,q->pw,q->ph,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);
  glGenFramebuffers(1,&q->fbo);glBindFramebuffer(GL_FRAMEBUFFER,q->fbo);glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,q->color,0);
  if(glCheckFramebufferStatus(GL_FRAMEBUFFER)!=GL_FRAMEBUFFER_COMPLETE||glGetError()!=GL_NO_ERROR||import_image(q->color,p->image))goto fail;
  ++imported;
  /* Symbian's screen bitmap stores logical top row at texture row zero.
   * Keep the normal uploaded-image orientation in the scene sampler; the FBO
   * above only established importable storage and is never a drawing target. */
  glDeleteFramebuffers(1,&q->fbo);q->fbo=0;
 }
 glBindFramebuffer(GL_FRAMEBUFFER,old_fbo);glBindTexture(GL_TEXTURE_2D,old_texture);
 result->texture=t;result->width=width;result->height=height;return result;
fail:
 for(unsigned i=0;i<imported;i++)forget(t->tiles[i].color);
 Scene_DestroyTexture(t);free(result);glBindFramebuffer(GL_FRAMEBUFFER,old_fbo);glBindTexture(GL_TEXTURE_2D,old_texture);return NULL;
#else
 (void)ptr;(void)width;(void)height;(void)images;(void)count;return NULL;
#endif
}
int pocket_scene_image(void *ptr,void *target,int x,int y){struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||scene_target(s,s->canvas))return -1;Scene_Rect r={x,y,(int)image->width,(int)image->height};return Scene_RenderCopy(s->device,image->texture,NULL,&r);}
void *pocket_scene_upload(void *ptr,const void *pixels,unsigned width,unsigned height,int alpha){
 struct gpu_scene *s=ptr;if(!s||!pixels||!width||!height||width>4096||height>4096)return NULL;struct scene_texture *image=calloc(1,sizeof(*image));if(!image)return NULL;image->width=width;image->height=height;
 image->texture=Scene_CreateTexture(s->device,alpha?Scene_PIXELFORMAT_ABGR8888:Scene_PIXELFORMAT_RGB565,Scene_TEXTUREACCESS_STATIC,width,height);if(!image->texture){free(image);return NULL;}
 const void *source=pixels;uint32_t *rgba=NULL;if(alpha){rgba=malloc((size_t)width*height*4);if(!rgba){Scene_DestroyTexture(image->texture);free(image);return NULL;}const uint32_t *in=pixels;for(size_t i=0;i<(size_t)width*height;i++){uint32_t c=scene_565(in[i]&65535);rgba[i]=((c&255)<<16)|(c&0xff00)|((c>>16)&255)|(in[i]&0xff0000)<<8;}source=rgba;}
 int result=Scene_UpdateTexture(image->texture,NULL,source,width*(alpha?4:2));free(rgba);if(result){Scene_DestroyTexture(image->texture);free(image);return NULL;}Scene_SetTextureBlendMode(image->texture,alpha?Scene_BLENDMODE_BLEND:Scene_BLENDMODE_NONE);Scene_SetTextureScaleMode(image->texture,Scene_ScaleModeNearest);s->uploads+=(uint64_t)width*height*(alpha?4:2);return image;
}
int pocket_scene_layer(void *ptr,void *target,int x,int y,int sx,int sy,unsigned shadow,int cx,int cy,unsigned cw,unsigned ch){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||shadow>255||scene_target(s,s->canvas))return -1;Scene_Rect clip={cx,cy,(int)cw,(int)ch},rect={x,y,(int)image->width,(int)image->height};if(Scene_RenderSetClipRect(s->device,&clip))return -1;
 if(shadow){Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_BLEND);Scene_SetRenderDrawColor(s->device,0,0,0,(uint8_t)shadow);Scene_Rect shade={x+sx,y+sy,rect.w,rect.h};if(Scene_RenderFillRect(s->device,&shade))return -1;}
 int result=Scene_RenderCopy(s->device,image->texture,NULL,&rect);Scene_RenderSetClipRect(s->device,NULL);return result;
}
int pocket_scene_draw(void *ptr,int native_text){
 struct gpu_scene *s=ptr;if(!s||scene_target(s,NULL)||Scene_SetRenderDrawColor(s->device,0,0,0,255)||Scene_RenderClear(s->device)||Scene_RenderSetLogicalSize(s->device,s->width,s->height)||Scene_RenderCopy(s->device,s->canvas,NULL,NULL))return -1;
#ifdef __APPLE__
 if(native_text&&pocket_native_text_draw(s->device,s->width,s->height))return -1;
#else
 (void)native_text;
#endif
 return 0;
}
int pocket_scene_present(void *ptr,int native_text){struct gpu_scene *s=ptr;
#ifdef POCKET_SCENE_GL
 (void)native_text;if(!s||Scene_PresentTarget(s->device,s->canvas))return -1;
#else
 if(pocket_scene_draw(ptr,native_text))return -1;
 Scene_RenderPresent(s->device);
#endif
 s->frames++;return 0;
}
int pocket_scene_capture(void *ptr,void *out,size_t size){struct gpu_scene *s=ptr;if(!s||!out||size!=(size_t)s->width*s->height*2||scene_target(s,s->canvas))return -1;s->readbacks++;
#ifdef POCKET_SCENE_GL
 int presented=Scene_ReadPresented(s->device,s->canvas,out,s->width*2);if(presented)return presented<0?-1:0;
#endif
 return Scene_RenderReadPixels(s->device,NULL,Scene_PIXELFORMAT_RGB565,out,s->width*2);}
int pocket_scene_stats(void *ptr,uint64_t out[5]){struct gpu_scene *s=ptr;if(!s||!out)return -1;out[0]=s->frames;out[1]=s->map_builds;out[2]=s->line_segments;out[3]=s->readbacks;out[4]=s->uploads;return 0;}
int pocket_scene_retained_draw(void *ptr,void *target,int x,int y,int width,int height){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;
 if(!s||!image||width<=0||height<=0||scene_target(s,s->canvas))return -1;
 Scene_Rect clip={x,y,width,height};if(Scene_RenderSetClipRect(s->device,&clip))return -1;
 Scene_Rect rect={x+(width>(int)image->width?(width-(int)image->width)/2:0),y+(height>(int)image->height?(height-(int)image->height)/2:0),(int)image->width,(int)image->height};
 int result=Scene_RenderCopy(s->device,image->texture,NULL,&rect);
 if(Scene_RenderSetClipRect(s->device,NULL))return -1;
 return result;
}
void pocket_scene_texture_free(void *ptr){struct scene_texture *image=ptr;if(image){Scene_DestroyTexture(image->texture);free(image);}}
void pocket_scene_close(void *ptr){struct gpu_scene *s=ptr;if(!s)return;
 if(s->base)Scene_DestroyTexture(s->base);
 if(s->canvas)Scene_DestroyTexture(s->canvas);
 if(s->font)Scene_DestroyTexture(s->font);
 for(unsigned i=0;i<32;i++)if(s->runs[i].texture)Scene_DestroyTexture(s->runs[i].texture);
 if(s->font_pixels&&getenv("POCKET_SCENE_PROFILE"))fprintf(stderr,"POCKET_TEXT_RUNS builds=%llu hits=%llu source_bytes=%llu\n",(unsigned long long)s->run_builds,(unsigned long long)s->run_hits,(unsigned long long)s->run_bytes);
 free(s->font_pixels);free(s->codes);free(s->glyph_rects);free(s->vertices);free(s->flux_vertices);scene_device_close(s->device);free(s);}
struct scene_cell_record {uint32_t index,glyph;uint64_t ink;};
static uint32_t scene_pack565(uint64_t rgb){return ((rgb>>8)&0xf800)|((rgb>>5)&0x7e0)|((rgb>>3)&31);}
static uint32_t scene_record_colors(uint64_t ink,const uint32_t *palette,unsigned count,uint32_t fallback,unsigned *alpha){
 if(ink&(UINT64_C(1)<<49)){unsigned role=(ink>>50)&3;*alpha=255;return (role<count?palette[role]&65535:65535)|(scene_pack565(ink)<<16);}
 if(ink>=(UINT64_C(1)<<48))return scene_pack565(ink>>24)|(scene_pack565(ink)<<16);
 if(ink>=(UINT64_C(1)<<24))return scene_pack565(ink)|(fallback<<16);
 return ink<count?palette[ink]:0;
}
/* Sparse landscape artwork from the shared scene producer. This bypasses
 * desktop cell composition and ANSI; solid glyph coverage becomes geometry,
 * irregular artwork keeps the exact installed font atlas. */
int pocket_scene_landscape(void *ptr,const struct scene_mark *marks,unsigned count,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback){
 struct gpu_scene *s=ptr;if(!s||!cols||cols>512||!rows||rows>256||count>cols*rows||(count&&!marks)||!palette||!palettes||scene_capacity(s,(size_t)count*6)||scene_target(s,s->canvas))return -1;
 for(unsigned i=0;i<count;i++)if(marks[i].index>=cols*rows||(marks[i].glyph!=32&&scene_glyph(s,marks[i].glyph)<0))return -1;
 if(Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_NONE))return -1;
 for(unsigned i=0;i<count;i++){unsigned alpha=255;uint32_t color=scene_record_colors(marks[i].ink,palette,palettes,fallback,&alpha);scene_quad(s->vertices+i*6,x+(marks[i].index%cols)*8,y+(marks[i].index/cols)*16,8,16,scene_rgb(scene_565(color>>16)),0,0,0,0);}
 if(count&&Scene_RenderGeometry(s->device,NULL,s->vertices,count*6,NULL,0))return -1;
 unsigned n=0;
 for(unsigned i=0;i<count;i++){if(marks[i].glyph==32)continue;int at=scene_glyph(s,marks[i].glyph);Scene_Rect q=s->glyph_rects[at];if(!q.w)continue;unsigned alpha=255;uint32_t color=scene_record_colors(marks[i].ink,palette,palettes,fallback,&alpha);scene_quad(s->vertices+n++*6,x+(marks[i].index%cols)*8+q.x,y+(marks[i].index/cols)*16+q.y,q.w,q.h,scene_rgb(scene_565(color&65535)),0,0,0,0);}
 if(n&&Scene_RenderGeometry(s->device,NULL,s->vertices,n*6,NULL,0))return -1;
 n=0;
 for(unsigned i=0;i<count;i++){if(marks[i].glyph==32)continue;int at=scene_glyph(s,marks[i].glyph);if(s->glyph_rects[at].w)continue;unsigned alpha=255;uint32_t color=scene_record_colors(marks[i].ink,palette,palettes,fallback,&alpha);scene_glyph_quad(s,s->vertices+n++*6,at,x+(marks[i].index%cols)*8,y+(marks[i].index/cols)*16,scene_rgb(scene_565(color&65535)));}
 return n?Scene_RenderGeometry(s->device,s->font,s->vertices,n*6,NULL,0):0;
}
static int scene_window_records(struct gpu_scene *s,struct scene_texture *target,const struct scene_cell_record *records,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback,int fill,unsigned opacity){
 size_t count=(size_t)cols*rows;if(!records||!palette||!palettes||cols>512||rows>256||opacity>255||scene_capacity(s,count*6)||scene_target(s,target->texture))return -1;
 Scene_SetRenderDrawBlendMode(s->device,Scene_BLENDMODE_BLEND);
 unsigned backgrounds=0;
 for(size_t i=0;i<count;){
  if(records[i].index!=i)return -1;
  unsigned alpha=fill?opacity:0;uint32_t colors=scene_record_colors(records[i].ink,palette,palettes,fallback,&alpha);unsigned run=1;
  while(i+run<count&&(i+run)%cols){unsigned next_alpha=fill?opacity:0;if(records[i+run].index!=i+run)return -1;uint32_t next=scene_record_colors(records[i+run].ink,palette,palettes,fallback,&next_alpha);if((next>>16)!=(colors>>16)||next_alpha!=alpha)break;run++;}
  if(alpha){Scene_Color color=scene_rgb(scene_565(colors>>16));color.a=(uint8_t)alpha;scene_quad(s->vertices+backgrounds++*6,x+(i%cols)*8,y+(i/cols)*16,run*8,16,color,0,0,0,0);}
  i+=run;
 }
 if(backgrounds&&Scene_RenderGeometry(s->device,NULL,s->vertices,(int)(backgrounds*6),NULL,0))return -1;
 unsigned n=0;
 if(s->font_pixels){
  for(size_t i=0;i<count;){
   unsigned alpha=fill?opacity:0;uint32_t color=scene_record_colors(records[i].ink,palette,palettes,fallback,&alpha)&65535;
   uint32_t text[128];unsigned run=1;text[0]=records[i].glyph;
   while(i+run<count&&(i+run)%cols&&run<128){unsigned a=fill?opacity:0;uint32_t next=scene_record_colors(records[i+run].ink,palette,palettes,fallback,&a)&65535;if(next!=color)break;text[run]=records[i+run].glyph;++run;}
   if(scene_text_run(s,x+(i%cols)*8,y+(i/cols)*16,text,run,scene_rgb(scene_565(color))))return -1;
   i+=run;
  }return 0;
 }
 for(size_t i=0;i<count;i++){if(records[i].glyph==32)continue;int at=scene_glyph(s,records[i].glyph);if(at<0)return -1;unsigned alpha=fill?opacity:0;uint32_t colors=scene_record_colors(records[i].ink,palette,palettes,fallback,&alpha);scene_glyph_quad(s,s->vertices+n*6,at,x+(i%cols)*8,y+(i/cols)*16,scene_rgb(scene_565(colors&65535)));n++;}
 return n?Scene_RenderGeometry(s->device,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_window_draw(void *ptr,const struct scene_cell_record *records,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback,int fill,unsigned opacity){
 struct gpu_scene *s=ptr;if(!s||!s->canvas)return -1;
 struct scene_texture canvas={.texture=s->canvas,.width=s->width,.height=s->height};
 return scene_window_records(s,&canvas,records,cols,rows,x,y,palette,palettes,fallback,fill,opacity);
}
void *pocket_scene_window(void *ptr,const struct scene_cell_record *records,unsigned cols,unsigned rows,const uint32_t *palette,unsigned palettes,unsigned fallback,int fill,unsigned opacity){
 struct gpu_scene *s=ptr;if(!s||!cols||!rows||cols>512||rows>256)return NULL;struct scene_texture *target=calloc(1,sizeof(*target));if(!target)return NULL;target->width=cols*8;target->height=rows*16;
 target->texture=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_ABGR8888,Scene_TEXTUREACCESS_TARGET,target->width,target->height);if(!target->texture){free(target);return NULL;}
 if(scene_target(s,target->texture)||Scene_SetRenderDrawColor(s->device,0,0,0,0)||Scene_RenderClear(s->device)||scene_window_records(s,target,records,cols,rows,0,0,palette,palettes,fallback,fill,opacity)){Scene_DestroyTexture(target->texture);free(target);return NULL;}
 Scene_BlendMode premultiplied=Scene_ComposeCustomBlendMode(Scene_BLENDFACTOR_ONE,Scene_BLENDFACTOR_ONE_MINUS_SRC_ALPHA,Scene_BLENDOPERATION_ADD,Scene_BLENDFACTOR_ONE,Scene_BLENDFACTOR_ONE_MINUS_SRC_ALPHA,Scene_BLENDOPERATION_ADD);
 if(Scene_SetTextureBlendMode(target->texture,premultiplied)){Scene_DestroyTexture(target->texture);free(target);return NULL;}return target;
}
int pocket_scene_window_patch(void *ptr,void *target,const struct scene_cell_record *records,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image)return -1;return scene_window_records(s,image,records,cols,rows,x,y,palette,palettes,fallback,1,255);
}

#ifdef POCKET_SCENE_GL
/* Producer GL entry points stay inside the owning backend/context. */
int pocket_scene_room_region_source(void *ptr,void *draw){struct gpu_scene *s=ptr;if(!s||!draw)return -1;s->room_region=draw;return 0;}
int pocket_scene_room_source(void *ptr,void *draw,void *eye){
 struct gpu_scene *s=ptr;if(!s||!draw||!eye)return -1;s->room_draw=draw;s->room_eye=eye;return 0;
}
void *pocket_scene_room_create(void *ptr,unsigned width,unsigned height){
 struct gpu_scene *s=ptr;if(!s||!width||!height||width>4096||height>4096)return NULL;
 struct scene_texture *t=calloc(1,sizeof(*t));if(!t)return NULL;t->width=width;t->height=height;
 const char *direct=getenv("POCKET_SCENE_DIRECT_ROOM");
 if(s->room_region&&direct&&!strcmp(direct,"1")){
  t->texture=calloc(1,sizeof(*t->texture));if(t->texture){t->texture->w=width;t->texture->h=height;t->texture->refs=1;t->texture->format=Scene_PIXELFORMAT_RGB565;}
 }else t->texture=Scene_CreateTexture(s->device,Scene_PIXELFORMAT_RGB565,Scene_TEXTUREACCESS_TARGET_DEPTH,width,height);
 if(!t->texture){free(t);return NULL;}return t;
}
int pocket_scene_room(void *ptr,void *target,float age,float x,float z,float yaw,float pitch,float eye){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;
 if(!s||!image||image->texture->refs!=1||scene_gl_owner(s->device)||!s->room_draw||!s->room_eye||s->room_eye(eye))return -1;
 const char *fused=getenv("POCKET_SCENE_DIRECT_ROOM");
 if(s->room_region&&fused&&!strcmp(fused,"1")){
  image->texture->room_region=s->room_region;image->texture->room_eye=s->room_eye;
  float state[6]={age,x,z,yaw,pitch,eye};memcpy(image->texture->room_state,state,sizeof state);
  return 1; /* retained geometry update, not a GPU job count */
 }
 image->texture->clear_pending=0;
 for(unsigned i=0;i<image->texture->n;i++){
  struct scene_gl_tile *tile=image->texture->tiles+i;
  scene_gl_bind(s->device,tile->fbo);glDisable(GL_SCISSOR_TEST);
  if(s->room_draw(age,x,z,yaw,pitch,image->width,image->height,tile->x,tile->y,tile->w,tile->h,tile->ph,1))return -1;
 }
 return (int)image->texture->n;
}
#endif

#ifdef POCKET_SCENE_GL
/* Frontend counters only. Driver FBO materialization must be measured in Mesa
 * and the kernel; none of these numbers claims physical residency. */
int pocket_scene_transfer_stats(void *ptr,uint64_t out[7]){
 struct gpu_scene *s=ptr;if(!s||!out)return -1;Scene_Renderer *r=s->device;
 out[0]=r->owner_checks;out[1]=r->owner_rejects;out[2]=0; /* no make-current in this backend */
 out[3]=r->target_switches;out[4]=r->readback_calls;out[5]=r->readback_bytes;out[6]=r->presentation_bytes;return 0;
}
#endif

int pocket_scene_sink_stats(void *ptr,uint64_t out[2]){
 struct gpu_scene *s=ptr;if(!s||!out)return -1;
#ifdef POCKET_SCENE_GL
 out[0]=s->device->sink_jobs;out[1]=s->device->sink_bytes;
#else
 out[0]=out[1]=0;
#endif
 return 0;
}

int pocket_scene_dma_stats(void *ptr,uint64_t out[2]){
 struct gpu_scene *s=ptr;if(!s||!out)return -1;
#ifdef POCKET_SCENE_GL
 out[0]=s->device->dma_jobs;out[1]=s->device->dma_bytes;
#else
 out[0]=out[1]=0;
#endif
 return 0;
}
