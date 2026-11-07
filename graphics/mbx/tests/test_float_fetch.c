#include "../mesa/mbx_float_fetch.h"
#include <assert.h>
#include <stdio.h>
int main(void){
 uint32_t rng=0x810;unsigned checks=0;
 for(unsigned words=1;words<=4;++words)for(unsigned sa=0;sa<8;++sa)for(unsigned da=0;da<8;++da)
 for(unsigned iteration=0;iteration<1000;++iteration){
  unsigned char src[32],dst[40],reference[40];memset(src,0xcc,sizeof(src));memset(dst,0xa7,sizeof(dst));memcpy(reference,dst,sizeof(dst));
  uint32_t v[4]={0,0,0,0x3f800000};
  for(unsigned j=0;j<words;++j){rng^=rng<<13;rng^=rng>>17;rng^=rng<<5;v[j]=rng;memcpy(src+sa+j*4,&rng,4);}
  memcpy(reference+da,v,16);mbx_float_fetch4(dst+da,src+sa,words);assert(!memcmp(dst,reference,sizeof(dst)));++checks;
  /* Overlap must behave like unpacking into a temporary before emitting. */
  memcpy(dst,src,sizeof(src));memcpy(reference,dst,sizeof(dst));memcpy(reference+da,v,16);
  mbx_float_fetch4(dst+da,dst+sa,words);assert(!memcmp(dst,reference,sizeof(dst)));++checks;
 }
 printf("PASS %u exact float-attribute expansions, unaligned input/output, overlap, guard bytes and arbitrary IEEE bits\n",checks);
}
