#include "../mesa/mbx_color_cache.h"
#include <assert.h>
#include <stdio.h>
#include <math.h>
int main(void){
 struct mbx_color_cache c={0};uint32_t rng=0x8160face;unsigned checks=0;
 for(unsigned i=0;i<100000;++i){
  float v[4];
  for(unsigned j=0;j<4;++j){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;
   uint32_t b=rng;if((b&0x7f800000)==0x7f800000)b&=0x807fffff;memcpy(&v[j],&b,4);}
  for(unsigned repeat=0;repeat<4;++repeat){assert(mbx_cached_color(&c,v)==mbx_color(v));++checks;}
 }
 for(unsigned byte=0;byte<255;++byte){
  float x=((float)byte+.5f)/255.0f;
  float cases[]={nextafterf(x,-INFINITY),x,nextafterf(x,INFINITY),0.0f,-0.0f,1.0f};
  for(unsigned k=0;k<6;++k){float v[]={cases[k],cases[k],cases[k],cases[k]};
   assert(mbx_cached_color(&c,v)==mbx_color(v));assert(mbx_cached_color(&c,v)==mbx_color(v));checks+=2;}
 }
 printf("PASS %u exact cached color conversions including rounding boundaries and signed zero\n",checks);
}
