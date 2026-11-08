/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Mac presentation text. One immutable CoreText atlas per output density;
 * apps, hit testing and device bitmaps retain the original logical cell grid. */
#include "native_text.h"
#include <CoreText/CoreText.h>
#include <CoreGraphics/CoreGraphics.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>
static SDL_Texture *atlas;
static SDL_Renderer *atlas_owner;
static unsigned atlas_scale;
static uint32_t *cells;
static size_t cell_words,capacity;
static SDL_Vertex *vertices;
static size_t vertex_capacity;
int pocket_native_text_stage(const uint32_t *data,size_t words){
 if(words>512U*256*2||words%2||(words&&!data))return -1;
 if(words>capacity){uint32_t *p=realloc(cells,words*4);if(!p)return -1;cells=p;capacity=words;}
 if(words)memcpy(cells,data,words*4);cell_words=words;return 0;
}
int pocket_native_text_clear(uint32_t *data,size_t words,unsigned cols,unsigned rows,int x,int y,unsigned w,unsigned h){
 if(!data||!cols||cols>512||!rows||rows>256||words!=(size_t)cols*rows*2||w>4096||h>4096||x < -4096||y < -4096||x>4096||y>4096)return -1;
 /* Only whole logical cells occur in direct-app image rectangles. */
 if(x%8||y%16||w%8||h%16)return -1;
 for(int yy=y/16;yy<(y+(int)h)/16;yy++)for(int xx=x/8;xx<(x+(int)w)/8;xx++)
  if(xx>=0&&yy>=0&&(unsigned)xx<cols&&(unsigned)yy<rows)data[((size_t)yy*cols+xx)*2]=0;
 return 0;
}
struct text_mark {uint32_t index,ch;uint64_t ink;};
int pocket_native_text_marks(uint32_t *data,size_t words,unsigned cols,unsigned rows,const void *raw,unsigned count,int x,int y,unsigned w,unsigned h){
 const struct text_mark *marks=raw;
 if(!data||!cols||cols>512||!rows||rows>256||words!=(size_t)cols*rows*2||!w||w>512||!h||h>256||count>w*h||(count&&!raw)||x < -512||y < -256||x>512||y>256)return -1;
 for(unsigned i=0;i<count;i++)if(marks[i].index>=w*h)return -1;
 for(unsigned i=0;i<count;i++){
  int xx=x+(int)(marks[i].index%w),yy=y+(int)(marks[i].index/w);
  if(xx<0||yy<0||(unsigned)xx>=cols||(unsigned)yy>=rows)continue;
  size_t at=((size_t)yy*cols+xx)*2;uint64_t rgb=marks[i].ink>>24;
  data[at]=marks[i].ch;data[at+1]=((rgb>>8)&0xf800)|((rgb>>5)&0x7e0)|((rgb>>3)&31);
 }
 return 0;
}
static int make_atlas(SDL_Renderer *renderer,unsigned scale){
 unsigned cw=8*scale,ch=16*scale,width=cw*19,height=ch*5;
 unsigned char *alpha=calloc((size_t)width,height),*rgba=malloc((size_t)width*height*4);
 if(!alpha||!rgba){free(alpha);free(rgba);return -1;}
 CGColorSpaceRef gray=CGColorSpaceCreateDeviceGray();
 CGContextRef ctx=CGBitmapContextCreate(alpha,width,height,8,width,gray,kCGImageAlphaNone);
 CTFontRef font=CTFontCreateWithName(CFSTR("Menlo"),13*scale,NULL);
 if(!ctx||!font){if(ctx)CGContextRelease(ctx);if(font)CFRelease(font);CGColorSpaceRelease(gray);free(alpha);free(rgba);return -1;}
 CGContextSetGrayFillColor(ctx,1,1);CGContextSetShouldAntialias(ctx,true);
 for(unsigned code=32;code<127;code++){
  UniChar c=code;CFStringRef text=CFStringCreateWithCharacters(NULL,&c,1);
  const void *keys[]={kCTFontAttributeName,kCTForegroundColorFromContextAttributeName},*values[]={font,kCFBooleanTrue};
  CFDictionaryRef attrs=CFDictionaryCreate(NULL,keys,values,2,&kCFTypeDictionaryKeyCallBacks,&kCFTypeDictionaryValueCallBacks);
  CFAttributedStringRef attributed=CFAttributedStringCreate(NULL,text,attrs);CTLineRef line=CTLineCreateWithAttributedString(attributed);
  unsigned i=code-32,x=(i%19)*cw,y=(4-i/19)*ch;
  CGContextSaveGState(ctx);CGContextClipToRect(ctx,CGRectMake(x,y,cw,ch));
  CGContextTranslateCTM(ctx,x,y+2*scale);double advance=CTLineGetTypographicBounds(line,NULL,NULL,NULL);
  if(advance>cw)CGContextScaleCTM(ctx,cw/advance,1);
  CGContextSetTextPosition(ctx,0,0);CTLineDraw(line,ctx);CGContextRestoreGState(ctx);
  CFRelease(line);CFRelease(attributed);CFRelease(attrs);CFRelease(text);
 }
 /* CoreGraphics bitmap memory uses the same top-row convention as the existing
  * generated coverage asset; retain it, including baseline and cell clipping. */
 for(size_t i=0;i<(size_t)width*height;i++){rgba[i*4]=rgba[i*4+1]=rgba[i*4+2]=255;rgba[i*4+3]=alpha[i];}
 CGContextRelease(ctx);CFRelease(font);CGColorSpaceRelease(gray);free(alpha);
 SDL_Texture *next=SDL_CreateTexture(renderer,SDL_PIXELFORMAT_RGBA32,SDL_TEXTUREACCESS_STATIC,width,height);
 if(!next){free(rgba);return -1;}
 int result=SDL_UpdateTexture(next,NULL,rgba,width*4)||SDL_SetTextureBlendMode(next,SDL_BLENDMODE_BLEND);free(rgba);
 if(result){SDL_DestroyTexture(next);return -1;}
 SDL_SetTextureScaleMode(next,SDL_ScaleModeLinear);
 if(atlas)SDL_DestroyTexture(atlas);atlas=next;atlas_owner=renderer;atlas_scale=scale;return 0;
}
unsigned pocket_native_text_density(unsigned ow,unsigned oh,unsigned pw,unsigned ph,unsigned width,unsigned height){
 if(!ow||!oh||!width||!height)return 0;
 float scale=pw&&ph?fminf((float)ow/pw,(float)oh/ph):fminf((float)ow/width,(float)oh/height);
 unsigned density=(unsigned)ceilf(scale-0.0001f);return density<1?1:density>8?0:density;
}
int pocket_native_text_draw(SDL_Renderer *renderer,unsigned width,unsigned height){
 if(!cell_words)return 0;
 if(!width||width%8||!height||height%16||cell_words!=(size_t)(width/8)*(height/16)*2)return -1;
 int ow,oh;if(SDL_GetRendererOutputSize(renderer,&ow,&oh))return -1;
 int pw=0,ph=0;SDL_Window *window=SDL_RenderGetWindow(renderer);if(window)SDL_GetWindowSize(window,&pw,&ph);
 /* Backing density belongs to the display; odd logical canvas sizes and
  * letterboxing must not switch a Retina atlas between2x and3x. */
 unsigned density=pocket_native_text_density(ow,oh,pw,ph,width,height);if(!density)return -1;
 if(!atlas||atlas_owner!=renderer||atlas_scale!=density)if(make_atlas(renderer,density))return -1;
 size_t needed=cell_words/2*6;if(needed>vertex_capacity){SDL_Vertex *p=realloc(vertices,needed*sizeof(*p));if(!p)return -1;vertices=p;vertex_capacity=needed;}
 size_t n=0;unsigned cols=width/8;const unsigned dx[]={0,1,0,1,1,0},dy[]={0,0,1,0,1,1};
 for(size_t i=0;i<cell_words/2;i++){
  unsigned code=cells[i*2],color=cells[i*2+1];if(code<=32||code>=127)continue;
  unsigned g=code-32;SDL_Color ink={(Uint8)(((color>>11)*255+15)/31),(Uint8)((((color>>5)&63)*255+31)/63),(Uint8)(((color&31)*255+15)/31),255};
  for(unsigned k=0;k<6;k++){SDL_Vertex *v=vertices+n++;v->position=(SDL_FPoint){(float)((i%cols+dx[k])*8),(float)((i/cols+dy[k])*16)};v->color=ink;v->tex_coord=(SDL_FPoint){(g%19+dx[k])/19.f,(g/19+dy[k])/5.f};}
 }
 return n?SDL_RenderGeometry(renderer,atlas,vertices,(int)n,NULL,0):0;
}
void pocket_native_text_close(void){if(atlas)SDL_DestroyTexture(atlas);atlas=NULL;atlas_owner=NULL;free(cells);cells=NULL;capacity=cell_words=0;free(vertices);vertices=NULL;vertex_capacity=0;}
