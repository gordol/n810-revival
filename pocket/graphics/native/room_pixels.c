/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Direct full-resolution room geometry. No semantic-cell or glyph conversion. */
#define GL_GLEXT_PROTOTYPES
#ifdef POCKET_DESKTOP_GL
#include "desktop_context.h"
#else
#include <GL/osmesa.h>
#endif
#include <stdint.h>
#include <math.h>
#include <string.h>
#include "room_mesh.h"
#include "pixel_target.h"
#include "room_draw.h"
/* Called on the GL owner thread before rendering a view. The caller retains
 * per-view camera state; this is only the current native draw setting. */
static float room_eye_height=340.f;
int pocket_room_set_eye_height(float height){
 if(!isfinite(height)||height<0.f||height>20000.f)return -1;
 room_eye_height=height;return 0;
}
/* Local-only fused composition plan. Handles remain owned by the caller. */
int pocket_pixel_layer_gpu(void *,int,int);
static struct {void *layer;int x,y;} room_overlays[32];
static unsigned room_overlay_count;
int pocket_room_gpu_layers(void *const *layers,const int *xy,unsigned count){
 if(count>32||(count&&(!layers||!xy)))return -1;
 for(unsigned i=0;i<count;++i)if(!layers[i]||xy[2*i]<-800||xy[2*i]>800||xy[2*i+1]<-480||xy[2*i+1]>480)return -1;
 /* Existing MBX state validator cannot mix depth-tested3D and depth-disabled2D.
  * Keep the candidate physically fail-closed until that contract is extended. */
 const char *renderer=(const char*)glGetString(GL_RENDERER);
 if(count&&(!renderer||strstr(renderer,"Nokia MBX")))return -3;
 for(unsigned i=0;i<count;++i){room_overlays[i].layer=layers[i];room_overlays[i].x=xy[2*i];room_overlays[i].y=xy[2*i+1];}
 room_overlay_count=count;return 0;
}
/* Draw into the caller-owned current GL target. No target switch, finish,
 * readback, allocation or pixel upload. The scene backend owns completion.
 * Tile offsets preserve the original full-view projection and rasterization. */
static int room_draw_region(float age,float x,float z,float yaw,float pitch,unsigned width,unsigned height,int tx,int ty,unsigned tw,unsigned th,unsigned target_height,int with_game,int clear){
 if(!width||!height||width>4096||height>4096||!tw||!th||tw>400||th>400||tx<=-4096||ty<=-4096||tx>=(int)width||ty>=(int)height||(clear&&(tx<0||ty<0||tw>width-(unsigned)tx||th>height-(unsigned)ty))||target_height<th||target_height>4096||!isfinite(age)||!isfinite(x)||!isfinite(z)||!isfinite(yaw)||!isfinite(pitch)||fabsf(pitch)>1.1f)return -1;
 const float eye=room_eye_height;
 float sy=sinf(yaw),cy=cosf(yaw),se=sinf(.05f+pitch),ce=cosf(.05f+pitch);
 float right[]={cy,0,-sy},up[]={-sy*se,-ce,-cy*se},forward[]={sy*ce,-se,cy*ce};
 GLfloat view[]={right[0],-up[0],-forward[0],0,right[1],-up[1],-forward[1],0,right[2],-up[2],-forward[2],0,-(right[0]*x+right[1]*eye+right[2]*z),up[0]*x+up[1]*eye+up[2]*z,forward[0]*x+forward[1]*eye+forward[2]*z,1};
 GLfloat ambient[]={.44f,.42f,.39f,1},sunlight[]={.72f,.72f,.72f,1},zero[]={0,0,0,1},sun[]={-.4879500365f,.7807200584f,-.3903600292f,0};
 glDisable(GL_BLEND);glDisable(GL_TEXTURE_2D);glDisable(GL_CULL_FACE);glDisable(GL_DITHER);glDisable(GL_VERTEX_PROGRAM_ARB);
 glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);glDepthMask(GL_TRUE);glEnable(GL_LIGHTING);glEnable(GL_LIGHT0);glShadeModel(GL_SMOOTH);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_NORMAL_ARRAY);glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
 glLightModelfv(GL_LIGHT_MODEL_AMBIENT,ambient);glLightfv(GL_LIGHT0,GL_DIFFUSE,sunlight);glLightfv(GL_LIGHT0,GL_AMBIENT,zero);glLightfv(GL_LIGHT0,GL_SPECULAR,zero);glMaterialfv(GL_FRONT_AND_BACK,GL_SPECULAR,zero);glMaterialfv(GL_FRONT_AND_BACK,GL_EMISSION,zero);glClearColor(0,0,0,0);glClearDepth(1);
 double top=1085*.05,right_edge=top*width/height;
  glEnable(GL_DEPTH_TEST);glDepthMask(GL_TRUE);glEnable(GL_LIGHTING);glEnableClientState(GL_NORMAL_ARRAY);
  glViewport(-(int)tx,(int)target_height-(int)height+(int)ty,width,height);glMatrixMode(GL_PROJECTION);glLoadIdentity();
  glFrustum(-right_edge,right_edge,-top,top,100,20000);
  glMatrixMode(GL_MODELVIEW);glLoadMatrixf(view);glLightfv(GL_LIGHT0,GL_POSITION,sun);if(clear)glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
  for(unsigned d=0;d<sizeof(room_draws)/sizeof(room_draws[0]);++d){const struct room_draw *draw=room_draws+d;
   glPushMatrix();if(draw->moving){glTranslatef(sinf(age*.35f)*180,0,2050);glRotatef((.15+age*.4)*180/3.141592653589793,0,1,0);}
   glMaterialfv(GL_FRONT_AND_BACK,GL_AMBIENT_AND_DIFFUSE,draw->color);glVertexPointer(3,GL_FLOAT,6*sizeof(float),room_vertices[draw->first]);glNormalPointer(GL_FLOAT,6*sizeof(float),room_vertices[draw->first]+3);
   glDrawArrays(GL_TRIANGLES,0,draw->count);glPopMatrix();
  }
#ifdef POCKET_NATIVE_GAME
 if(with_game)game_draw(age,width,height,tx,ty,tw,th);
#else
 (void)with_game;
#endif
 return 0;
}
int pocket_room_draw_tile(float age,float x,float z,float yaw,float pitch,unsigned width,unsigned height,unsigned tx,unsigned ty,unsigned tw,unsigned th,unsigned target_height,int with_game){
 if(tx>4096||ty>4096)return -1;
 return room_draw_region(age,x,z,yaw,pitch,width,height,(int)tx,(int)ty,tw,th,target_height,with_game,1);
}
/* Draw into an initialized composition target. Caller owns clipping and has
 * cleared depth once for this frame. No intermediate image or clear occurs. */
int pocket_room_draw_region(float age,float x,float z,float yaw,float pitch,unsigned width,unsigned height,int tx,int ty,unsigned tw,unsigned th,unsigned target_height,int with_game){
 return room_draw_region(age,x,z,yaw,pitch,width,height,tx,ty,tw,th,target_height,with_game,0);
}
/* Pixel compatibility sink; only this entry materializes completed tiles. */
int pocket_room_pixels_into(float age,float x,float z,float yaw,float pitch,unsigned width,unsigned height,uint16_t *out,unsigned stride,size_t capacity,unsigned tile_limit){
 if(!out||!width||!height||width>4096||height>4096||stride<width||stride>4096||capacity<((size_t)(height-1)*stride+width)*2||!tile_limit||tile_limit>400||!isfinite(age)||!isfinite(x)||!isfinite(z)||!isfinite(yaw)||!isfinite(pitch)||fabsf(pitch)>1.1f||!OSMesaGetCurrentContext())return -1;
 GLint bw,bh,format;void *buffer;
 if(!OSMesaGetColorBuffer(OSMesaGetCurrentContext(),&bw,&bh,&format,&buffer)||bw!=400||bh!=400||format!=OSMESA_RGB_565)return -1;
 if(pocket_target_begin())return -2;
 unsigned jobs=0;
 for(unsigned ty=0;ty<height;ty+=tile_limit)for(unsigned tx=0;tx<width;tx+=tile_limit){
  unsigned tw=width-tx,th=height-ty;if(tw>tile_limit)tw=tile_limit;if(th>tile_limit)th=tile_limit;
  if(pocket_room_draw_tile(age,x,z,yaw,pitch,width,height,tx,ty,tw,th,400,0)){pocket_target_end();return -2;}
  for(unsigned i=0;i<room_overlay_count;++i)if(pocket_pixel_layer_gpu(room_overlays[i].layer,room_overlays[i].x-(int)tx,room_overlays[i].y-(int)ty)<0){pocket_target_end();return -3;}
#ifdef POCKET_NATIVE_GAME
  game_draw(age,width,height,tx,ty,tw,th);
#endif
  if(pocket_target_read(out+ty*stride+tx,capacity-((size_t)ty*stride+tx)*2,stride,tw,th)){pocket_target_end();return -2;}++jobs;
 }
 pocket_target_end();return (int)jobs;
}
/* Compatibility entry retains a tightly packed image. The strided entry allows
 * the native presenter/compositor to receive final tiles directly in its canvas. */
int pocket_room_pixels(float age,float x,float z,float yaw,float pitch,unsigned width,unsigned height,uint16_t *out,unsigned tile_limit){
 return pocket_room_pixels_into(age,x,z,yaw,pitch,width,height,out,width,(size_t)width*height*2,tile_limit);
}
/* Native rectangular visibility clipping; no Python pixel walking. */
int pocket_pixels_blit(uint16_t *dst,const uint16_t *src,int x,int y,unsigned w,unsigned h,const int *occluders,unsigned count){
 if(!dst||!src||!w||!h||w>800||h>480||count>64||(count&&!occluders)||x < -800||x>800||y < -480||y>480)return -1;
 for(unsigned i=0;i<count;++i)if(occluders[4*i+2]<0||occluders[4*i+2]>800||occluders[4*i+3]<0||occluders[4*i+3]>480||occluders[4*i]<-800||occluders[4*i]>800||occluders[4*i+1]<-480||occluders[4*i+1]>480)return -1;
 int left=x<0?0:x,right=x+(int)w;if(right>800)right=800;
 for(unsigned row=0;row<h;++row){int yy=y+(int)row;if(yy<0||yy>=480)continue;
  for(int at=left;at<right;){int end=right,skip=at;
   for(unsigned i=0;i<count;++i){const int *r=occluders+i*4;if(yy<r[1]||yy>=r[1]+r[3])continue;
    if(r[0]<=at&&r[0]+r[2]>skip)skip=r[0]+r[2];else if(r[0]>at&&r[0]<end)end=r[0];
   }
   if(skip>at){at=skip;continue;}
   memcpy(dst+yy*800+at,src+row*w+(at-x),(end-at)*2);at=end;
  }
 }
 return 0;
}

/* Cached native pixel layers. RGB565 plus straight alpha8; no image-to-cell path.
 * The coverage mask limits replay to regions replaced by direct pixel apps.
 * Elsewhere the retained desktop image is already complete. */
#include <stdlib.h>
static unsigned pixel_canvas_width=800,pixel_canvas_height=480;
int pocket_pixel_canvas_size(unsigned width,unsigned height){if(!width||width>4096||!height||height>4096)return -1;pixel_canvas_width=width;pixel_canvas_height=height;return 0;}
#define PIXEL_W ((int)pixel_canvas_width)
#define PIXEL_H ((int)pixel_canvas_height)
struct pocket_pixel_layer {unsigned width,height;const uint32_t *coverage_codes;const unsigned char *coverage;unsigned coverage_count;GLuint exact_program,exact_background;GLuint textures[104];unsigned texture_count;uint32_t pixels[];};
void *pocket_pixel_layer_new(unsigned cols,unsigned rows){
 if(!cols||cols>512||!rows||rows>256)return NULL;
 struct pocket_pixel_layer *p=calloc(1,sizeof(*p)+(size_t)cols*8*rows*16*4);
 if(p){p->width=cols*8;p->height=rows*16;}return p;
}
/* Borrowed read-only RGB565+alpha storage for the Mac Metal compositor.
 * The layer owner keeps the allocation alive throughout composition; rebuilding
 * updates these pixels in place. The pointer expires at layer_free, never cache
 * it past the frame or free it from the presentation consumer. */
int pocket_mac_layer_view(const void *handle,unsigned *width,unsigned *height,const uint32_t **pixels){
 const struct pocket_pixel_layer *p=handle;
 if(!p||!width||!height||!pixels||!p->width||p->width>4096||!p->height||p->height>4096)return -1;
 *width=p->width;*height=p->height;*pixels=p->pixels;return 0;
}
static void pixel_textures_clear(struct pocket_pixel_layer *p){if(p->exact_program){glDeleteProgram(p->exact_program);p->exact_program=0;}if(p->exact_background){glDeleteTextures(1,&p->exact_background);p->exact_background=0;}if(p->texture_count)glDeleteTextures(p->texture_count,p->textures);p->texture_count=0;}
void pocket_pixel_layer_free(void *handle){struct pocket_pixel_layer *p=handle;if(p)pixel_textures_clear(p);free(p);}
static int pixel_glyph(const uint32_t *codes,unsigned n,uint32_t glyph){
 unsigned lo=0,hi=n;while(lo<hi){unsigned m=lo+(hi-lo)/2;if(codes[m]<glyph)lo=m+1;else hi=m;}
 return lo<n&&codes[lo]==glyph?(int)lo:-1;
}
int pocket_pixel_layer_font_coverage(void *handle,const uint32_t *codes,const unsigned char *coverage,unsigned count){
 struct pocket_pixel_layer *p=handle;if(!p||count>1024||(count&&(!codes||!coverage)))return -1;
 for(unsigned i=0;i<count;++i)if(codes[i]<32||codes[i]>126||(i&&codes[i]<=codes[i-1]))return -1;
 p->coverage_codes=codes;p->coverage=coverage;p->coverage_count=count;return 0;
}
static unsigned pixel_rgb565(uint64_t v){return ((v>>8)&0xf800)|((v>>5)&0x7e0)|((v>>3)&31);}
int pocket_pixel_layer_build(void *handle,const void *data,size_t bytes,const uint32_t *codes,const unsigned char *font,unsigned glyphs,const uint32_t *palette,unsigned palettes,unsigned fallback,unsigned fill,unsigned opacity){
 struct pocket_pixel_layer *p=handle;const unsigned char *raw=data;
 if(!p||!raw||!codes||!font||!glyphs||glyphs>65536||!palette||!palettes||palettes>256||fallback>65535||fill>1||opacity>255||bytes!=(size_t)(p->width/8)*(p->height/16)*16)return -1;
 unsigned n=(unsigned)(bytes/16);
 for(unsigned i=0;i<n;++i){uint32_t index,ch;uint64_t ink;memcpy(&index,raw+i*16,4);memcpy(&ch,raw+i*16+4,4);memcpy(&ink,raw+i*16+8,8);
  if(index!=i||pixel_glyph(codes,glyphs,ch)<0||(ink<(UINT64_C(1)<<24)&&ink>=palettes)||(ink&(UINT64_C(1)<<55)))return -1;
  if(ink>=(UINT64_C(1)<<49)&&(!(ink&(UINT64_C(1)<<49))||!(ink&(UINT64_C(1)<<48))||((ink>>50)&3)<1||((ink>>50)&3)>2||((ink>>50)&3)>=palettes||(ink&~((UINT64_C(1)<<53)-1))))return -1;
 }
 pixel_textures_clear(p);
 for(unsigned i=0;i<n;++i){uint32_t ch,colors;uint64_t ink;memcpy(&ch,raw+i*16+4,4);memcpy(&ink,raw+i*16+8,8);
  unsigned alpha=fill?opacity:0;
  if(ink&(UINT64_C(1)<<49)){colors=(palette[(ink>>50)&3]&65535)|(pixel_rgb565(ink)<<16);alpha=255;}
  else if(ink>=(UINT64_C(1)<<48))colors=pixel_rgb565(ink>>24)|(pixel_rgb565(ink)<<16);
  else if(ink>=(UINT64_C(1)<<24))colors=pixel_rgb565(ink)|(fallback<<16);
  else colors=palette[ink];
  const unsigned char *mask=font+16*(unsigned)pixel_glyph(codes,glyphs,ch);
  unsigned x=(i%(p->width/8))*8,y=(i/(p->width/8))*16;
  int aa=pixel_glyph(p->coverage_codes,p->coverage_count,ch);
  const unsigned char *coverage=aa<0?NULL:p->coverage+128*(unsigned)aa;
  if(!coverage){
   /* The Nokia/default bitmap path keeps its original branch-only hot loop. */
   for(unsigned row=0;row<16;++row)for(unsigned col=0;col<8;++col)
    p->pixels[(y+row)*p->width+x+col]=(mask[row]&(128>>col))?(colors&65535)|(255U<<16):(colors>>16)|(alpha<<16);
   continue;
  }
  for(unsigned row=0;row<16;++row)for(unsigned col=0;col<8;++col){
   unsigned a=coverage[row*8+col];
   unsigned out_a=a+(alpha*(255-a)+127)/255;
   unsigned fg=colors&65535,bg=colors>>16;
   /* Cached straight-alpha layer: blend foreground coverage with the window
    * material once at rebuild, then composite that layer normally. */
   unsigned weight=out_a?(a*255+out_a/2)/out_a:0;
   unsigned red=((fg>>11)*weight+(bg>>11)*(255-weight)+127)/255;
   unsigned green=(((fg>>5)&63)*weight+((bg>>5)&63)*(255-weight)+127)/255;
   unsigned blue=((fg&31)*weight+(bg&31)*(255-weight)+127)/255;
   p->pixels[(y+row)*p->width+x+col]=(red<<11)|(green<<5)|blue|(out_a<<16);
  }
 }
 return 0;
}
static uint16_t pixel_over(uint16_t dst,unsigned source,unsigned alpha){
 if(alpha==255)return (uint16_t)source;
 if(!alpha)return dst;
 unsigned inv=255-alpha;
 unsigned r=(((source>>11)&31)*alpha+(dst>>11)*inv+127)/255;
 unsigned g=(((source>>5)&63)*alpha+((dst>>5)&63)*inv+127)/255;
 unsigned b=((source&31)*alpha+(dst&31)*inv+127)/255;
 return (uint16_t)((r<<11)|(g<<5)|b);
}
int pocket_pixel_image(uint16_t *canvas,unsigned char *coverage,const uint16_t *image,int x,int y,unsigned width,unsigned height){
 if(!canvas||!coverage||!image||!width||width>pixel_canvas_width||!height||height>pixel_canvas_height||x < -PIXEL_W||x>PIXEL_W||y < -PIXEL_H||y>PIXEL_H)return -1;
 int left=x<0?0:x,right=x+(int)width;if(right>PIXEL_W)right=PIXEL_W;if(left>=right)return 0;
 for(unsigned row=0;row<height;++row){int yy=y+(int)row;if(yy<0||yy>=PIXEL_H)continue;
  memcpy(canvas+yy*PIXEL_W+left,image+row*width+left-x,(right-left)*2);memset(coverage+yy*PIXEL_W+left,1,right-left);
 }
 return 0;
}
int pocket_pixel_layer_over(uint16_t *canvas,const unsigned char *coverage,const void *handle,int x,int y,int shadow_x,int shadow_y,unsigned shadow_alpha){
 const struct pocket_pixel_layer *p=handle;
 if(!canvas||!coverage||!p||x < -PIXEL_W||x>PIXEL_W||y < -PIXEL_H||y>PIXEL_H||shadow_x < -PIXEL_W||shadow_x>PIXEL_W||shadow_y < -PIXEL_H||shadow_y>PIXEL_H||shadow_alpha>255)return -1;
 if(shadow_alpha){
  int sx=x+shadow_x,sy=y+shadow_y,left=sx<0?0:sx,right=sx+(int)p->width;if(right>PIXEL_W)right=PIXEL_W;
  for(unsigned row=0;row<p->height;++row){int yy=sy+(int)row;if(yy<0||yy>=PIXEL_H)continue;
   for(int xx=left;xx<right;++xx){if(xx>=x&&xx<x+(int)p->width&&yy>=y&&yy<y+(int)p->height)continue;
    unsigned at=yy*PIXEL_W+xx;if(coverage[at])canvas[at]=pixel_over(canvas[at],0,shadow_alpha);
   }
  }
 }
 int left=x<0?0:x,right=x+(int)p->width;if(right>PIXEL_W)right=PIXEL_W;
 for(unsigned row=0;row<p->height;++row){int yy=y+(int)row;if(yy<0||yy>=PIXEL_H)continue;
  for(int xx=left;xx<right;++xx){unsigned at=yy*PIXEL_W+xx;if(!coverage[at])continue;unsigned src=p->pixels[row*p->width+xx-x];canvas[at]=pixel_over(canvas[at],src&65535,(src>>16)&255);}
 }
 return 0;
}
int pocket_pixel_layer_outline(void *handle,const uint32_t *glyphs6,const uint32_t *codes,const unsigned char *font,unsigned glyphs,unsigned color){
 struct pocket_pixel_layer *p=handle;int ids[6];
 if(!p||!glyphs6||!codes||!font||!glyphs||glyphs>65536||color>65535)return -1;
 for(unsigned i=0;i<6;++i){ids[i]=pixel_glyph(codes,glyphs,glyphs6[i]);if(ids[i]<0)return -1;}
 pixel_textures_clear(p);
 memset(p->pixels,0,(size_t)p->width*p->height*4);
 unsigned cols=p->width/8,rows=p->height/16;
 for(unsigned y=0;y<rows;++y)for(unsigned x=0;x<cols;++x){
  if(x&&x+1<cols&&y&&y+1<rows)continue;
  unsigned which=y==0?(x==0?0:x+1==cols?1:4):y+1==rows?(x==0?2:x+1==cols?3:4):5;
  const unsigned char *mask=font+16*ids[which];
  for(unsigned yy=0;yy<16;++yy)for(unsigned xx=0;xx<8;++xx)if(mask[yy]&(128>>xx))p->pixels[(y*16+yy)*p->width+x*8+xx]=color|(255U<<16);
 }
 return 0;
}

/* Local candidate: cached64x64 RGBA resources, nearest sampling, source-over.
 * Caller owns the current400x400 target, ordering and its final readback.
 * Never enable for MBX until mixed3D/2D state is admitted by that driver.
 * Returns texture draws; no glFinish, readback or CPU image composition. */
int pocket_pixel_layer_gpu(void *handle,int x,int y){
 struct pocket_pixel_layer *p=handle;
 if(!p||x < -800||x>800||y < -480||y>480||!OSMesaGetCurrentContext())return -1;
 const char *renderer=(const char*)glGetString(GL_RENDERER);
 if(!renderer||strstr(renderer,"Nokia MBX"))return -3;
 unsigned nx=(p->width+63)/64,ny=(p->height+63)/64;
 if(nx*ny>104)return -1;
 if(!p->texture_count){
  unsigned char rgba[64*64*4];glGenTextures(nx*ny,p->textures);p->texture_count=nx*ny;
  glPixelStorei(GL_UNPACK_ALIGNMENT,1);
  for(unsigned ty=0;ty<ny;++ty)for(unsigned tx=0;tx<nx;++tx){
   memset(rgba,0,sizeof(rgba));
   for(unsigned yy=0;yy<64&&ty*64+yy<p->height;++yy)for(unsigned xx=0;xx<64&&tx*64+xx<p->width;++xx){
    unsigned v=p->pixels[(ty*64+yy)*p->width+tx*64+xx],at=(yy*64+xx)*4;
    unsigned r=(v>>11)&31,g=(v>>5)&63,b=v&31;
    rgba[at]=(r<<3)|(r>>2);rgba[at+1]=(g<<2)|(g>>4);rgba[at+2]=(b<<3)|(b>>2);rgba[at+3]=(v>>16)&255;
   }
   glBindTexture(GL_TEXTURE_2D,p->textures[ty*nx+tx]);
   glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
   glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
   glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,64,64,0,GL_RGBA,GL_UNSIGNED_BYTE,rgba);
  }
  if(glGetError()!=GL_NO_ERROR){pixel_textures_clear(p);return -2;}
 }
 if(!p->exact_program){
  const char *source="#version 120\nuniform sampler2D foreground_image;uniform sampler2D background_image;void main(){vec4 s=texture2D(foreground_image,gl_TexCoord[0].xy);vec3 d=texture2D(background_image,gl_FragCoord.xy/512.0).rgb;vec3 divisor=vec3(8.0,4.0,8.0);vec3 si=floor(floor(s.rgb*255.0+0.5)/divisor);vec3 di=floor(floor(d*255.0+0.5)/divisor);float a=floor(s.a*255.0+0.5);vec3 q=floor((si*a+di*(255.0-a)+127.0)/255.0);vec3 encoded_color=q*divisor+floor(q/vec3(4.0,16.0,4.0));gl_FragColor=vec4(encoded_color/255.0,1.0);}\n";
  GLuint shader=glCreateShader(GL_FRAGMENT_SHADER);glShaderSource(shader,1,&source,NULL);glCompileShader(shader);GLint ok=0;glGetShaderiv(shader,GL_COMPILE_STATUS,&ok);if(!ok){glDeleteShader(shader);return -4;}
  p->exact_program=glCreateProgram();glAttachShader(p->exact_program,shader);glLinkProgram(p->exact_program);glDeleteShader(shader);glGetProgramiv(p->exact_program,GL_LINK_STATUS,&ok);if(!ok)return -4;
  glGenTextures(1,&p->exact_background);glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D,p->exact_background);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA8,512,512,0,GL_RGBA,GL_UNSIGNED_BYTE,NULL);glActiveTexture(GL_TEXTURE0);
 }
 glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D,p->exact_background);glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,400,400);glActiveTexture(GL_TEXTURE0);
 glUseProgram(p->exact_program);glUniform1i(glGetUniformLocation(p->exact_program,"foreground_image"),0);glUniform1i(glGetUniformLocation(p->exact_program,"background_image"),1);
 glViewport(0,0,400,400);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,400,400,0,-1,1);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 glMatrixMode(GL_TEXTURE);glLoadIdentity();glMatrixMode(GL_MODELVIEW);
 glDisable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_LIGHTING);glDisable(GL_VERTEX_PROGRAM_ARB);glDisable(GL_CULL_FACE);glDisable(GL_DITHER);glDisable(GL_SCISSOR_TEST);
 glEnable(GL_TEXTURE_2D);glTexEnvi(GL_TEXTURE_ENV,GL_TEXTURE_ENV_MODE,GL_REPLACE);glDisable(GL_BLEND);
 glDisableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_TEXTURE_COORD_ARRAY);
 unsigned draws=0;
 for(unsigned ty=0;ty<ny;++ty)for(unsigned tx=0;tx<nx;++tx){
  int left=x+tx*64,top=y+ty*64;unsigned w=p->width-tx*64,h=p->height-ty*64;if(w>64)w=64;if(h>64)h=64;
  if(left>=400||top>=400||left+(int)w<=0||top+(int)h<=0)continue;
  float right=left+w,bottom=top+h,u=w/64.f,v=h/64.f;
  const float vertices[]={left,top,0,right,top,0,left,bottom,0,right,top,0,right,bottom,0,left,bottom,0};
  const float uv[]={0,0,0,1,u,0,0,1,0,v,0,1,u,0,0,1,u,v,0,1,0,v,0,1};
  glBindTexture(GL_TEXTURE_2D,p->textures[ty*nx+tx]);glVertexPointer(3,GL_FLOAT,0,vertices);glTexCoordPointer(4,GL_FLOAT,0,uv);glDrawArrays(GL_TRIANGLES,0,6);++draws;
 }
 glUseProgram(0);glDisable(GL_TEXTURE_2D);glDisable(GL_BLEND);glDisableClientState(GL_TEXTURE_COORD_ARRAY);glDepthMask(GL_TRUE);
 return glGetError()==GL_NO_ERROR?(int)draws:-2;
}
/* One cached layer including its non-overlapping shadow. No per-frame packing. */
void *pocket_pixel_layer_with_shadow(const void *handle,int dx,int dy,unsigned alpha){
 const struct pocket_pixel_layer *src=handle;
 if(!src||dx < -4096||dx>4096||dy < -4096||dy>4096||alpha>255)return NULL;
 unsigned w=src->width+(unsigned)abs(dx),h=src->height+(unsigned)abs(dy);
 if(w>4096||h>4096||((w+63)/64)*((h+63)/64)>104)return NULL;
 struct pocket_pixel_layer *out=calloc(1,sizeof(*out)+(size_t)w*h*4);if(!out)return NULL;out->width=w;out->height=h;
 unsigned wx=dx<0?-dx:0,wy=dy<0?-dy:0,sx=dx>0?dx:0,sy=dy>0?dy:0;
 for(unsigned y=0;y<src->height;++y)for(unsigned x=0;x<src->width;++x){
  unsigned xx=sx+x,yy=sy+y;if(xx>=wx&&xx<wx+src->width&&yy>=wy&&yy<wy+src->height)continue;
  out->pixels[yy*w+xx]=alpha<<16;
 }
 for(unsigned y=0;y<src->height;++y)memcpy(out->pixels+(wy+y)*w+wx,src->pixels+y*src->width,src->width*4);
 return out;
}
