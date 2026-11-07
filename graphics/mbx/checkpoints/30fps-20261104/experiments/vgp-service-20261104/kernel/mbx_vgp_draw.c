/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_draw.h"
#include "mbx_vgp_isa.h"
#ifndef MBX_VGP_REUSE_STRIPS
#define MBX_VGP_REUSE_STRIPS 1
#endif
#ifndef MBX_VGP_UNIFORM_COLOR_REUSE
#define MBX_VGP_UNIFORM_COLOR_REUSE 1
#endif
/* Conservative per-lane dependency analysis, not shader evaluation. A color
 * independent of every vertex input is identical across this draw; rotating
 * its flat triangles cannot change their provoking color. Unknown/unwritten
 * temporary lanes remain varying. Run only after valid_program(). */
static int uniform_color(const struct mbx_vgp_draw *d)
{
 unsigned temp[14][4],color[4]={1,1,1,1},i,j,s,k;
 for(i=0;i<14;++i)for(j=0;j<4;++j)temp[i][j]=1;
 for(i=0;i<d->instructions;++i){
  unsigned a=d->program[2*i],b=d->program[2*i+1],op=a&31;
  unsigned ns=op==3?3:(op==1||op==5||op==6)?1:2,values[4]={0};
  unsigned dst=b>>26,mask=(b>>22)&15;
  for(j=0;j<4;++j)if(mask&(1U<<j)){
   unsigned first=(op==5||op==6||op==7||op==8)?0:j;
   unsigned end=op==7?3:op==8?4:first+1;
   for(s=0;s<ns;++s)for(k=first;k<end;++k){
    unsigned bank=(b>>(16+2*s))&3,index=(b>>(4*s))&15,lane=(a>>(8+8*s+2*k))&3;
    values[j]|=bank==0?1:bank==1?0:temp[index][lane];
   }
  }
  if(dst==1||dst>=16)for(j=0;j<4;++j)if(mask&(1U<<j)){
   if(dst==1)color[j]=values[j];else temp[dst-16][j]=values[j];
  }
 }
 return !(color[0]|color[1]|color[2]|color[3]);
}
/* Original implementation of adjacent primitive reuse. The reference selects
 * block type 0x40000000 for strips and terminates via polygon control = 1.
 * Never merge across draws or compare positions without other attributes. */
static int same_vertex(const struct mbx_vgp_draw *d,unsigned a,unsigned b)
{
 unsigned k,words=d->input_count==2?7:4,stride=4*d->input_count;
 if(a==b)return 1;
 for(k=0;k<words;++k)if(d->vertices[a*stride+k]!=d->vertices[b*stride+k])return 0;
 return 1;
}
static int strip_next(const struct mbx_vgp_draw *d,unsigned triangle,
                     unsigned a,unsigned b,unsigned rotate,unsigned *next)
{
 unsigned r;
 /* Cyclic rotations preserve winding; flat shading must also preserve the
  * exact last/provoking vertex, so only the original order is eligible. */
 for(r=0;r<(rotate?3U:1U);++r){
  const unsigned short *t=d->indices+3*triangle;
  if(same_vertex(d,a,t[r])&&same_vertex(d,b,t[(r+1)%3])){
   *next=t[(r+2)%3];return 1;
  }
 }
 return 0;
}
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
static int validate_shader(const struct mbx_vgp_draw *d,struct mbx_vgp_shader_cache *cache,unsigned *constant)
{
 unsigned i,k;
 if(cache&&d->instructions<=32)for(i=0;i<4;++i){
  struct mbx_vgp_shader_cache_entry *e=cache->entries+i;
  if(e->instructions!=d->instructions||e->inputs!=d->input_count||
     e->uniforms!=d->uniform_count||e->immediates!=d->immediate_count)continue;
  for(k=0;k<2*d->instructions;++k)if(e->program[k]!=d->program[k])break;
  if(k==2*d->instructions){*constant=e->uniform_color;return 1;}
 }
 if(!valid_program(d))return 0;
 *constant=MBX_VGP_UNIFORM_COLOR_REUSE&&uniform_color(d);
 if(cache&&d->instructions<=32){
  struct mbx_vgp_shader_cache_entry *e=cache->entries+(cache->replace++&3);
  e->instructions=d->instructions;e->inputs=d->input_count;
  e->uniforms=d->uniform_count;e->immediates=d->immediate_count;e->uniform_color=*constant;
  for(k=0;k<2*d->instructions;++k)e->program[k]=d->program[k];
 }
 return 1;
}
int mbx_vgp_draw_encode_cached(const struct mbx_vgp_draw *d,struct mbx_command *c,unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *cache)
{
 unsigned at=0,i,j,k,needed,format,rotate,constant;
 if(!d||!c||!written||!d->program||!d->vertices||!d->indices||
    !d->instructions||d->instructions>128||d->uniform_count>83||d->immediate_count>6||
    (d->input_count!=1&&d->input_count!=2)||!d->vertex_count||d->vertex_count>4096||
    !d->triangle_count||d->triangle_count>256||d->smooth>1||d->depth_always>1||d->cull_mode>2||
    (d->uniform_count&&!d->uniforms)||(d->immediate_count&&!d->immediates))return -22;
 needed=25+2*d->instructions+(d->uniform_count?1+4*d->uniform_count:0)+
  (d->immediate_count?1+4*d->immediate_count:0)+(8+3*(d->input_count==2?7:4))*d->triangle_count;
 if(capacity<needed||!validate_shader(d,cache,&constant))return -22;
 for(i=0;i<6;++i)if(!finite_word(d->viewport[i]))return -22;
 for(i=0;i<4*d->uniform_count;++i)if(!finite_word(d->uniforms[i]))return -22;
 for(i=0;i<4*d->immediate_count;++i)if(!finite_word(d->immediates[i]))return -22;
 for(i=0;i<4*d->input_count*d->vertex_count;++i)if(!finite_word(d->vertices[i]))return -22;
 for(i=0;i<3*d->triangle_count;++i)if(d->indices[i]>=d->vertex_count)return -22;
 rotate=d->smooth||constant;
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
  unsigned a=d->indices[i*3+1],b=d->indices[i*3+2],run=1,next;
  emit(c,&at,0x10000063);emit(c,&at,0x22200200|(d->smooth?0x400000:0)|(d->depth_always?0xc00:0));emit(c,&at,0xe0000000);
  emit(c,&at,format);emit(c,&at,0);emit(c,&at,0x40000000|(d->cull_mode<<18));emit(c,&at,0x70020004);
  for(j=0;j<3;++j)for(k=0;k<(d->input_count==2?7:4);++k)emit(c,&at,d->vertices[d->indices[i*3+j]*4*d->input_count+k]);
  while(MBX_VGP_REUSE_STRIPS&&i+1<d->triangle_count&&
        strip_next(d,i+1,(run&1)?b:a,(run&1)?a:b,rotate,&next)){
   for(k=0;k<(d->input_count==2?7:4);++k)emit(c,&at,d->vertices[next*4*d->input_count+k]);
   a=b;b=next;++run;++i;
  }
  c[at++]=(struct mbx_command){MBX_POLYGON_CONTROL,1};
 }
 *written=at;return 0;
}
int mbx_vgp_draw_encode(const struct mbx_vgp_draw *d,struct mbx_command *c,unsigned capacity,unsigned *written)
{return mbx_vgp_draw_encode_cached(d,c,capacity,written,0);}
int mbx_vgp_frame_end(struct mbx_command *c,unsigned capacity,unsigned *written)
{if(!c||!written||!capacity)return -22;*c=(struct mbx_command){MBX_FIFO,0xf0000000};*written=1;return 0;}
