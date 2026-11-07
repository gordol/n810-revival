#include <assert.h>
#include <stdint.h>
#include "draw_mbx_buffers.h"
int main(void){
 setenv("N810_MBX_REUSE_VERTEX_BUFFERS","1",1);
 for(unsigned c=0;c<32;++c){struct mbx_vertex_buffers b={0};
  for(unsigned n=1;n<=4096;n*=2){
   size_t bytes=n*80+64;void *a=mbx_vertex_alloc(&b,0,bytes),*d=mbx_vertex_alloc(&b,1,bytes);
   assert(a&&d&&a!=d);memset(a,0xa5,bytes);memset(d,0x5a,bytes);
   mbx_vertex_release(&b,a);mbx_vertex_release(&b,d);
   assert(mbx_vertex_alloc(&b,0,bytes)==a);assert(mbx_vertex_alloc(&b,1,bytes)==d);
   assert(((uint8_t *)a)[bytes-1]==0xa5&&((uint8_t *)d)[bytes-1]==0x5a);
   void *other=malloc(bytes);mbx_vertex_release(&b,other);
  }
  void *large=mbx_vertex_alloc(&b,0,1024*1024+1);assert(large!=b.data[0]&&large!=b.data[1]);mbx_vertex_release(&b,large);
  mbx_vertex_buffers_destroy(&b);assert(!b.data[0]&&!b.data[1]);
 }
 unsetenv("N810_MBX_REUSE_VERTEX_BUFFERS");struct mbx_vertex_buffers b={0};
 void *a=mbx_vertex_alloc(&b,0,4096);assert(!b.data[0]);mbx_vertex_release(&b,a);mbx_vertex_buffers_destroy(&b);
 puts("PASS retained fetch/shade separation, growth, temporary/oversized release, destruction and disabled mode");
}
