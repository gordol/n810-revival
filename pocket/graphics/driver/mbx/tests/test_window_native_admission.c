/* SPDX-License-Identifier: MIT. Executes the real pre-hardware image admission block. */
#include <assert.h>
#include <stdbool.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
#include "mbx_vgp_wire.h"
#include "mbx_wire_resources.h"
#include "channel_request.h"
static struct mbx_window_state gpu_windows;
static struct mbx_window_request gpu_window_binding;
static struct mbx_vgp_wire_frame frame;
static const struct mbx_vgp_wire_frame *texture_job=&frame;
static struct mbx_wire_resources resources;
static struct {void *windows;} gpu_memory={(void*)1};
static bool gpu_window_bound,gpu_window_images=true,gpu_window_native=true,update,gpu_resident_surfaces,gpu_prepared_commands;
static unsigned passed;
static int channel_mask=-1;
static int admit(void){
 int e=0;unsigned i;bool resident_job,merge_job,window_merge;
#include "native_admission.inc"
 if(!e)passed++;
out:
 (void)resident_job;return e;
}
static struct mbx_window_token render(unsigned slot,unsigned w,unsigned h){
 struct mbx_window_request q={.version=gpu_windows.layout,.destination=slot};struct mbx_window_token t;
 assert(!mbx_window_begin_sized(&gpu_windows,&q,0,w,h));assert(!mbx_window_complete(&gpu_windows,1,&t));return t;
}
int main(void){
 gpu_windows=(struct mbx_window_state){.session=7,.layout=2};
 struct mbx_window_token rgb=render(14,240,320),alpha=render(15,240,320),source=render(1,240,320);
 frame=(struct mbx_vgp_wire_frame){.version=10,.width=240,.height=320};resources.count=1;resources.item[0].version=11;
 gpu_window_bound=true;gpu_window_binding=(struct mbx_window_request){.version=2,.destination=0,.source={rgb,alpha}};
 struct mbx_window_state before=gpu_windows;assert(!admit()&&passed==1&&!memcmp(&before,&gpu_windows,sizeof before));
 for(unsigned mutation=0;mutation<10;mutation++){
  struct mbx_window_request original=gpu_window_binding;struct mbx_vgp_wire_frame f=frame;unsigned saved=passed;
  if(mutation==0)gpu_window_binding.version=1;if(mutation==1)frame.width=128;if(mutation==2)frame.height=128;
  if(mutation==3)gpu_window_binding.source[0].generation++;if(mutation==4)gpu_window_binding.source[1]=rgb;
  if(mutation==5)gpu_window_binding.destination=14;if(mutation==6)frame.clear_buffers=5;
  if(mutation==7)gpu_prepared_commands=true;if(mutation==8)gpu_resident_surfaces=true;if(mutation==9)update=true;
  assert(admit()==-EINVAL&&passed==saved&&!memcmp(&before,&gpu_windows,sizeof before));
  gpu_window_binding=original;frame=f;gpu_prepared_commands=gpu_resident_surfaces=update=false;
 }
 resources.item[0]=(struct mbx_wire_resource){14,source.generation,source.slot,source.session};
 gpu_window_binding=(struct mbx_window_request){.version=2,.destination=0};frame.clear_buffers=5;
 assert(!admit());unsigned saved=passed;resources.item[0].version=13;assert(admit()==-EINVAL&&passed==saved);
 resources.item[0].version=14;resources.item[0].bytes++;assert(admit()==-EINVAL&&passed==saved);resources.item[0].bytes--;
 gpu_window_native=false;assert(admit()==-EINVAL&&passed==saved);gpu_window_native=true;
 /* Uploaded two-plane alpha merge: no source tokens, exact full dimensions,
  * no clear/draws. Run the actual service gate, not a test-only replica. */
 resources.item[0]=(struct mbx_wire_resource){9,240*320*8,0,8};resources.bytes=240*320*8;
 frame.clear_buffers=0;channel_mask=8;assert(!admit());
 gpu_window_binding.source[0]=source;assert(admit()==-EINVAL);gpu_window_binding.source[0]=(struct mbx_window_token){0};
 resources.bytes--;assert(admit()==-EINVAL);resources.bytes++;
 channel_mask=7;assert(admit()==-EINVAL);channel_mask=8;
 frame.draws=1;assert(admit()==-EINVAL);frame.draws=0;
 frame.clear_buffers=5;assert(admit()==-EINVAL);frame.clear_buffers=0;
 frame.width=128;frame.height=128;resources.bytes=128*128*8;gpu_window_binding.destination=2;assert(!admit());
 channel_mask=-1;resources.item[0]=(struct mbx_wire_resource){14,source.generation,source.slot,source.session};resources.bytes=0;
 gpu_window_bound=false;frame.version=9;frame.width=800;frame.height=480;assert(!admit());
 gpu_windows=(struct mbx_window_state){.session=8,.layout=1};gpu_window_native=false;source=render(1,128,128);
 resources.item[0]=(struct mbx_wire_resource){13,source.generation,source.slot,source.session};assert(!admit());
 puts("real service admission: native RGB/alpha/merge and compositor sampling admitted; stale/layout/shape/feedback/conflicting modes rejected before hardware");
}
