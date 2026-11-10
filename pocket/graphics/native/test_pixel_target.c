/* SPDX-License-Identifier: GPL-2.0-or-later */
#define GL_GLEXT_PROTOTYPES
#include <GL/osmesa.h>
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <sys/resource.h>
#include "pixel_target.h"
#include "room_draw.h"
void *pocket_mbx_open(int);
int pocket_mbx_resize(void *,unsigned,unsigned);
int pocket_mbx_stage(void *,unsigned,const unsigned char *,unsigned,unsigned);
int pocket_mbx_render(void *,uint16_t *);
void pocket_mbx_close(void *);
int pocket_room_pixels_into(float,float,float,float,float,unsigned,unsigned,uint16_t *,unsigned,size_t,unsigned);
static void render(void *owner,const char *mode,unsigned width,unsigned height,unsigned scene,uint16_t *out){
 unsigned stride=width+7;
 if(scene){
  if(!strcmp(mode,"direct")){
   glPixelStorei(GL_PACK_ROW_LENGTH,17);glPixelStorei(GL_PACK_SKIP_PIXELS,2);
   glPixelStorei(GL_PACK_SKIP_ROWS,3);glPixelStorei(GL_PACK_ALIGNMENT,8);
   glPixelStorei(GL_PACK_SWAP_BYTES,GL_TRUE);
  }
  if(getenv("POCKET_TEST_ROOM_DRAW")){
   assert(!pocket_target_begin());
   for(unsigned y=0;y<height;y+=400)for(unsigned x=0;x<width;x+=400){
    unsigned w=width-x,h=height-y;if(w>400)w=400;if(h>400)h=400;
    assert(!pocket_room_draw_tile(.75f,20,0,.08f,.03f,width,height,x,y,w,h,400,1));
    assert(!pocket_target_read(out+y*stride+x,((size_t)stride*height-y*stride-x)*2,stride,w,h));
   }
   pocket_target_end();
  }else{
  assert(pocket_room_pixels_into(.75f,20,0,.08f,.03f,width,height,out,stride,(size_t)stride*height*2,400)>0);
  }
  if(!strcmp(mode,"direct")){
   GLint value;glGetIntegerv(GL_PACK_ROW_LENGTH,&value);assert(value==17);
   glGetIntegerv(GL_PACK_SKIP_PIXELS,&value);assert(value==2);
   glGetIntegerv(GL_PACK_SKIP_ROWS,&value);assert(value==3);
   glGetIntegerv(GL_PACK_ALIGNMENT,&value);assert(value==8);
   glGetIntegerv(GL_PACK_SWAP_BYTES,&value);assert(value==GL_TRUE);
  }
 }else{
  assert(width==64&&height==48);assert(!pocket_mbx_resize(owner,9,3));assert(!pocket_mbx_resize(owner,8,3));
  for(unsigned i=0;i<24;++i){unsigned char glyph[16];for(unsigned y=0;y<16;++y)glyph[y]=(unsigned char)(i*13+y*17);
   assert(!pocket_mbx_stage(owner,i,glyph,0xfe66,0x11aa));}
  uint16_t cells[64*48];assert(!pocket_mbx_render(owner,cells));
  for(unsigned y=0;y<height;++y)memcpy(out+y*stride,cells+y*width,width*2);
 }
 GLint bound;glGetIntegerv(GL_FRAMEBUFFER_BINDING,&bound);assert(bound==0);
 assert(glGetError()==GL_NO_ERROR);
 glPixelStorei(GL_PACK_ROW_LENGTH,0);glPixelStorei(GL_PACK_SKIP_PIXELS,0);glPixelStorei(GL_PACK_SKIP_ROWS,0);glPixelStorei(GL_PACK_ALIGNMENT,4);glPixelStorei(GL_PACK_SWAP_BYTES,GL_FALSE);
}
static uint64_t ns(clockid_t clock){struct timespec t;assert(!clock_gettime(clock,&t));return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;}
int main(int argc,char **argv){
 int capture=argc==2&&!strcmp(argv[1],"--hardware-capture");
 int hardware=capture||(argc==2&&!strcmp(argv[1],"--hardware"));assert(argc==1||hardware);
 const unsigned sizes[][3]={{64,48,0},{320,200,1},{417,257,1},{64,48,0}};
 uint16_t *images[2][4];
 for(unsigned mode=0;mode<2;++mode){
  const char *name=mode?"direct":"legacy";assert(!setenv("POCKET_GL_TARGET",name,1));
  void *owner=pocket_mbx_open(hardware);assert(owner);
  if(hardware)assert(!strcmp((const char*)glGetString(GL_RENDERER),"Nokia MBX GPU transform, lighting and rasterizer"));
  uint16_t guard=0xa55a;
  assert(pocket_target_read(&guard,2,1,1,1)==-1);
  assert(!pocket_target_begin());assert(pocket_target_begin()==-1);
  assert(pocket_target_read(&guard,1,1,1,1)==-1);
  assert(pocket_target_read(&guard,2,0,1,1)==-1);
  assert(pocket_target_read(&guard,2,1,401,1)==-1);
  assert(guard==0xa55a);pocket_target_end();
  for(unsigned i=0;i<4;++i){unsigned w=sizes[i][0],h=sizes[i][1],stride=w+7;size_t n=(size_t)stride*h;
   uint16_t *pixels=malloc((n+64)*2);assert(pixels);images[mode][i]=pixels;
   for(size_t j=0;j<n+64;++j)pixels[j]=0xa55a;
   GLint bw,bh,format;void *backing;
   int verify_no_front_copy=mode&&(capture||!hardware);
   if(verify_no_front_copy){
    assert(OSMesaGetColorBuffer(OSMesaGetCurrentContext(),&bw,&bh,&format,&backing));
    assert(bw==400&&bh==400&&format==OSMESA_RGB_565);
    memset(backing,0xa5,400*400*2);
   }
   unsigned measured=hardware&&!capture?80:1,warmup=hardware&&!capture?10:0;
   uint64_t wall=0,cpu=0;struct rusage before,after;getrusage(RUSAGE_SELF,&before);
   for(unsigned frame=0;frame<measured+warmup;++frame){
    if(frame==warmup)getrusage(RUSAGE_SELF,&before);
    uint64_t t=ns(CLOCK_MONOTONIC),c=ns(CLOCK_PROCESS_CPUTIME_ID);
    render(owner,name,w,h,sizes[i][2],pixels+32);
    if(frame>=warmup){wall+=ns(CLOCK_MONOTONIC)-t;cpu+=ns(CLOCK_PROCESS_CPUTIME_ID)-c;}
   }
   getrusage(RUSAGE_SELF,&after);
   if(verify_no_front_copy){
    const unsigned char *bytes=backing;
    for(unsigned j=0;j<400*400*2;++j)assert(bytes[j]==0xa5);
    printf("case=%u osmesa_front_copy=absent checked_bytes=320000\n",i);
   }
   printf("mode=%s case=%u frames=%u wall_ns=%llu cpu_ns=%llu minor_faults=%ld major_faults=%ld peak_rss_kib=%ld hardware=%d\n",name,i,measured,(unsigned long long)wall,(unsigned long long)cpu,after.ru_minflt-before.ru_minflt,after.ru_majflt-before.ru_majflt,after.ru_maxrss,hardware);fflush(stdout);
   for(unsigned y=0;y<h;++y)for(unsigned x=w;x<stride;++x)assert(pixels[32+y*stride+x]==0xa55a);
   for(unsigned j=0;j<32;++j)assert(pixels[j]==0xa55a&&pixels[32+n+j]==0xa55a);
  }
  pocket_mbx_close(owner);
 }
 unsigned mismatches=0;
 for(unsigned i=0;i<4;++i){unsigned w=sizes[i][0],h=sizes[i][1];
  unsigned changed=0;
  for(unsigned y=0;y<h;++y)for(unsigned x=0;x<w;++x){size_t j=32+y*(w+7)+x;if(images[0][i][j]!=images[1][i][j])++changed;}
  mismatches+=changed;
  if(hardware)for(unsigned mode=0;mode<2;++mode){
   char name[64];snprintf(name,sizeof name,"target-%u-%s.rgb565",i,mode?"direct":"legacy");FILE *f=fopen(name,"wb");assert(f);
   for(unsigned y=0;y<h;++y)assert(fwrite(images[mode][i]+32+y*(w+7),2,w,f)==w);
   assert(!fclose(f));
  }
  printf("%ux%u %s exact_pixels=%u changed_pixels=%u guards=ok pack_state=restored shared_context=1\n",w,h,sizes[i][2]?"Room":"cells",w*h-changed,changed);
  free(images[0][i]);free(images[1][i]);
 }
 return mismatches?2:0;
}
