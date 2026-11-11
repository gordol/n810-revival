#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "linear_resource.h"
int reference_pack(const struct mbx_linear_source *,void *,size_t);
int main(void){unsigned n=0;for(unsigned w=1;w<=320;w+=7)for(unsigned h=1;h<=320;h+=31)for(unsigned flags=0;flags<8;flags++){
 unsigned pitch;size_t size=mbx_linear_size(w,h,&pitch),stride=w*4+3,bytes=stride*h;
 unsigned char *raw=malloc(bytes+1),*a=malloc(size+2),*b=malloc(size+2);for(size_t i=0;i<bytes+1;i++)raw[i]=(i*73+n*17)&255;
 memset(a,0xa5,size+2);memset(b,0xa5,size+2);
 struct mbx_linear_source s={0};s.data=raw+1;s.bytes=bytes;s.stride=stride;s.width=w;s.height=h;s.rgba=flags&1;s.opaque=(flags>>1)&1;s.repeat=(flags>>2)&1;
 assert(!mbx_linear_pack(&s,a+1,size));assert(!reference_pack(&s,b+1,size));assert(!memcmp(a,b,size+2));free(raw);free(a);free(b);n++;
 }printf("%u full-buffer cases: channels, opacity, wrap halos, padding and unaligned input/output match\n",n);}
