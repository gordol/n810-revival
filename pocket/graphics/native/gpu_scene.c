/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include <math.h>
#include <stdint.h>
#include <string.h>
struct scene_texture {SDL_Texture *texture;unsigned width,height;};
struct scene_mark {uint32_t index,glyph;uint64_t ink;};
struct gpu_scene {
 struct window *window;SDL_Texture *base,*canvas,*font;uint32_t *codes;
 unsigned width,height,count,atlas_width,atlas_height;SDL_Vertex *vertices;size_t capacity;
 uint64_t frames,map_builds,line_segments,readbacks,uploads;
};
static SDL_Color scene_rgb(uint32_t v){return (SDL_Color){(v>>16)&255,(v>>8)&255,v&255,255};}
static uint32_t scene_565(uint32_t v){return (((((v>>11)&31)*255+15)/31)<<16)|(((((v>>5)&63)*255+31)/63)<<8)|(((v&31)*255+15)/31);}
static int scene_target(struct gpu_scene *s,SDL_Texture *target){
 if(SDL_SetRenderTarget(s->window->renderer,target)||SDL_RenderSetLogicalSize(s->window->renderer,0,0)||SDL_RenderSetScale(s->window->renderer,1,1)||SDL_RenderSetViewport(s->window->renderer,NULL)||SDL_RenderSetClipRect(s->window->renderer,NULL))return -1;return 0;
}
static int scene_capacity(struct gpu_scene *s,size_t n){
 if(n>6000000)return -1;if(n<=s->capacity)return 0;SDL_Vertex *v=realloc(s->vertices,n*sizeof(*v));if(!v)return -1;s->vertices=v;s->capacity=n;return 0;
}
static void scene_quad(SDL_Vertex *v,float x,float y,float w,float h,SDL_Color color,float u,float t,float uw,float th){
 const unsigned corner[6]={0,1,2,0,2,3};for(unsigned i=0;i<6;i++){unsigned c=corner[i];v[i].position=(SDL_FPoint){x+((c==1||c==2)?w:0),y+(c>=2?h:0)};v[i].color=color;v[i].tex_coord=(SDL_FPoint){u+((c==1||c==2)?uw:0),t+(c>=2?th:0)};}
}
static int scene_glyph(struct gpu_scene *s,uint32_t code){unsigned lo=0,hi=s->count;while(lo<hi){unsigned m=(lo+hi)/2;if(s->codes[m]<code)lo=m+1;else hi=m;}return lo<s->count&&s->codes[lo]==code?(int)lo:-1;}
static void scene_glyph_quad(struct gpu_scene *s,SDL_Vertex *v,int at,float x,float y,SDL_Color color){unsigned gx=(unsigned)at%64*8,gy=(unsigned)at/64*16;scene_quad(v,x,y,8,16,color,(float)gx/s->atlas_width,(float)gy/s->atlas_height,8.f/s->atlas_width,16.f/s->atlas_height);}
void *pocket_scene_open(void *window,int require_gpu){
 if(!window)return NULL;struct window *w=window;SDL_RendererInfo info;if(SDL_GetRendererInfo(w->renderer,&info))return NULL;
 if(require_gpu&&!(info.flags&SDL_RENDERER_ACCELERATED)){SDL_SetError("Accelerated native scene renderer required");return NULL;}
 struct gpu_scene *s=calloc(1,sizeof(*s));if(s)s->window=w;return s;
}
const char *pocket_scene_backend(void *ptr){struct gpu_scene *s=ptr;SDL_RendererInfo i;if(!s||SDL_GetRendererInfo(s->window->renderer,&i))return "unavailable";return i.name;}
int pocket_scene_font(void *ptr,const uint32_t *codes,const unsigned char *bits,unsigned count,const uint32_t *aa_codes,const unsigned char *coverage,unsigned aa_count){
 struct gpu_scene *s=ptr;if(!s||!codes||!bits||!count||count>32768)return -1;s->atlas_width=512;s->atlas_height=((count+63)/64)*16;
 size_t n=(size_t)s->atlas_width*s->atlas_height;uint32_t *pixels=calloc(n,4);if(!pixels)return -1;
 for(unsigned i=0;i<count;i++){int aa=-1;for(unsigned k=0;k<aa_count;k++)if(aa_codes[k]==codes[i]){aa=(int)k;break;}
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<8;x++){unsigned alpha=aa>=0?coverage[(unsigned)aa*128+y*8+x]:(bits[i*16+y]&(128>>x)?255:0);pixels[((i/64)*16+y)*s->atlas_width+(i%64)*8+x]=0xffffffu|(alpha<<24);}}
 SDL_Texture *font=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_STATIC,s->atlas_width,s->atlas_height);
 int result=font?SDL_UpdateTexture(font,NULL,pixels,s->atlas_width*4):-1;free(pixels);if(result){if(font)SDL_DestroyTexture(font);return -1;}SDL_SetTextureBlendMode(font,SDL_BLENDMODE_BLEND);SDL_SetTextureScaleMode(font,SDL_ScaleModeNearest);
 uint32_t *copy=malloc(count*4);if(!copy){SDL_DestroyTexture(font);return -1;}memcpy(copy,codes,count*4);free(s->codes);s->codes=copy;s->count=count;if(s->font)SDL_DestroyTexture(s->font);s->font=font;s->uploads+=n*4;return 0;
}
int pocket_scene_size(void *ptr,unsigned width,unsigned height){
 struct gpu_scene *s=ptr;if(!s||!width||!height||width>4096||height>4096)return -1;if(width==s->width&&height==s->height)return 0;
 SDL_Texture *base=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_TARGET,width,height),*canvas=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_TARGET,width,height);
 if(!base||!canvas){if(base)SDL_DestroyTexture(base);if(canvas)SDL_DestroyTexture(canvas);return -1;}if(s->base)SDL_DestroyTexture(s->base);if(s->canvas)SDL_DestroyTexture(s->canvas);s->base=base;s->canvas=canvas;s->width=width;s->height=height;return 0;
}
int pocket_scene_cells(void *ptr,const uint32_t *cells,unsigned cols,unsigned rows,int defer){
 struct gpu_scene *s=ptr;size_t count=(size_t)cols*rows;if(!s||!cells||cols*8!=s->width||rows*16!=s->height||!s->font||scene_capacity(s,count*6)||scene_target(s,s->base))return -1;
 for(size_t i=0;i<count;i++)scene_quad(s->vertices+i*6,(float)(i%cols)*8,(float)(i/cols)*16,8,16,scene_rgb(scene_565(cells[i*2+1]>>16)),0,0,0,0);
 if(SDL_RenderGeometry(s->window->renderer,NULL,s->vertices,(int)(count*6),NULL,0))return -1;unsigned n=0;
 for(size_t i=0;i<count;i++){uint32_t code=cells[i*2];if(code==32||(defer&&code>=32&&code<127))continue;int at=scene_glyph(s,code);if(at<0)return -1;scene_glyph_quad(s,s->vertices+n*6,at,(float)(i%cols)*8,(float)(i/cols)*16,scene_rgb(scene_565(cells[i*2+1]&65535)));n++;}
 return n?SDL_RenderGeometry(s->window->renderer,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_begin(void *ptr){struct gpu_scene *s=ptr;if(!s||scene_target(s,s->canvas))return -1;return SDL_RenderCopy(s->window->renderer,s->base,NULL,NULL);}
void *pocket_scene_map(void *ptr,const uint32_t *colors,unsigned cols,unsigned rows,unsigned sample_width,unsigned sample_height,int smooth){
 struct gpu_scene *s=ptr;if(!s||!colors||!cols||!rows||cols>512||rows>256||!sample_width||!sample_height||sample_width>4096||sample_height>4096)return NULL;struct scene_texture *image=calloc(1,sizeof(*image));if(!image)return NULL;image->width=cols*8;image->height=rows*16;
 image->texture=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_TARGET,image->width,image->height);SDL_Texture *samples=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_STATIC,sample_width,sample_height);
 uint32_t *rgba=malloc((size_t)sample_width*sample_height*4);if(!image->texture||!samples||!rgba)goto fail;
 for(size_t i=0;i<(size_t)sample_width*sample_height;i++){uint32_t c=colors[i];rgba[i]=((c&255)<<16)|(c&0xff00)|((c>>16)&255)|0xff000000u;}
 if(SDL_UpdateTexture(samples,NULL,rgba,sample_width*4)||SDL_SetTextureScaleMode(samples,smooth?SDL_ScaleModeLinear:SDL_ScaleModeNearest)||scene_target(s,image->texture)||SDL_RenderCopy(s->window->renderer,samples,NULL,NULL)||SDL_SetTextureScaleMode(image->texture,smooth?SDL_ScaleModeLinear:SDL_ScaleModeNearest))goto fail;
 free(rgba);SDL_DestroyTexture(samples);s->uploads+=(uint64_t)sample_width*sample_height*4;s->map_builds++;return image;
 fail:free(rgba);if(samples)SDL_DestroyTexture(samples);if(image->texture)SDL_DestroyTexture(image->texture);free(image);return NULL;
}
void *pocket_scene_blank(void *ptr,unsigned cols,unsigned rows){
 struct gpu_scene *s=ptr;if(!s||!cols||!rows||cols>512||rows>256)return NULL;
 struct scene_texture *image=calloc(1,sizeof(*image));if(!image)return NULL;
 image->width=cols*8;image->height=rows*16;
 image->texture=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_TARGET,image->width,image->height);
 if(!image->texture||scene_target(s,image->texture)||SDL_SetRenderDrawColor(s->window->renderer,0,0,0,0)||SDL_RenderClear(s->window->renderer)||SDL_SetTextureBlendMode(image->texture,SDL_BLENDMODE_BLEND)){
  if(image->texture)SDL_DestroyTexture(image->texture);free(image);return NULL;
 }
 return image;
}
static int scene_clip(double *x,double *y,double *xx,double *yy,unsigned w,unsigned h){
 double dx=*xx-*x,dy=*yy-*y,low=0,high=1,p[4]={-dx,dx,-dy,dy},q[4]={*x,w-*x,*y,h-*y};
 for(unsigned i=0;i<4;i++){if(!p[i]){if(q[i]<0)return 0;continue;}double t=q[i]/p[i];if(p[i]<0){if(t>high)return 0;if(t>low)low=t;}else{if(t<low)return 0;if(t<high)high=t;}}
 *xx=*x+high*dx;*yy=*y+high*dy;*x+=low*dx;*y+=low*dy;return 1;
}
int pocket_scene_lines(void *ptr,void *target,const double *points,unsigned count,uint32_t color){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||count>250000||(count&&!points)||scene_capacity(s,(size_t)count*6)||scene_target(s,image->texture))return -1;unsigned n=0;
 for(unsigned i=0;i<count;i++){double x=points[i*4],y=points[i*4+1],xx=points[i*4+2],yy=points[i*4+3];if(!isfinite(x)||!isfinite(y)||!isfinite(xx)||!isfinite(yy))return -1;if(!scene_clip(&x,&y,&xx,&yy,image->width,image->height))continue;
  double dx=xx-x,dy=yy-y,length=hypot(dx,dy);if(length<1e-9){scene_quad(s->vertices+n*6,(float)x-.5f,(float)y-.5f,1,1,scene_rgb(color),0,0,0,0);n++;continue;}
  float nx=(float)(-.5*dy/length),ny=(float)(.5*dx/length),tx=(float)(.5*dx/length),ty=(float)(.5*dy/length);SDL_FPoint corners[4]={{(float)x-tx+nx,(float)y-ty+ny},{(float)xx+tx+nx,(float)yy+ty+ny},{(float)xx+tx-nx,(float)yy+ty-ny},{(float)x-tx-nx,(float)y-ty-ny}};const unsigned order[6]={0,1,2,0,2,3};
  for(unsigned k=0;k<6;k++)s->vertices[n*6+k]=(SDL_Vertex){corners[order[k]],scene_rgb(color),{0,0}};n++;}
 s->line_segments+=n;return n?SDL_RenderGeometry(s->window->renderer,NULL,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_marks(void *ptr,void *target,const struct scene_mark *marks,unsigned count,int defer){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||(count&&!marks)||scene_capacity(s,(size_t)count*6)||scene_target(s,image->texture))return -1;unsigned cols=image->width/8,rows=image->height/16;
 for(unsigned i=0;i<count;i++){if(marks[i].index>=cols*rows)return -1;scene_quad(s->vertices+i*6,(marks[i].index%cols)*8,(marks[i].index/cols)*16,8,16,scene_rgb((uint32_t)marks[i].ink&0xffffff),0,0,0,0);}
 if(count&&SDL_RenderGeometry(s->window->renderer,NULL,s->vertices,(int)(count*6),NULL,0))return -1;unsigned n=0;
 for(unsigned i=0;i<count;i++){uint32_t ch=marks[i].glyph;if(ch==32||(defer&&ch>=32&&ch<127))continue;int at=scene_glyph(s,ch);if(at<0)return -1;scene_glyph_quad(s,s->vertices+n*6,at,(marks[i].index%cols)*8,(marks[i].index/cols)*16,scene_rgb((uint32_t)(marks[i].ink>>24)&0xffffff));n++;}
 return n?SDL_RenderGeometry(s->window->renderer,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
int pocket_scene_image(void *ptr,void *target,int x,int y){struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||scene_target(s,s->canvas))return -1;SDL_Rect r={x,y,(int)image->width,(int)image->height};return SDL_RenderCopy(s->window->renderer,image->texture,NULL,&r);}
int pocket_scene_image_region(void *ptr,void *target,int sx,int sy,int sw,int sh,int x,int y,int w,int h,int cx,int cy,int cw,int ch){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;
 if(!s||!image||sx<0||sy<0||sw<=0||sh<=0||w<=0||h<=0||cw<=0||ch<=0||
    sx+sw>(int)image->width||sy+sh>(int)image->height||scene_target(s,s->canvas))return -1;
 SDL_Rect source={sx,sy,sw,sh},dest={x,y,w,h},clip={cx,cy,cw,ch};
 if(SDL_RenderSetClipRect(s->window->renderer,&clip))return -1;
 int result=SDL_RenderCopy(s->window->renderer,image->texture,&source,&dest);
 SDL_RenderSetClipRect(s->window->renderer,NULL);return result;
}
int pocket_scene_fill(void *ptr,int x,int y,int w,int h,uint32_t rgb){
 struct gpu_scene *s=ptr;if(!s||w<=0||h<=0||scene_target(s,s->canvas))return -1;
 SDL_Rect rect={x,y,w,h};SDL_Color color=scene_rgb(rgb);
 if(SDL_SetRenderDrawBlendMode(s->window->renderer,SDL_BLENDMODE_NONE)||
    SDL_SetRenderDrawColor(s->window->renderer,color.r,color.g,color.b,255))return -1;
 return SDL_RenderFillRect(s->window->renderer,&rect);
}
void *pocket_scene_upload(void *ptr,const void *pixels,unsigned width,unsigned height,int alpha){
 struct gpu_scene *s=ptr;if(!s||!pixels||!width||!height||width>4096||height>4096)return NULL;struct scene_texture *image=calloc(1,sizeof(*image));if(!image)return NULL;image->width=width;image->height=height;
 image->texture=SDL_CreateTexture(s->window->renderer,alpha?SDL_PIXELFORMAT_ABGR8888:SDL_PIXELFORMAT_RGB565,SDL_TEXTUREACCESS_STATIC,width,height);if(!image->texture){free(image);return NULL;}
 const void *source=pixels;uint32_t *rgba=NULL;if(alpha){rgba=malloc((size_t)width*height*4);if(!rgba){SDL_DestroyTexture(image->texture);free(image);return NULL;}const uint32_t *in=pixels;for(size_t i=0;i<(size_t)width*height;i++){uint32_t c=scene_565(in[i]&65535);rgba[i]=((c&255)<<16)|(c&0xff00)|((c>>16)&255)|(in[i]&0xff0000)<<8;}source=rgba;}
 int result=SDL_UpdateTexture(image->texture,NULL,source,width*(alpha?4:2));free(rgba);if(result){SDL_DestroyTexture(image->texture);free(image);return NULL;}SDL_SetTextureBlendMode(image->texture,alpha?SDL_BLENDMODE_BLEND:SDL_BLENDMODE_NONE);SDL_SetTextureScaleMode(image->texture,SDL_ScaleModeNearest);s->uploads+=(uint64_t)width*height*(alpha?4:2);return image;
}
int pocket_scene_layer(void *ptr,void *target,int x,int y,int sx,int sy,unsigned shadow,int cx,int cy,unsigned cw,unsigned ch){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image||shadow>255||scene_target(s,s->canvas))return -1;SDL_Rect clip={cx,cy,(int)cw,(int)ch},rect={x,y,(int)image->width,(int)image->height};if(SDL_RenderSetClipRect(s->window->renderer,&clip))return -1;
 if(shadow){SDL_SetRenderDrawBlendMode(s->window->renderer,SDL_BLENDMODE_BLEND);SDL_SetRenderDrawColor(s->window->renderer,0,0,0,(Uint8)shadow);SDL_Rect shade={x+sx,y+sy,rect.w,rect.h};if(SDL_RenderFillRect(s->window->renderer,&shade))return -1;}
 int result=SDL_RenderCopy(s->window->renderer,image->texture,NULL,&rect);SDL_RenderSetClipRect(s->window->renderer,NULL);return result;
}
int pocket_scene_present(void *ptr,int native_text){
 struct gpu_scene *s=ptr;
 if(!s||scene_target(s,NULL)||SDL_SetRenderDrawColor(s->window->renderer,14,23,28,255)||SDL_RenderClear(s->window->renderer)||SDL_RenderSetLogicalSize(s->window->renderer,s->width,s->height)||SDL_RenderCopy(s->window->renderer,s->canvas,NULL,NULL))return -1;
#ifdef __APPLE__
 if(native_text&&pocket_native_text_draw(s->window->renderer,s->width,s->height))return -1;
#else
 (void)native_text;
#endif
 SDL_RenderPresent(s->window->renderer);s->frames++;return 0;
}
int pocket_scene_capture(void *ptr,void *out,size_t size){struct gpu_scene *s=ptr;if(!s||!out||size!=(size_t)s->width*s->height*2||scene_target(s,s->canvas))return -1;s->readbacks++;return SDL_RenderReadPixels(s->window->renderer,NULL,SDL_PIXELFORMAT_RGB565,out,s->width*2);}
int pocket_scene_stats(void *ptr,uint64_t out[5]){struct gpu_scene *s=ptr;if(!s||!out)return -1;out[0]=s->frames;out[1]=s->map_builds;out[2]=s->line_segments;out[3]=s->readbacks;out[4]=s->uploads;return 0;}
void pocket_scene_texture_free(void *ptr){struct scene_texture *image=ptr;if(image){SDL_DestroyTexture(image->texture);free(image);}}
void pocket_scene_close(void *ptr){struct gpu_scene *s=ptr;if(!s)return;if(s->base)SDL_DestroyTexture(s->base);if(s->canvas)SDL_DestroyTexture(s->canvas);if(s->font)SDL_DestroyTexture(s->font);free(s->codes);free(s->vertices);free(s);}
struct scene_cell_record {uint32_t index,glyph;uint64_t ink;};
static uint32_t scene_pack565(uint64_t rgb){return ((rgb>>8)&0xf800)|((rgb>>5)&0x7e0)|((rgb>>3)&31);}
static uint32_t scene_record_colors(uint64_t ink,const uint32_t *palette,unsigned count,uint32_t fallback,unsigned *alpha){
 if(ink&(UINT64_C(1)<<49)){unsigned role=(ink>>50)&3;*alpha=255;return (role<count?palette[role]&65535:65535)|(scene_pack565(ink)<<16);}
 if(ink>=(UINT64_C(1)<<48))return scene_pack565(ink>>24)|(scene_pack565(ink)<<16);
 if(ink>=(UINT64_C(1)<<24))return scene_pack565(ink)|(fallback<<16);
 return ink<count?palette[ink]:0;
}
static int scene_window_records(struct gpu_scene *s,struct scene_texture *target,const struct scene_cell_record *records,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback,int fill,unsigned opacity){
 size_t count=(size_t)cols*rows;if(!records||!palette||!palettes||cols>512||rows>256||opacity>255||scene_capacity(s,count*6)||scene_target(s,target->texture))return -1;
 SDL_SetRenderDrawBlendMode(s->window->renderer,SDL_BLENDMODE_BLEND);
 for(size_t i=0;i<count;i++){if(records[i].index!=i)return -1;unsigned alpha=fill?opacity:0;uint32_t colors=scene_record_colors(records[i].ink,palette,palettes,fallback,&alpha);SDL_Color color=scene_rgb(scene_565(colors>>16));color.a=(Uint8)alpha;scene_quad(s->vertices+i*6,x+(i%cols)*8,y+(i/cols)*16,8,16,color,0,0,0,0);}
 if(count&&SDL_RenderGeometry(s->window->renderer,NULL,s->vertices,(int)(count*6),NULL,0))return -1;unsigned n=0;
 for(size_t i=0;i<count;i++){if(records[i].glyph==32)continue;int at=scene_glyph(s,records[i].glyph);if(at<0)return -1;unsigned alpha=fill?opacity:0;uint32_t colors=scene_record_colors(records[i].ink,palette,palettes,fallback,&alpha);scene_glyph_quad(s,s->vertices+n*6,at,x+(i%cols)*8,y+(i/cols)*16,scene_rgb(scene_565(colors&65535)));n++;}
 return n?SDL_RenderGeometry(s->window->renderer,s->font,s->vertices,(int)(n*6),NULL,0):0;
}
void *pocket_scene_window(void *ptr,const struct scene_cell_record *records,unsigned cols,unsigned rows,const uint32_t *palette,unsigned palettes,unsigned fallback,int fill,unsigned opacity){
 struct gpu_scene *s=ptr;if(!s||!cols||!rows||cols>512||rows>256)return NULL;struct scene_texture *target=calloc(1,sizeof(*target));if(!target)return NULL;target->width=cols*8;target->height=rows*16;
 target->texture=SDL_CreateTexture(s->window->renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_TARGET,target->width,target->height);if(!target->texture){free(target);return NULL;}
 if(scene_target(s,target->texture)||SDL_SetRenderDrawColor(s->window->renderer,0,0,0,0)||SDL_RenderClear(s->window->renderer)||scene_window_records(s,target,records,cols,rows,0,0,palette,palettes,fallback,fill,opacity)){SDL_DestroyTexture(target->texture);free(target);return NULL;}
 SDL_BlendMode premultiplied=SDL_ComposeCustomBlendMode(SDL_BLENDFACTOR_ONE,SDL_BLENDFACTOR_ONE_MINUS_SRC_ALPHA,SDL_BLENDOPERATION_ADD,SDL_BLENDFACTOR_ONE,SDL_BLENDFACTOR_ONE_MINUS_SRC_ALPHA,SDL_BLENDOPERATION_ADD);
 if(SDL_SetTextureBlendMode(target->texture,premultiplied)){SDL_DestroyTexture(target->texture);free(target);return NULL;}return target;
}
int pocket_scene_window_patch(void *ptr,void *target,const struct scene_cell_record *records,unsigned cols,unsigned rows,int x,int y,const uint32_t *palette,unsigned palettes,unsigned fallback){
 struct gpu_scene *s=ptr;struct scene_texture *image=target;if(!s||!image)return -1;return scene_window_records(s,image,records,cols,rows,x,y,palette,palettes,fallback,1,255);
}
