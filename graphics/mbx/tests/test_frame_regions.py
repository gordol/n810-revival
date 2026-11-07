"""Validate actual whole-frame region generation with ASan/UBSan.
Every visible tile must start with the background primitive in single-pass mode;
all lists terminate in bounds and worst-case bin overflow rejects before writes.
"""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'kernel/mbx_render_service.h').read_text()
structs=s[s.index('struct mbx_service_vertex'):s.index('static int gpu_service_kick_surface_stride')]
code=s[s.index('struct gpu_region_bounds'):s.index('    dma_wmb();gpu_phase=21;t1=ktime_get_ns();')]+ '\n return 0;\n}\n'
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint32_t u32;typedef uint32_t __le32;typedef uint16_t u16;typedef uint8_t u8;typedef uint64_t u64;
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define cpu_to_le32(x) (x)
#define MBX_TILE_BYTES 16384
static struct {void *parameters,*tiles;unsigned frame_page_count;} gpu_memory;
static bool gpu_frame_background,gpu_frame_damage,gpu_frame_sparse_parameters=true;
static unsigned gpu_frame_width,gpu_frame_height,gpu_frame_stride,gpu_frame_capacity_bytes=512*1024,gpu_phase;
static u64 ktime_get_ns(void){return 0;}
static int mbx_dma_frame_for_device(void *p){return 0;}
#define MBX_BACKGROUND_WORDS 26
/* SPDX-License-Identifier: MIT */
int mbx_background_parameter(unsigned *w,unsigned n)
{
 unsigned i;
 if(!w||n<MBX_BACKGROUND_WORDS)return -22;
 for(i=0;i<MBX_BACKGROUND_WORDS;++i)w[i]=0;
 w[0]=0xe0000000U;w[1]=0xa8800000U;w[2]=0x0e000000U;
 w[3]=0xd6887610U;w[4]=0x22220e80U;
 for(i=11;i<=16;++i)w[i]=0x3f800000U;
 return 0;
}
int mbx_tile_headers(unsigned *w,unsigned capacity,unsigned tx,unsigned ty,unsigned gx,unsigned gy)
{
 unsigned nx,ny,group_words,x,y,i,j,index;
 if(!w||!tx||!ty||!gx||!gy||tx>256||ty>256||gx>256||gy>256)return -22;
 nx=(tx+gx-1)/gx;ny=(ty+gy-1)/gy;
 if(nx>256/gx||ny>256/gy)return -22;
 group_words=gx*gy*2U;
 if(nx*ny*group_words>capacity)return -22;
 for(i=0;i<nx*ny*group_words;++i)w[i]=0;
 for(y=0;y<ny;++y)for(x=0;x<nx;++x){
  index=(y*nx+x)*group_words;
  j=0x22000000U|(x*gx)|((y*gy)<<8);
  for(i=0;i<gx*gy;++i)w[index+2*i]=j;
 }
 return 0;
}
int mbx_render_list32(unsigned *words,unsigned capacity)
{
 unsigned i;if(!words||capacity<8)return -22;
 for(i=0;i<8;++i)words[i]=0;
 words[0]=0xe2000000U;
 return 0;
}
int mbx_background32(unsigned *words,unsigned capacity)
{
 int error=mbx_background_parameter(words,capacity);
 if(error)return error;
 /* Original0x801ba8ec derives padded4x4tile extent64x64 pixels.
  * 0x801ba974 patches template+1c,+28,+54,+64 with converted
  * fixed16 values. Doubled extent128 and extent/1024=1/16. */
 words[7]=0x43000000U;words[10]=0x43000000U;
 words[21]=0x3d800000U;words[25]=0x3d800000U;
 return 0;
}
'''
main=r'''
static unsigned bits(float v){unsigned b;memcpy(&b,&v,4);return b;}
int main(void){
 gpu_memory.parameters=malloc(65536);gpu_memory.tiles=malloc(MBX_TILE_BYTES);gpu_memory.frame_page_count=128;
 struct {struct mbx_service_job h;struct mbx_service_primitive p[512];} job={0};
 unsigned cases=0;
 for(unsigned mode=0;mode<2;++mode)for(unsigned w=2;w<=512;w+=2)for(unsigned h=1;h<=512;h+=17){
  gpu_frame_background=mode;job.h=(struct mbx_service_job){0x314a424d,2,1,w,h,0};
  job.p[0].vertices[0].x=bits(0);job.p[0].vertices[0].y=bits(0);
  job.p[0].vertices[1].x=bits(w/2);job.p[0].vertices[1].y=bits(h/2);
  job.p[0].vertices[2].x=bits(w);job.p[0].vertices[2].y=bits(h);
  gpu_frame_sparse_parameters=false;assert(!gpu_service_frame(&job.h));
  unsigned char expected[65536];memcpy(expected,gpu_memory.parameters,65536);
  memset(gpu_memory.parameters,0xa5,65536);gpu_frame_sparse_parameters=true;
  assert(!gpu_service_frame(&job.h));
  assert(!memcmp(expected,gpu_memory.parameters,26*4));
  assert(!memcmp(expected+4096,(u8 *)gpu_memory.parameters+4096,68));
  if(mode)assert(!memcmp(expected+128,(u8 *)gpu_memory.parameters+128,68));
  unsigned nx=(w+15)/16,ny=(h+15)/16,gx=(nx+3)/4,last=0;
  u32 *r=gpu_memory.tiles,*p=gpu_memory.parameters;
  for(unsigned y=0;y<ny;++y)for(unsigned x=0;x<nx;++x){
   unsigned n=((y/4)*gx+x/4)*32+((y%4)*4+x%4)*2;
   last=max(last,n);assert(!(r[n]&0x02000000));
   unsigned ptr=r[n+1]-0x10000;assert(ptr>=0xa000&&ptr<65536);
   if(mode){assert(p[ptr/4]==0x40800020);ptr+=4;}
   assert(p[ptr/4]==0x40800400);ptr+=4;assert(p[ptr/4]==0xf0000000);
   unsigned first=r[n+1]-0x10000;assert(!memcmp(expected+first,(u8 *)p+first,ptr-first+4));
  }
  assert((r[last]&0x84000000)==0x84000000);
  if(mode){assert(p[32]==0xe0000000&&p[33]==0x22200e00);for(unsigned i=40;i<46;++i)assert(p[i]==0x3f800000);}
  ++cases;
  job.h.count=0;assert(!gpu_service_frame(&job.h));
  if(mode)for(unsigned y=0;y<ny;++y)for(unsigned x=0;x<nx;++x){
   unsigned n=((y/4)*gx+x/4)*32+((y%4)*4+x%4)*2,ptr=r[n+1]-0x10000;
   assert(!(r[n]&0x02000000));assert(p[ptr/4]==0x40800020&&p[ptr/4+1]==0xf0000000);
  }
 }
 /* Move from tile0 to tile15: erase old coverage and shade new coverage,
  * then erase the last tile on an empty frame. No unrelated tile is touched. */
 gpu_frame_background=true;gpu_frame_damage=true;
 memset(gpu_previous_regions,0,sizeof(gpu_previous_regions));gpu_previous_regions[0]=true;
 job.h=(struct mbx_service_job){0x314a424d,2,1,64,64,0};
 for(unsigned v=0;v<3;++v){job.p[0].vertices[v].x=bits(48+v*3);job.p[0].vertices[v].y=bits(48+v*3);}
 assert(!gpu_service_frame(&job.h));u32 *regions=gpu_memory.tiles,*parameters=gpu_memory.parameters;
 for(unsigned i=0;i<16;++i){
  if(i==0||i==15){assert(!(regions[2*i]&0x02000000));unsigned at=(regions[2*i+1]-0x10000)/4;
   assert(parameters[at]==0x40800020);assert(parameters[at+1]==(i==0?0xf0000000:0x40800400));
  }else assert(regions[2*i]&0x02000000);
 }
 memset(gpu_previous_regions,0,sizeof(gpu_previous_regions));gpu_previous_regions[15]=true;job.h.count=0;
 assert(!gpu_service_frame(&job.h));for(unsigned i=0;i<16;++i)assert(!!(regions[2*i]&0x02000000)==(i!=15));
 memset(gpu_previous_regions,0,sizeof(gpu_previous_regions));assert(!gpu_service_frame(&job.h));
 for(unsigned i=0;i<16;++i)assert((regions[2*i]&0x86000000)==0x02000000);
 gpu_frame_damage=false;
 gpu_frame_background=true;job.h=(struct mbx_service_job){0x314a424d,2,512,512,512,0};
 for(unsigned i=0;i<512;++i){job.p[i].vertices[1].x=bits(512);job.p[i].vertices[2].y=bits(512);}
 memset(gpu_memory.parameters,0x5a,65536);assert(gpu_service_frame(&job.h)==-ENOSPC);
 for(unsigned i=0;i<65536;++i)assert(((u8 *)gpu_memory.parameters)[i]==0x5a);
 free(gpu_memory.parameters);free(gpu_memory.tiles);
 printf("PASS %u region layouts plus empty-frame coverage, moving-tile damage, and atomic overflow rejection\n",cases);
}
'''
with tempfile.TemporaryDirectory(prefix='mbx-regions-') as d:
 c=Path(d)/'test.c';c.write_text(prefix+structs+code+main);exe=Path(d)/'test'
 subprocess.run(['cc','-std=c11','-O1','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
