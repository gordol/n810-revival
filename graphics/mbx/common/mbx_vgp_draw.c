/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_draw.h"
#include "mbx_vgp_isa.h"
static int finite_word(unsigned n){return (n&0x7fffffffU)<0x7f800000U;}
static void emit(struct mbx_command *c,unsigned *at,unsigned word)
{c[(*at)++]=(struct mbx_command){MBX_FIFO,word};}
int mbx_vgp_frame_begin(struct mbx_command *c,unsigned capacity,unsigned *written)
{
 unsigned at=0,i;
 if(!c||!written||capacity<59)return -22;
 emit(c,&at,0x10000010);emit(c,&at,0);
 emit(c,&at,0xa0530054);emit(c,&at,0);emit(c,&at,0);emit(c,&at,0x3f800000);emit(c,&at,0);
 emit(c,&at,0x40e00000);emit(c,&at,0x3f808084);emit(c,&at,0x40e00000);emit(c,&at,0x40e00000);
 emit(c,&at,0xa0660066);for(i=0;i<4;++i)emit(c,&at,0x00800000);
 emit(c,&at,0xa0a600a8);for(i=0;i<12;++i)emit(c,&at,i%5==0?0x3f800000:0);
 emit(c,&at,0xa0a900ab);for(i=0;i<12;++i)emit(c,&at,i%5==0?0x40e00000:0);
 emit(c,&at,0xa0700073);
 emit(c,&at,0);emit(c,&at,0);emit(c,&at,0x3f800000);emit(c,&at,0x3f800000);
 emit(c,&at,0);emit(c,&at,0);emit(c,&at,0xbf800000);emit(c,&at,0x3f800000);
 for(i=0;i<4;++i)emit(c,&at,0);
 for(i=0;i<4;++i)emit(c,&at,0x3f800000);
 *written=at;return 0;
}
static int valid_program(const struct mbx_vgp_draw *d)
{
 unsigned i,j,pos=0,color=0,clip=0;
 for(i=0;i<d->instructions;++i){
  unsigned a=d->program[2*i],b=d->program[2*i+1],op=a&31,ns,dst=b>>26,mask=(b>>22)&15,encoded[2];
  struct mbx_vgp_source src[3];
  if(op==1||op==5||op==6)ns=1;
  else if(op==3)ns=3;
  else if(op==2||op==4||(op>=7&&op<=12))ns=2;
  else return 0;
  if(dst!=0&&dst!=1&&dst!=7&&(dst<16||dst>29))return 0;
  for(j=0;j<ns;++j){
   unsigned bank=(b>>(16+2*j))&3,index=(b>>(4*j))&15;
   if(bank==1)index|=((b>>12)&7)<<4;
   if(bank==0&&index>=d->input_count)return 0;
   if(bank==0&&index==1){
    unsigned used=(op==7?7:op==8?15:(op==5||op==6)?1:mask),lane;
    /* Normal delivery is xyz; do not silently discard a shader's w read. */
    for(lane=0;lane<4;++lane)if((used&(1U<<lane))&&((a>>(8+8*j+2*lane))&3)==3)return 0;
   }
   if(bank==1&&!((index<d->uniform_count)||(index>=96&&index<96+d->immediate_count)||(index>=112&&index<=115)))return 0;
   src[j]=(struct mbx_vgp_source){bank,index,(a>>(8+8*j))&255,(a>>(5+j))&1};
  }
  if(mbx_vgp_encode(op,dst,mask,src,ns,encoded)||encoded[0]!=a||encoded[1]!=b)return 0;
  if(dst==0)pos|=mask;else if(dst==1)color|=mask;else if(dst==7)clip|=mask;
 }
 return pos==15&&color==15&&(clip&3)==3;
}
int mbx_vgp_draw_encode(const struct mbx_vgp_draw *d,struct mbx_command *c,unsigned capacity,unsigned *written)
{
 unsigned at=0,i,j,k,needed,format;
 if(!d||!c||!written||!d->program||!d->vertices||!d->indices||
    !d->instructions||d->instructions>128||d->uniform_count>83||d->immediate_count>6||
    (d->input_count!=1&&d->input_count!=2)||!d->vertex_count||d->vertex_count>4096||
    !d->triangle_count||d->triangle_count>256||d->smooth>1||d->depth_always>1||d->cull_mode>2||
    (d->uniform_count&&!d->uniforms)||(d->immediate_count&&!d->immediates))return -22;
 needed=25+2*d->instructions+(d->uniform_count?1+4*d->uniform_count:0)+
  (d->immediate_count?1+4*d->immediate_count:0)+(8+3*(d->input_count==2?7:4))*d->triangle_count;
 if(capacity<needed||!valid_program(d))return -22;
 for(i=0;i<6;++i)if(!finite_word(d->viewport[i]))return -22;
 for(i=0;i<4*d->uniform_count;++i)if(!finite_word(d->uniforms[i]))return -22;
 for(i=0;i<4*d->immediate_count;++i)if(!finite_word(d->immediates[i]))return -22;
 for(i=0;i<4*d->input_count*d->vertex_count;++i)if(!finite_word(d->vertices[i]))return -22;
 for(i=0;i<3*d->triangle_count;++i)if(d->indices[i]>=d->vertex_count)return -22;
 /* Entire validation precedes writes, including late indices and attributes. */
 emit(c,&at,0x90000000|(d->instructions-1));
 for(i=0;i<2*d->instructions;++i)emit(c,&at,d->program[i]);
 emit(c,&at,0x8000ffff);
 for(i=0;i<16;++i)emit(c,&at,i==2?0x01000000|((d->instructions-1)<<8):0xf0000000);
 if(d->uniform_count){emit(c,&at,0xa0000000|(d->uniform_count-1));for(i=0;i<4*d->uniform_count;++i)emit(c,&at,d->uniforms[i]);}
 if(d->immediate_count){emit(c,&at,0xa0600000|(95+d->immediate_count));for(i=0;i<4*d->immediate_count;++i)emit(c,&at,d->immediates[i]);}
 emit(c,&at,0x10000080);for(i=0;i<6;++i)emit(c,&at,d->viewport[i]);
 format=d->input_count==1?4:0x34;
 for(i=0;i<d->triangle_count;++i){
  emit(c,&at,0x10000063);emit(c,&at,0x22200200|(d->smooth?0x400000:0)|(d->depth_always?0xc00:0));emit(c,&at,0xe0000000);
  emit(c,&at,format);emit(c,&at,0);emit(c,&at,0x40000000|(d->cull_mode<<18));emit(c,&at,0x70020004);
  for(j=0;j<3;++j)for(k=0;k<(d->input_count==2?7:4);++k)emit(c,&at,d->vertices[d->indices[i*3+j]*4*d->input_count+k]);
  c[at++]=(struct mbx_command){MBX_POLYGON_CONTROL,1};
 }
 *written=at;return 0;
}
int mbx_vgp_frame_end(struct mbx_command *c,unsigned capacity,unsigned *written)
{if(!c||!written||!capacity)return -22;*c=(struct mbx_command){MBX_FIFO,0xf0000000};*written=1;return 0;}
