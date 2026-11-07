#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "mbx_vgp_batch.h"
#include "mbx_gears_fixture.h"
int main(void){
 struct mbx_vgp_position v[6];memcpy(v,vgp_gears_vertices,sizeof(v));
 struct mbx_command c[229],before[229];unsigned m[16]={0},color[4]={0},n=99;
 memset(c,0xa5,sizeof(c));memcpy(before,c,sizeof(c));
 assert(mbx_encode_vgp_batch(v,2,m,color,c,226,&n)<0&&n==99&&!memcmp(c,before,sizeof(c)));
 assert(!mbx_encode_vgp_batch(v,2,m,color,c,227,&n)&&n==227);
 assert(!memcmp(c+227,before+227,sizeof(c)-227*sizeof(*c)));
 assert(c[59].value==0x90000012&&c[115].value==0xa0000009);
 for(unsigned i=0;i<38;++i)assert(c[60+i].value==vgp_gears_program[i]);
 for(unsigned i=0;i<40;++i)assert(c[116+i].value==vgp_gears_constants[i]);
 assert(c[156].value==0xa0600060);
 for(unsigned i=0;i<4;++i)assert(c[157+i].value==vgp_gears_constants[96*4+i]);
 assert(c[226].destination==MBX_FIFO&&c[226].value==0xf0000000);
 for(unsigned t=0;t<2;++t){unsigned at=168+t*29;assert(c[at+3].value==0x34&&c[at+6].value==0x70020004);for(unsigned j=0;j<21;++j)assert(c[at+7+j].value==vgp_gears_vertices[t*24+(j/7)*8+j%7]);}
 puts("PASS 227-command compact gears packet, exact program/uniform/immediate/input words, capacity rejection and untouched tail");
}
