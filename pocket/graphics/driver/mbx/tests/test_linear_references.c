/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../mesa/mbx_linear_cache.h"
#include "../mesa/mbx_wire_resources.h"
static unsigned baseline[262144],candidate[262144];
static unsigned char pixels[3][2560];
int main(void){
 struct mbx_linear_entry cache[3]={0};unsigned crop[4]={0,0,16,16};
 for(unsigned i=0;i<3;i++)for(unsigned j=0;j<sizeof pixels[i];j++)pixels[i][j]=(unsigned char)(i*31+j);
 for(uint64_t epoch=1;epoch<40;epoch++){
  memset(baseline,0,sizeof baseline);memset(candidate,0,sizeof candidate);
  baseline[0]=candidate[0]=0x3156474d;baseline[1]=candidate[1]=9;baseline[2]=candidate[2]=64;baseline[11]=candidate[11]=5;
  for(unsigned n=0;n<100;n++){
   unsigned which=n%3,ref,got;struct mbx_linear_entry *e=cache+which;
   if(n==50){pixels[which][0]++;e->wire_epoch=0;} /* Updated content invalidates ownership. */
   assert(!mbx_wire_resource_append_linear(baseline,sizeof baseline,pixels[which],16,18,sizeof pixels[which],&ref));
   if(mbx_linear_wire_matches(e,epoch))got=e->wire_index;
   else{assert(!mbx_wire_resource_append_linear(candidate,sizeof candidate,pixels[which],16,18,sizeof pixels[which],&got));e->wire_epoch=epoch;e->wire_index=got;}
   assert(got==ref&&baseline[2]==candidate[2]&&!memcmp(baseline,candidate,baseline[2]));
  }
 }
 struct pipe_resource *r=(struct pipe_resource*)(void*)pixels;
 cache[0].resource=r;cache[0].timestamp=7;cache[0].flags=2;memcpy(cache[0].crop,crop,sizeof crop);
 assert(mbx_linear_matches(cache,r,7,2,crop));assert(!mbx_linear_matches(cache,r,8,2,crop));
 crop[0]++;assert(!mbx_linear_matches(cache,r,7,2,crop));assert(!mbx_linear_wire_matches(cache,0));
 puts("PASS 3900 resource references: canonical bytes/indices exact, content and frame invalidation");
}
