/* SPDX-License-Identifier: MIT. Software admission/command checks, not GPU pixels. */
#define main baseline_admission_main
#include "test_window_native_admission.c"
#undef main
#include "../mesa/window_checkpoint.h"
#include "../mesa/separate_blend.h"
#include "mbx_vgp_transform.h"
static unsigned wire[4096],rgb_wire[4096],alpha_wire[4096],saved_wire[4096];
static struct mbx_command commands[65536];
int main(void){
 baseline_admission_main();
 assert(!mbx_checkpoint_enabled(NULL)&&!mbx_checkpoint_enabled("")&&!mbx_checkpoint_enabled("0")&&!mbx_checkpoint_enabled("false")&&mbx_checkpoint_enabled("1"));
 for(unsigned layout=1;layout<=2;layout++)for(unsigned small=layout==1?1:0;small<2;small++){
  unsigned width=small?128:240,height=small?128:320,slot=small?2:0;
  gpu_windows=(struct mbx_window_state){.session=91,.layout=layout};gpu_window_native=layout==2;
  struct mbx_window_token source=render(slot,width,height);
  for(unsigned round=0;round<1000;round++){
   assert(!mbx_window_checkpoint(wire,sizeof wire,source,layout,width,height));
   struct mbx_vgp_wire_frame *f=(void*)wire;unsigned n,count;
   unsigned reference_program[16];assert(mbx_vgp_transform(0,4,112,reference_program,16)==8);assert(!memcmp(wire+36,reference_program,sizeof reference_program));
   assert(f->bytes==436&&f->draws==1&&f->clear_buffers==5);
   assert(!mbx_wire_resources_parse(wire,f->bytes,&resources));
   assert(resources.count==1&&resources.bytes==0&&resources.item[0].version==(layout==2?14U:13U));
   assert(resources.item[0].bytes==source.generation);
   assert(!mbx_vgp_wire_encode(wire,f->bytes,commands,65536,&n));
   assert(!mbx_split_separate_blend(wire,f->bytes,rgb_wire,alpha_wire,sizeof rgb_wire,&count)&&count==0);
   assert(!memcmp(wire,rgb_wire,f->bytes)&&!memcmp(wire,alpha_wire,f->bytes));
   /* Same published source survives both scratch writes; final merge alone
    * invalidates it. A direct feedback attempt fails before any mutation. */
   frame=*f;gpu_window_bound=true;gpu_window_binding=(struct mbx_window_request){.version=layout,.destination=slot};
   struct mbx_window_state before=gpu_windows;assert(admit()==-EINVAL&&!memcmp(&before,&gpu_windows,sizeof before));
   struct mbx_window_token planes[2];
   for(unsigned k=0;k<2;k++){
    gpu_window_binding.destination=14+k;assert(!admit());
    assert(!mbx_window_begin_sized(&gpu_windows,&gpu_window_binding,0,width,height));
    assert(!mbx_window_complete(&gpu_windows,1,&planes[k]));assert(!mbx_window_lookup(&gpu_windows,source));
   }
   resources.count=1;resources.item[0]=(struct mbx_wire_resource){.version=11};frame.clear_buffers=0;frame.draws=0;
   gpu_window_binding=(struct mbx_window_request){.version=layout,.destination=slot,.source={planes[0],planes[1]}};
   assert(!admit());assert(!mbx_window_begin_sized(&gpu_windows,&gpu_window_binding,2,width,height));
   assert(!mbx_window_complete(&gpu_windows,1,&planes[0]));assert(mbx_window_lookup(&gpu_windows,source));source=planes[0];
  }
  memcpy(saved_wire,wire,sizeof wire);source.generation=0;
  assert(mbx_window_checkpoint(wire,sizeof wire,source,layout,width,height)&&!memcmp(saved_wire,wire,sizeof wire));
  /* Check actual emitted top-down UV values at every pixel centre. This is
   * coordinate math validation, not a claim about hardware sample rounding. */
  const struct mbx_vgp_wire_draw *d=(void*)(wire+20);const unsigned *vertices=(const unsigned*)(d+1)+18+20;
  float u,v;memcpy(&u,vertices+12,4);memcpy(&v,vertices+21,4);
  for(unsigned y=0;y<height;y++)for(unsigned x=0;x<width;x++){
   unsigned sx=(unsigned)(((x+.5)/(double)width)*u*2048.0);
   unsigned sy=(unsigned)(((y+.5)/(double)height)*v*2048.0);assert(sx==x&&sy==y);
  }
 }
 puts("window checkpoint: 436-byte v13/v14 quad; 3000 bounded cycles; RGB/alpha scratch before merge; stale/feedback guards; every pixel-centre UV; explicit flags passed (no GPU execution)");
}
