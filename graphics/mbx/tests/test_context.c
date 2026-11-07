/* SPDX-License-Identifier: MIT */
#include "../common/mbx_context.h"
#include <assert.h>
#include <stdio.h>
int main(void)
{
 unsigned a,b,selection=0xdeadbeefU;
 /* Actual failed-test status must not authorize a fresh geometry context. */
 assert(mbx_context_selection(0x141,&selection)==-11 && selection==0xdeadbeefU);
 assert(mbx_context_selection(0xffffffffU,&selection)==-5 && selection==0xdeadbeefU);
 for(a=0;a<8;++a)for(b=0;b<8;++b){
  assert(!mbx_context_selection(0x01000000U|(a<<25)|(b<<28),&selection));
  assert(selection==((a<<17)|b));
 }
 assert(mbx_context_selection(0x01000020U,&selection)==-5);
 puts("MBX context: fresh-context prerequisite, all64 selection encodings and invalid status rejection PASS");
}
