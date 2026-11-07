/* SPDX-License-Identifier: MIT */
#include "cells.h"
#include <string.h>
int mbx_cell_rgb565(struct mbx_surface *s,unsigned x,unsigned y,
                   unsigned w,unsigned h,const unsigned char *g,size_t bytes,
                   uint16_t fg,uint16_t bg)
{
    if(!s||!s->pixels||!g||!w||!h||w>32||h>32||!s->stride||
       s->width>s->stride/2||s->height>s->bytes/s->stride||x>s->width||y>s->height||
       w>s->width-x||h>s->height-y||bytes<(size_t)((w+7)/8)*h)return -1;
    unsigned stride=(w+7)/8;
    for(unsigned row=0;row<h;++row)for(unsigned col=0;col<w;++col){
        uint16_t pixel=(g[row*stride+col/8]&(0x80>>(col%8)))?fg:bg;
        memcpy((unsigned char *)s->pixels+(y+row)*s->stride+(size_t)(x+col)*2,&pixel,2);
    }
    return 0;
}

/* Exact native front -> glyph pixels. Caller retains all immutable inputs.
 * Records are index:u32, glyph:u32, ink:u64; palette words are bg:16|fg:16.
 * Unsupported styles are rejected by the adapter before this call. */
struct mbx_cell_seen {uint32_t glyph,colors,valid;};
static uint16_t cell_rgb(uint64_t v){return ((v>>8)&0xf800)|((v>>5)&0x7e0)|((v>>3)&31);}
static int font_index(const uint32_t *codes,unsigned count,uint32_t ch){
 unsigned lo=0,hi=count;while(lo<hi){unsigned m=lo+(hi-lo)/2;if(codes[m]<ch)lo=m+1;else hi=m;}
 return lo<count&&codes[lo]==ch?(int)lo:-1;
}
int mbx_cells_rgb565(struct mbx_surface *s,const void *data,size_t bytes,
 const uint32_t *codes,const unsigned char *glyphs,unsigned count,unsigned font_height,
 const uint32_t *palette,unsigned palettes,uint16_t rgb_background,struct mbx_cell_seen *seen,unsigned slots){
 if(!s||!s->pixels||!s->stride||!s->width||!s->height||s->width>65536||s->height>65536||!codes||!glyphs||!palette||!seen||!font_height||font_height>32||!count||count>65536||!palettes||palettes>256||bytes>65536*16||bytes%16||(bytes&&!data)||s->width%8||s->height%font_height||slots>65536||(uint64_t)slots!=(uint64_t)(s->width/8)*(s->height/font_height)||s->width>s->stride/2||s->height>s->bytes/s->stride)return -1;
 const unsigned char *records=data;unsigned n=bytes/16;if(n>65536)return -1;
 for(unsigned i=0;i<n;++i){uint32_t index,ch;uint64_t ink;memcpy(&index,records+i*16,4);memcpy(&ch,records+i*16+4,4);memcpy(&ink,records+i*16+8,8);
  if(index>=slots||font_index(codes,count,ch)<0||(ink<(UINT64_C(1)<<24)&&ink>=palettes)||(ink&(UINT64_C(1)<<55)))return -1;
  if(ink>=(UINT64_C(1)<<49)&&(!(ink&(UINT64_C(1)<<49))||!(ink&(UINT64_C(1)<<48))||((ink>>50)&3)<1||((ink>>50)&3)>2||((ink>>50)&3)>=palettes||(ink&~((UINT64_C(1)<<53)-1))))return -1;
 }
 unsigned drawn=0,cols=s->width/8;
 for(unsigned i=0;i<n;++i){uint32_t index,ch,colors;uint64_t ink;memcpy(&index,records+i*16,4);memcpy(&ch,records+i*16+4,4);memcpy(&ink,records+i*16+8,8);
  if(ink&(UINT64_C(1)<<49))colors=(palette[(ink>>50)&3]&65535)|((uint32_t)cell_rgb(ink)<<16);
  else if(ink>=(UINT64_C(1)<<48))colors=cell_rgb(ink>>24)|((uint32_t)cell_rgb(ink)<<16);
  else if(ink>=(UINT64_C(1)<<24))colors=cell_rgb(ink)|((uint32_t)rgb_background<<16);
  else colors=palette[ink];
  if(seen[index].valid&&seen[index].glyph==ch&&seen[index].colors==colors)continue;
  int j=font_index(codes,count,ch);
  if(mbx_cell_rgb565(s,(index%cols)*8,(index/cols)*font_height,8,font_height,glyphs+(unsigned)j*font_height,font_height,colors&65535,colors>>16))return -1;
  seen[index]=(struct mbx_cell_seen){ch,colors,1};++drawn;
 }
 return (int)drawn;
}
