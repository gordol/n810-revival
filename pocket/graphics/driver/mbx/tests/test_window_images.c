#include <assert.h>
#include <string.h>
#include <stdio.h>
#include "../common/mbx_window_images.h"
int main(void){
 struct mbx_window_state s={.session=17},before;struct mbx_window_token t[16],out;
 for(unsigned i=0;i<16;i++){
  struct mbx_window_request q={.version=1,.destination=i};assert(!mbx_window_begin(&s,&q,0));
  before=s;assert(mbx_window_begin(&s,&q,0));assert(!memcmp(&s,&before,sizeof(s)));
  assert(!mbx_window_complete(&s,1,t+i));assert(!mbx_window_lookup(&s,t[i]));
 }
 struct mbx_window_request q={.version=1,.destination=2,.source={t[0],t[1]}};
 assert(!mbx_window_begin(&s,&q,2));assert(mbx_window_lookup(&s,t[2]));
 assert(!mbx_window_complete(&s,1,&out));assert(mbx_window_lookup(&s,t[2]));assert(!mbx_window_lookup(&s,out));
 for(unsigned mutation=0;mutation<6;mutation++){
  struct mbx_window_request bad=q;
  if(mutation==0)bad.source[0].session++;
  if(mutation==1)bad.source[0].generation++;
  if(mutation==2)bad.source[0].slot=16;
  if(mutation==3)bad.destination=0;
  if(mutation==4)bad.source[1]=bad.source[0];
  if(mutation==5)bad.version=2;
  before=s;assert(mbx_window_begin(&s,&bad,2));assert(!memcmp(&s,&before,sizeof(s)));
 }
 assert(!mbx_window_begin(&s,&q,2));assert(mbx_window_complete(&s,0,&out));assert(!out.session&&!out.generation&&!out.slot);
 s.serial=~0U;before=s;assert(mbx_window_begin(&s,&q,2));assert(!memcmp(&s,&before,sizeof(s)));
 mbx_window_invalidate(&s);assert(mbx_window_lookup(&s,t[0]));
 puts("rendered image ownership: stale/alias/pending/wrap/failure rejected; completion-only publication");
}
