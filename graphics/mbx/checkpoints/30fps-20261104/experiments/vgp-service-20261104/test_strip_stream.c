/* Decode emitted strips independently and compare every assembled primitive
 * to the original triangle stream, including complete attributes and order. */
#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "common/mbx_vgp_isa.c"
#include "common/mbx_vgp_draw.c"
#include "common/mbx_vgp_topology.c"
#include "common/mbx_gears_frame_fixture.h"
#include "test_color_reference.h"
static struct mbx_command commands[24000],before[24000];
static unsigned seed=1;
static unsigned random_word(void){seed=seed*1664525U+1013904223U;return seed;}
static unsigned check(struct mbx_vgp_draw d)
{
 unsigned n=0,at=25+2*d.instructions+(d.uniform_count?1+4*d.uniform_count:0)+
  (d.immediate_count?1+4*d.immediate_count:0),tri=0,w=d.input_count==2?7:4;
 unsigned rotate=d.smooth||(MBX_VGP_UNIFORM_COLOR_REUSE&&reference_uniform_color(&d));
 if(uniform_color(&d))assert(reference_uniform_color(&d));
 {int e=mbx_vgp_draw_encode(&d,commands,24000,&n);if(e)fprintf(stderr,"encode error=%d vertices=%u triangles=%u inputs=%u\n",e,d.vertex_count,d.triangle_count,d.input_count);assert(!e);}
 while(at<n){
  unsigned v[258][7],count=0,t,r,k,ok;
  assert(commands[at].value==0x10000063);
  assert(commands[at+5].value==(0x40000000|(d.cull_mode<<18)));
  assert(commands[at+6].value==0x70020004);at+=7;
  while(at<n&&commands[at].destination==MBX_FIFO){
   assert(count<258);
   for(k=0;k<w;++k){assert(commands[at].destination==MBX_FIFO);v[count][k]=commands[at++].value;}
   ++count;
  }
  assert(count>=3&&commands[at].destination==MBX_POLYGON_CONTROL&&commands[at].value==1);++at;
  for(t=0;t<count-2;++t,++tri){
   unsigned corners[3]={t+(t&1),t+1-(t&1),t+2};
   assert(tri<d.triangle_count);ok=0;
   for(r=0;r<(rotate?3U:1U);++r){
    unsigned j;
    for(j=0;j<3;++j){
     const unsigned *original=d.vertices+d.indices[tri*3+(r+j)%3]*4*d.input_count;
     if(memcmp(v[corners[j]],original,w*sizeof(unsigned)))break;
    }
    if(j==3){ok=1;break;}
   }
   assert(ok);
  }
 }
 assert(at==n&&tri==d.triangle_count);return n;
}
int main(void)
{
 unsigned i,n,j,words=162,original=162,cases=0;
 unsigned short indices[768];
 for(i=0;i<sizeof(gears_draws)/sizeof(gears_draws[0]);++i){
  const struct mbx_gears_draw_fixture *f=&gears_draws[i];struct mbx_vgp_draw d=f->draw;
  assert(!mbx_vgp_topology(f->primitive,f->indices,f->count,f->lengths,f->runs,d.vertex_count,indices,768,&n));
  d.indices=indices;d.triangle_count=n/3;d.cull_mode=1;
  words+=check(d);++cases;
  original+=25+2*d.instructions+(d.uniform_count?1+4*d.uniform_count:0)+
   (d.immediate_count?1+4*d.immediate_count:0)+(8+3*(d.input_count==2?7:4))*d.triangle_count;
  /* Exercise all supported run lengths, alternating winding, arbitrary
   * disconnected triangles, duplicate attributes and both shading modes. */
  for(j=1;j<=256;++j){
   unsigned k,a=0,b=1%d.vertex_count,c=2%d.vertex_count;
   for(k=0;k<j;++k){
    indices[3*k]=(k&1)?b:a;indices[3*k+1]=(k&1)?a:b;indices[3*k+2]=c;
    a=b;b=c;c=random_word()%d.vertex_count;
    if(k%7==6)indices[3*k]=random_word()%d.vertex_count;
   }
   d.triangle_count=j;d.smooth=j&1;check(d);++cases;
  }
  memset(commands,0xa5,sizeof(commands));memcpy(before,commands,sizeof(commands));
  indices[3*d.triangle_count-1]=d.vertex_count;n=99;
  assert(mbx_vgp_draw_encode(&d,commands,24000,&n)==-22&&n==99&&!memcmp(before,commands,sizeof(commands)));
 }
 printf("{\"status\":\"PASS\",\"decoded_primitive_cases\":%u,\"baseline_words\":%u,\"strip_words\":%u,\"saved_words\":%u}\n",cases,original,words,original-words);
 return 0;
}
