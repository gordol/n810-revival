/* SPDX-FileCopyrightText: 2026 Thomas Gordon Lowrey IV
 * SPDX-License-Identifier: GPL-2.0-or-later */
/* Native map presentation: sampled terrain, clipped geographic lines, then
 * semantic labels. Roads never pass through a character-cell glyph encoder. */
#include <stdint.h>
#include <stddef.h>
#include <math.h>
#include <stdlib.h>
struct map_sample {uint32_t ch,pad;uint64_t ink;};
struct map_mark {uint32_t index,ch;uint64_t ink;};
static uint16_t map_color(uint64_t rgb){return (uint16_t)(((rgb>>8)&0xf800)|((rgb>>5)&0x7e0)|((rgb>>3)&31));}
int pocket_map_base(uint16_t *out,size_t capacity,const struct map_sample *cells,unsigned cols,unsigned rows){
 if(!out||!cells||!cols||cols>512||!rows||rows>256||capacity<(size_t)cols*8*rows*16)return -1;
 unsigned width=cols*8;
 for(unsigned y=0;y<rows*16;++y)for(unsigned x=0;x<width;++x){
  const struct map_sample *cell=cells+(y/16)*cols+x/8;
  int front=cell->ch==0x2588||(cell->ch==0x2580&&y%16<8)||(cell->ch==0x2584&&y%16>=8);
  out[y*width+x]=map_color(front?cell->ink>>24:cell->ink);
 }
 return 0;
}
static unsigned map_outcode(double x,double y,unsigned width,unsigned height){return (x<0?1:x>width-1?2:0)|(y<0?4:y>height-1?8:0);}
int pocket_map_lines(uint16_t *out,size_t capacity,unsigned width,unsigned height,const double *segments,unsigned count,unsigned color){
 if(!out||!width||width>4096||!height||height>4096||capacity<(size_t)width*height||count>250000||(count&&!segments)||color>65535)return -1;
 for(unsigned i=0;i<count*4;++i)if(!isfinite(segments[i])||fabs(segments[i])>1e12)return -1;
 for(unsigned i=0;i<count;++i){
  double x=segments[i*4],y=segments[i*4+1],xx=segments[i*4+2],yy=segments[i*4+3];int accepted=0;
  for(unsigned step=0;step<8;++step){
   unsigned a=map_outcode(x,y,width,height),b=map_outcode(xx,yy,width,height);
   if(!(a|b)){accepted=1;break;}if(a&b)break;
   unsigned outside=a?a:b;double nx,ny;
   if(outside&12){ny=outside&4?0:height-1;nx=x+(xx-x)*(ny-y)/(yy-y);}
   else{nx=outside&1?0:width-1;ny=y+(yy-y)*(nx-x)/(xx-x);}
   if(outside==a){x=nx;y=ny;}else{xx=nx;yy=ny;}
  }
  if(!accepted)continue;
  int x0=(int)lround(x),y0=(int)lround(y),x1=(int)lround(xx),y1=(int)lround(yy);
  int dx=abs(x1-x0),dy=-abs(y1-y0),sx=x0<x1?1:-1,sy=y0<y1?1:-1,error=dx+dy;
  for(;;){out[(unsigned)y0*width+(unsigned)x0]=(uint16_t)color;if(x0==x1&&y0==y1)break;int twice=2*error;if(twice>=dy){error+=dy;x0+=sx;}if(twice<=dx){error+=dx;y0+=sy;}}
 }
 return 0;
}
int pocket_map_marks(uint16_t *out,size_t capacity,unsigned cols,unsigned rows,const struct map_mark *marks,unsigned count,const unsigned char *glyphs){
 if(!out||!cols||cols>512||!rows||rows>256||capacity<(size_t)cols*8*rows*16||count>cols*rows||(count&&(!marks||!glyphs)))return -1;
 for(unsigned i=0;i<count;++i)if(marks[i].index>=cols*rows)return -1;
 for(unsigned i=0;i<count;++i){
  unsigned x=(marks[i].index%cols)*8,y=(marks[i].index/cols)*16;uint16_t fg=map_color(marks[i].ink>>24),bg=map_color(marks[i].ink);
  for(unsigned yy=0;yy<16;++yy)for(unsigned xx=0;xx<8;++xx)out[(y+yy)*cols*8+x+xx]=(glyphs[i*16+yy]&(128>>xx))?fg:bg;
 }
 return 0;
}
