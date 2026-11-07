/* Production homogeneous clipping shortcut versus Mesa plane expressions. */
#include <assert.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "draw_mbx_clip.h"
static uint32_t state=0x810cafe;
static uint32_t next(void){state^=state<<13;state^=state>>17;state^=state<<5;return state;}
static unsigned original(const float *p){unsigned m=0;
 if(!(-p[0]+p[3]>=0))m|=1;if(!(p[0]+p[3]>=0))m|=2;
 if(!(-p[1]+p[3]>=0))m|=4;if(!(p[1]+p[3]>=0))m|=8;
 if(!(p[2]+p[3]>=0))m|=16;if(!(-p[2]+p[3]>=0))m|=32;return m;}
int main(void){unsigned accepted=0;
 for(unsigned i=0;i<4000000;++i){uint32_t b[4];float p[4];
  for(unsigned j=0;j<4;++j)b[j]=next();
  if(i&1){b[3]=0x00800000u+next()%0x7f000000u;for(unsigned j=0;j<3;++j)b[j]=(next()&0x80000000u)|(next()%(b[3]+1));}
  if(i%7==0)b[i%3]=(i&1?0x80000000u:0)|b[3];
  memcpy(p,b,16);unsigned ref=original(p);int inside=mbx_clip_cube_inside(p);
  assert(!inside||ref==0);assert((inside?0:original(p))==ref);accepted+=inside;
 }
 printf("PASS 4000000 clipping vectors, %u exact interior shortcuts\n",accepted);
}
