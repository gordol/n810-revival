/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Retained console-cell descriptions with explicit native CPU or Mesa/MBX raster.
 * Bounded subdivision respects the accepted400x400/2048-triangle service.
 * This first backend favors exact output; timings must be measured on device. */
#define GL_GLEXT_PROTOTYPES
#ifdef POCKET_DESKTOP_GL
#include "desktop_context.h"
#else
#include <GL/osmesa.h>
#endif
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
struct cell {uint16_t fg,bg;unsigned char mask[16],valid,dirty;uint32_t code;};
struct renderer {OSMesaContext gl;uint16_t image[160000];struct cell *cells;unsigned cols,rows;float positions[6144*3],colors[6144*4];unsigned rectangles,jobs;float glyph_depth;GLuint program;const uint32_t *coverage_codes;const unsigned char *coverage;unsigned coverage_count;int defer_text,cpu_cells;};
static const char *failure="MBX cell renderer rejected input";
const char *pocket_mbx_error(void){return failure;}
void *pocket_mbx_open_cells(int require_gpu,int cpu_cells){
 struct renderer *r=calloc(1,sizeof(*r));if(!r)return NULL;
 r->cpu_cells=!!cpu_cells;
 if(r->cpu_cells){
  r->cols=100;r->rows=30;r->cells=calloc(r->cols*r->rows,sizeof(*r->cells));
  if(!r->cells){free(r);return NULL;}
  return r;
 }
 r->gl=OSMesaCreateContextExt(OSMESA_RGB_565,24,0,0,NULL);
 if(!r->gl||!OSMesaMakeCurrent(r->gl,r->image,GL_UNSIGNED_SHORT_5_6_5,400,400)){failure="OSMesa context unavailable";if(r->gl)OSMesaDestroyContext(r->gl);free(r);return NULL;}
 const char *name=(const char*)glGetString(GL_RENDERER);
 #ifdef POCKET_DESKTOP_GL
 if(require_gpu&&(!name||strstr(name,"llvmpipe")||strstr(name,"softpipe")||strstr(name,"Software")))
#else
 if(require_gpu&&(!name||!strstr(name,"Nokia MBX GPU transform")))
#endif
 {failure="Actual MBX service required; CPU fallback refused";OSMesaDestroyContext(r->gl);free(r);return NULL;}
 /* The verified second VGP attribute delivers xyz. Cells are opaque, so
  * supply alpha=1 as a constant instead of reading an undelivered fourth lane. */
 const char *program="!!ARBvp1.0\n"
  "DP4 result.position.x, state.matrix.mvp.row[0], vertex.position;\n"
  "DP4 result.position.y, state.matrix.mvp.row[1], vertex.position;\n"
  "DP4 result.position.z, state.matrix.mvp.row[2], vertex.position;\n"
  "DP4 result.position.w, state.matrix.mvp.row[3], vertex.position;\n"
  "MOV result.color.xyz, vertex.color;\n"
  "MOV result.color.w, {1}.x;\nEND\n";
 glGenProgramsARB(1,&r->program);glBindProgramARB(GL_VERTEX_PROGRAM_ARB,r->program);
 glProgramStringARB(GL_VERTEX_PROGRAM_ARB,GL_PROGRAM_FORMAT_ASCII_ARB,(GLsizei)strlen(program),program);
 if(glGetError()!=GL_NO_ERROR){failure="Opaque cell vertex program rejected";OSMesaDestroyContext(r->gl);free(r);return NULL;}
 glEnable(GL_VERTEX_PROGRAM_ARB);
 r->cols=100;r->rows=30;r->cells=calloc(r->cols*r->rows,sizeof(*r->cells));
 if(!r->cells){failure="Cell allocation failed";OSMesaDestroyContext(r->gl);free(r);return NULL;}
 OSMesaPixelStore(OSMESA_Y_UP,0);return r;
}
void *pocket_mbx_open(int require_gpu){return pocket_mbx_open_cells(require_gpu,0);}
int pocket_mbx_resize(void *ptr,unsigned cols,unsigned rows){
 struct renderer *r=ptr;if(!r||!cols||!rows||cols>512||rows>256)return -1;
 if(cols==r->cols&&rows==r->rows)return 0;
 struct cell *cells=calloc((size_t)cols*rows,sizeof(*cells));if(!cells)return -1;
 free(r->cells);r->cells=cells;r->cols=cols;r->rows=rows;return 0;
}
int pocket_mbx_stage(void *ptr,unsigned index,const unsigned char *mask,unsigned fg,unsigned bg){
 struct renderer *r=ptr;if(!r||index>=r->cols*r->rows||!mask||fg>65535||bg>65535)return -1;
 struct cell *c=r->cells+index;
 if(!c->valid||c->fg!=fg||c->bg!=bg||memcmp(c->mask,mask,16)){c->fg=fg;c->bg=bg;memcpy(c->mask,mask,16);c->valid=c->dirty=1;}
 return 0;
}
/* Existing native export format: index:u32, glyph:u32, ink:u64. */
static int find_glyph(const uint32_t *codes,unsigned count,uint32_t ch){
 unsigned lo=0,hi=count;while(lo<hi){unsigned m=lo+(hi-lo)/2;if(codes[m]<ch)lo=m+1;else hi=m;}
 return lo<count&&codes[lo]==ch?(int)lo:-1;
}
/* Immutable font coverage belongs to the renderer's Python font object. */
int pocket_mbx_font_coverage(void *ptr,const uint32_t *codes,const unsigned char *coverage,unsigned count){
 struct renderer *r=ptr;if(!r||count>1024||(count&&(!codes||!coverage)))return -1;
 for(unsigned i=0;i<count;++i)if(codes[i]<32||codes[i]>126||(i&&codes[i]<=codes[i-1]))return -1;
 r->coverage_codes=codes;r->coverage=coverage;r->coverage_count=count;
 for(unsigned i=0;i<r->cols*r->rows;++i)r->cells[i].dirty=1;
 return 0;
}
static uint16_t glyph_color(unsigned fg,unsigned bg,unsigned a){
 unsigned red=(((fg>>11)*a+(bg>>11)*(255-a)+127)/255);
 unsigned green=((((fg>>5)&63)*a+((bg>>5)&63)*(255-a)+127)/255);
 unsigned blue=(((fg&31)*a+(bg&31)*(255-a)+127)/255);
 return (uint16_t)((red<<11)|(green<<5)|blue);
}
static uint16_t rgb565(uint64_t v){return ((v>>8)&0xf800)|((v>>5)&0x7e0)|((v>>3)&31);}
int pocket_mbx_stage_batch(void *ptr,const void *data,size_t bytes,const uint32_t *codes,
 const unsigned char *glyphs,unsigned count,const uint32_t *palette,unsigned palettes,unsigned fallback){
 struct renderer *r=ptr;const unsigned char *records=data;
 if(!r||(bytes&&!data)||bytes%16||bytes>(size_t)r->cols*r->rows*16||!codes||!glyphs||!count||count>65536||!palette||!palettes||palettes>256||fallback>65535)return -1;
 for(unsigned i=0;i<bytes/16;++i){uint32_t index,ch;uint64_t ink;
  memcpy(&index,records+16*i,4);memcpy(&ch,records+16*i+4,4);memcpy(&ink,records+16*i+8,8);
  if(index>=r->cols*r->rows||find_glyph(codes,count,ch)<0||(ink<(UINT64_C(1)<<24)&&ink>=palettes)||(ink&(UINT64_C(1)<<55)))return -1;
  if(ink>=(UINT64_C(1)<<49)&&(!(ink&(UINT64_C(1)<<49))||!(ink&(UINT64_C(1)<<48))||((ink>>50)&3)<1||((ink>>50)&3)>2||((ink>>50)&3)>=palettes||(ink&~((UINT64_C(1)<<53)-1))))return -1;
 }
 unsigned changed=0;
 for(unsigned i=0;i<bytes/16;++i){uint32_t index,ch,colors;uint64_t ink;
  memcpy(&index,records+16*i,4);memcpy(&ch,records+16*i+4,4);memcpy(&ink,records+16*i+8,8);
  if(ink&(UINT64_C(1)<<49))colors=(palette[(ink>>50)&3]&65535)|((uint32_t)rgb565(ink)<<16);
  else if(ink>=(UINT64_C(1)<<48))colors=rgb565(ink>>24)|((uint32_t)rgb565(ink)<<16);
  else if(ink>=(UINT64_C(1)<<24))colors=rgb565(ink)|((uint32_t)fallback<<16);
  else colors=palette[ink];
  const unsigned char *mask=glyphs+16*(unsigned)find_glyph(codes,count,ch);struct cell *c=r->cells+index;
  if(!c->valid||c->code!=ch||c->fg!=(colors&65535)||c->bg!=(colors>>16)||memcmp(c->mask,mask,16)){
   pocket_mbx_stage(r,index,mask,colors&65535,colors>>16);c->code=ch;c->dirty=1;++changed;
  }
 }
 return (int)changed;
}
static void rectangle(struct renderer *r,unsigned x,unsigned y,unsigned w,unsigned h,unsigned color){
 const unsigned dx[6]={0,1,0,1,1,0},dy[6]={0,0,1,0,1,1};
 unsigned red=color>>11,green=(color>>5)&63,blue=color&31;
 float rgb[4]={((red<<3)|(red>>2))/255.f,((green<<2)|(green>>4))/255.f,((blue<<3)|(blue>>2))/255.f,1};
 for(unsigned k=0;k<6;++k){unsigned i=r->rectangles*6+k;r->positions[i*3]=x+w*dx[k];r->positions[i*3+1]=y+h*dy[k];r->positions[i*3+2]=r->glyph_depth;memcpy(r->colors+i*4,rgb,16);}
 ++r->rectangles;
}
/* Merge identical glyph spans on consecutive rows, exactly as the accepted
 * native glyph encoder. Counting and emission use the same bounded traversal. */
static unsigned glyph(struct renderer *r,const struct cell *c,unsigned x,unsigned y,int emit){
 if(c->fg==c->bg||(r->defer_text&&c->code>=32&&c->code<127))return 0;
 int aa=find_glyph(r->coverage_codes,r->coverage_count,c->code);
 if(aa>=0){
  const unsigned char *coverage=r->coverage+128*(unsigned)aa;unsigned count=0;
  for(unsigned row=0;row<16;++row)for(unsigned col=0;col<8;){
   unsigned a=coverage[row*8+col],start=col++;
   while(col<8&&coverage[row*8+col]==a)++col;
   if(!a)continue;
   unsigned color=glyph_color(c->fg,c->bg,a);if(color==c->bg)continue;
   if(emit)rectangle(r,x+start,y+row,col-start,1,color);
   ++count;
  }
  return count;
 }
 unsigned boxes[64][4],count=0;int previous[64],current[64];
 for(unsigned i=0;i<64;++i)previous[i]=-1;
 for(unsigned row=0;row<16;++row){
  for(unsigned i=0;i<64;++i)current[i]=-1;
  for(unsigned col=0;col<8;){
   if(!(c->mask[row]&(128>>col))){++col;continue;}
   unsigned start=col;while(col<8&&(c->mask[row]&(128>>col)))++col;
   unsigned key=start*8+col-1;int at=previous[key];
   if(at<0){at=(int)count++;boxes[at][0]=start;boxes[at][1]=row;boxes[at][2]=col-start;boxes[at][3]=1;}
   else ++boxes[at][3];
   current[key]=at;
  }
  memcpy(previous,current,sizeof(previous));
 }
 if(emit)for(unsigned i=0;i<count;++i)rectangle(r,x+boxes[i][0],y+boxes[i][1],boxes[i][2],boxes[i][3],c->fg);
 return count;
}
static int tile(struct renderer *r,uint16_t *canvas,unsigned x,unsigned y,unsigned w,unsigned h){
 unsigned count=0,dirty=0;
 for(unsigned j=0;j<h;++j)for(unsigned i=0;i<w;++i){struct cell *c=r->cells+(y+j)*r->cols+x+i;dirty|=c->dirty;count+=glyph(r,c,0,0,0);if(!i||c->bg!=(c-1)->bg)++count;}
 if(!dirty)return 0;
 if(count>1024){
  if(w>=h&&w>1){unsigned n=w/2;return tile(r,canvas,x,y,n,h)||tile(r,canvas,x+n,y,w-n,h)?-1:0;}
  if(h>1){unsigned n=h/2;return tile(r,canvas,x,y,w,n)||tile(r,canvas,x,y+n,w,h-n)?-1:0;}
  return -1;
 }
 r->rectangles=0;r->glyph_depth=0;
 /* Adjacent opaque backgrounds share one rectangle. Glyphs remain exact
  * and cannot cross their cell bounds, so drawing them afterward is equivalent. */
 for(unsigned j=0;j<h;++j)for(unsigned i=0;i<w;){
  unsigned first=i,color=r->cells[(y+j)*r->cols+x+i].bg;
  while(i<w&&r->cells[(y+j)*r->cols+x+i].bg==color)++i;
  rectangle(r,first*8,j*16,(i-first)*8,16,color);
 }
 r->glyph_depth=.5f;
 for(unsigned j=0;j<h;++j)for(unsigned i=0;i<w;++i){const struct cell *c=r->cells+(y+j)*r->cols+x+i;glyph(r,c,i*8,j*16,1);}
 glEnable(GL_VERTEX_PROGRAM_ARB);glBindProgramARB(GL_VERTEX_PROGRAM_ARB,r->program);
 glViewport(0,0,400,400);glMatrixMode(GL_PROJECTION);glLoadIdentity();glOrtho(0,400,400,0,-1,1);glMatrixMode(GL_MODELVIEW);glLoadIdentity();
 glDisable(GL_LIGHTING);glDisable(GL_TEXTURE_2D);glDisable(GL_CULL_FACE);glDisable(GL_DITHER);glDisable(GL_BLEND);glDepthMask(GL_TRUE);
#ifdef POCKET_DESKTOP_GL
 glDisable(GL_DEPTH_TEST);
#else
 /* The pinned Nokia backend supports LESS with writes. Put glyphs in front
  * of their opaque background instead of requiring a newer 2D driver state. */
 glEnable(GL_DEPTH_TEST);glDepthFunc(GL_LESS);
#endif
 glShadeModel(GL_SMOOTH);glClearColor(0,0,0,0);glClearDepth(1);glClear(GL_COLOR_BUFFER_BIT|GL_DEPTH_BUFFER_BIT);
 glEnableClientState(GL_VERTEX_ARRAY);glEnableClientState(GL_COLOR_ARRAY);glDisableClientState(GL_NORMAL_ARRAY);glDisableClientState(GL_TEXTURE_COORD_ARRAY);
 glVertexPointer(3,GL_FLOAT,0,r->positions);glColorPointer(4,GL_FLOAT,0,r->colors);
 for(unsigned first=0;first<r->rectangles;first+=128){unsigned n=r->rectangles-first;if(n>128)n=128;glDrawArrays(GL_TRIANGLES,first*6,n*6);}
 glFinish();if(glGetError()!=GL_NO_ERROR){failure="MBX draw failed; no CPU fallback";return -1;}++r->jobs;
 for(unsigned row=0;row<h*16;++row)memcpy(canvas+(y*16+row)*(r->cols*8)+x*8,r->image+row*400,w*16);
 return 0;
}
int pocket_mbx_render(void *ptr,uint16_t *canvas){
 struct renderer *r=ptr;if(!r||!canvas)return -1;
 for(unsigned i=0;i<r->cols*r->rows;++i)if(!r->cells[i].valid){failure="Incomplete retained cell frame";return -1;}
 /* Small opaque UI glyphs are cheaper as native pixel stores than hundreds
  * of GPU rectangles. Retain the same staging, coverage and damage contract;
  * direct image/3D applications keep their own presentation path. */
 if(r->cpu_cells){
  for(unsigned i=0;i<r->cols*r->rows;++i){
   struct cell *c=r->cells+i;if(!c->dirty)continue;
   int aa=find_glyph(r->coverage_codes,r->coverage_count,c->code);
   int hidden=r->defer_text&&c->code>=32&&c->code<127;
   for(unsigned y=0;y<16;++y)for(unsigned x=0;x<8;++x){
    unsigned a=hidden?0:aa>=0?r->coverage[128*(unsigned)aa+y*8+x]:(c->mask[y]&(128>>x)?255:0);
    canvas[((i/r->cols)*16+y)*r->cols*8+(i%r->cols)*8+x]=a==255?c->fg:a?glyph_color(c->fg,c->bg,a):c->bg;
   }
   c->dirty=0;
  }
  return 0;
 }
 for(unsigned y=0;y<r->rows;y+=25)for(unsigned x=0;x<r->cols;x+=50){
  unsigned w=r->cols-x,h=r->rows-y;if(w>50)w=50;if(h>25)h=25;
  if(tile(r,canvas,x,y,w,h))return -1;
 }
 for(unsigned i=0;i<r->cols*r->rows;++i)r->cells[i].dirty=0;
 return 0;
}
unsigned pocket_mbx_jobs(void *ptr){return ((struct renderer*)ptr)->jobs;}
void pocket_mbx_close(void *ptr){struct renderer *r=ptr;if(r){if(r->gl)OSMesaDestroyContext(r->gl);free(r->cells);free(r);}}
/* Model viewport to physical desktop mapping, validated before staging. */
int pocket_mbx_stage_region(void *ptr,const void *data,size_t bytes,const uint32_t *codes,const unsigned char *glyphs,unsigned count,const uint32_t *palette,unsigned palettes,unsigned fallback,unsigned width,unsigned height,unsigned x,unsigned y){
 struct renderer *r=ptr;
 if(!r||!width||!height||width>r->cols||height>r->rows||x>r->cols-width||y>r->rows-height||bytes>(size_t)width*height*16||bytes%16||(bytes&&!data))return -1;
 unsigned char *records=bytes?malloc(bytes):NULL;if(bytes&&!records)return -1;if(bytes)memcpy(records,data,bytes);
 for(size_t at=0;at<bytes;at+=16){uint32_t index;memcpy(&index,records+at,4);if(index>=width*height){free(records);return -1;}index=(y+index/width)*r->cols+x+index%width;memcpy(records+at,&index,4);}
 int result=pocket_mbx_stage_batch(ptr,records,bytes,codes,glyphs,count,palette,palettes,fallback);free(records);return result;
}
int pocket_mbx_text(void *ptr,unsigned x,unsigned y,const uint32_t *text,unsigned length,const uint32_t *codes,const unsigned char *glyphs,unsigned count,unsigned fg,unsigned bg){
 struct renderer *r=ptr;
 if(!r||x>=r->cols||y>=r->rows||length>r->cols-x||!text||!codes||!glyphs||!count||fg>65535||bg>65535)return -1;
 for(unsigned i=0;i<length;++i)if(find_glyph(codes,count,text[i])<0)return -1;
 for(unsigned i=0;i<length;++i){
  unsigned index=y*r->cols+x+i;pocket_mbx_stage(ptr,index,glyphs+16*find_glyph(codes,count,text[i]),fg,bg);
  if(r->cells[index].code!=text[i])r->cells[index].dirty=1;
  r->cells[index].code=text[i];
 }
 return 0;
}

void pocket_mbx_blank(void *ptr){struct renderer *r=ptr;if(!r)return;memset(r->cells,0,(size_t)r->cols*r->rows*sizeof(*r->cells));for(unsigned i=0;i<r->cols*r->rows;++i)r->cells[i].valid=r->cells[i].dirty=1;}

/* Presentation-only switch: cell descriptions and Nokia geometry are unchanged. */
int pocket_mbx_defer_text(void *ptr,int enabled){
 struct renderer *r=ptr;if(!r)return -1;enabled=!!enabled;
 if(r->defer_text!=enabled){r->defer_text=enabled;for(unsigned i=0;i<r->cols*r->rows;i++)r->cells[i].dirty=1;}
 return 0;
}
int pocket_mbx_text_cells(void *ptr,uint32_t *out,size_t count){
 struct renderer *r=ptr;if(!r||!out||count!=(size_t)r->cols*r->rows*2)return -1;
 for(unsigned i=0;i<r->cols*r->rows;i++){out[i*2]=r->cells[i].code;out[i*2+1]=r->cells[i].fg;}
 return 0;
}

int pocket_mbx_cell_colors(void *ptr,uint32_t *out,size_t count){struct renderer *r=ptr;if(!r||!out||count!=(size_t)r->cols*r->rows*2)return -1;for(size_t i=0;i<count/2;i++){out[i*2]=r->cells[i].code;out[i*2+1]=r->cells[i].fg|((uint32_t)r->cells[i].bg<<16);}return 0;}
