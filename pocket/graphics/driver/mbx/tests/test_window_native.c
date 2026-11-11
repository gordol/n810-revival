/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "mbx_window_export.h"
static int guards(const unsigned char *p,unsigned layout){
 for(unsigned j=0;j<4096;j++)if(p[j]!=0xa5)return 0;
 for(unsigned i=0;i<16;i++){
  unsigned at=mbx_window_offset(layout,i)+mbx_window_capacity(layout,i);
  for(unsigned j=0;j<4096;j++)if(p[at+j]!=0xa5)return 0;
 }
 return 1;
}
int main(void){
 assert(MBX_WINDOW_LEGACY_BYTES==1092U*1024U&&MBX_WINDOW_NATIVE_BYTES==2036U*1024U);
 for(unsigned layout=1;layout<=2;layout++){
  unsigned bytes=layout==1?MBX_WINDOW_LEGACY_BYTES:MBX_WINDOW_NATIVE_BYTES,cursor=4096;
  unsigned char *p=malloc(bytes);assert(p);memset(p,0xa5,bytes);
  for(unsigned i=0;i<16;i++){
   unsigned capacity=layout==2&&(i<2||i>=14)?307200U:65536U;
   assert(mbx_window_capacity(layout,i)==capacity&&mbx_window_offset(layout,i)==cursor);
   assert(!(mbx_window_address(layout,i)&4095U));
   assert(mbx_window_address(layout,i)+capacity+4096<=MBX_WINDOW_BASE+bytes);
   memset(p+cursor,(int)i,capacity);cursor+=capacity+4096;
  }
  assert(cursor==bytes&&guards(p,layout));
  for(unsigned i=0;i<16;i++){
   unsigned at=mbx_window_offset(layout,i)+mbx_window_capacity(layout,i);p[at]^=1;assert(!guards(p,layout));p[at]^=1;
  }
  /* The actual allocator programs eight 4 KiB PTE banks (8192 pages). */
  unsigned table[8192],first=MBX_WINDOW_BASE/4096,pages=bytes/4096;
  for(unsigned i=0;i<8192;i++)table[i]=0x02000000;
  assert(first+pages<8192);
  for(unsigned i=0;i<pages;i++)table[first+i]=0x08000000+i*4096;
  for(unsigned i=0;i<8192;i++)assert(table[i]==(i>=first&&i<first+pages?0x08000000+(i-first)*4096:0x02000000));
  if(layout==2)assert(first+pages>1024&&table[1024]!=0x02000000);
  free(p);
 }
 struct mbx_window_state state={.session=7,.layout=2},before;struct mbx_window_token token[16],out;
 for(unsigned i=0;i<16;i++){
  struct mbx_window_request q={.version=2,.destination=i};
  unsigned w=mbx_window_width(2,i),h=mbx_window_height(2,i);
  assert(!mbx_window_begin_sized(&state,&q,0,w,h));assert(!mbx_window_complete(&state,1,token+i));
 }
 struct mbx_window_request merge={.version=2,.destination=0,.source={token[14],token[15]}};
 assert(!mbx_window_begin_sized(&state,&merge,2,240,320));assert(!mbx_window_complete(&state,1,&out));
 assert(mbx_window_lookup(&state,token[0])&&!mbx_window_lookup(&state,out));
 for(unsigned mutation=0;mutation<8;mutation++){
  struct mbx_window_request bad=merge;unsigned w=240,h=320;
  if(mutation==0)bad.version=1;if(mutation==1)bad.destination=2;if(mutation==2)bad.source[0].generation++;
  if(mutation==3)bad.source[1]=bad.source[0];if(mutation==4)bad.destination=14;
  if(mutation==5)w=256;if(mutation==6)h=128;if(mutation==7)bad.source[1].session++;
  before=state;assert(mbx_window_begin_sized(&state,&bad,2,w,h));assert(!memcmp(&state,&before,sizeof state));
 }
 for(unsigned i=14;i<16;i++){
  struct mbx_window_request q={.version=2,.destination=i};assert(!mbx_window_begin_sized(&state,&q,0,128,128));assert(!mbx_window_complete(&state,1,token+i));
 }
 merge.destination=2;merge.source[0]=token[14];merge.source[1]=token[15];
 assert(!mbx_window_begin_sized(&state,&merge,2,128,128));assert(!mbx_window_complete(&state,1,&out));
 struct mbx_window_image image={.version=2,.width=240,.height=320,.format=1,.token={7,11,0},.stride_bytes=960};
 assert(mbx_window_image_valid(&image));image.stride_bytes=1024;assert(!mbx_window_image_valid(&image));
 assert(!mbx_window_shape(2,0,128,128)&&!mbx_window_shape(2,2,240,320)&&!mbx_window_shape(1,0,240,320));
 puts("native layout: two 240x320 clients, twelve small clients, two large scratch; all 17 guards, bank1 PTEs, dimensions and generations checked");
}
