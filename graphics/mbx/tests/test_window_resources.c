#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include "../common/mbx_wire_resources.h"
int main(void){
 unsigned char *p=calloc(1,1048576);unsigned frame[16]={0x3156474dU,9,64,0,800,480,0,0,0,0,0x3f800000,5};
 memcpy(p,frame,64);unsigned index;struct mbx_window_token t={11,7,3};struct mbx_wire_resources r;
 assert(!mbx_wire_resource_append_window(p,1048576,t,&index)&&index==0);
 assert(!mbx_wire_resources_parse(p,80,&r)&&r.count==1&&r.bytes==0&&r.draw_offset==80);
 assert(r.item[0].version==13&&r.item[0].reserved==11&&r.item[0].bytes==7&&r.item[0].offset==3);
 assert(!mbx_wire_resource_append_window(p,1048576,t,&index)&&index==0);
 unsigned char pixels[2304]={0};assert(!mbx_wire_resource_append_linear(p,1048576,pixels,16,16,sizeof(pixels),&index)&&index==1);
 t.slot=4;assert(!mbx_wire_resource_append_window(p,1048576,t,&index)&&index==2);
 unsigned bytes;memcpy(&bytes,p+8,4);assert(!mbx_wire_resources_parse(p,bytes,&r)&&r.count==3&&r.bytes==2304);
 assert(mbx_resources_use_linear(&r));
 struct mbx_wire_resource *last=(void *)(p+96);last->reserved=0;assert(mbx_wire_resources_parse(p,bytes,&r));last->reserved=11;
 last->bytes=0;assert(mbx_wire_resources_parse(p,bytes,&r));last->bytes=7;
 last->offset=16;assert(mbx_wire_resources_parse(p,bytes,&r));last->offset=4;
 assert(!mbx_wire_resources_parse(p,bytes,&r));free(p);
 puts("rendered image resources: mixed uploaded/token resources exact; stale structure and slot bounds rejected");
}
