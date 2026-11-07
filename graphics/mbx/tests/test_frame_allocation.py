"""Compile the actual allocator with DMA ownership mocks and inject failures."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
header='\n'.join(l for l in (root/'kernel/mbx_dma.h').read_text().splitlines() if not l.startswith('#include'))
source=(root/'kernel/mbx_dma.c').read_text()
source=source[source.index('static bool valid_address'):source.index('int mbx_dma_attach')]
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
typedef uint64_t dma_addr_t;typedef uint64_t u64;typedef uint32_t u32;typedef uint32_t __le32;typedef uint8_t u8;
struct device {unsigned refs;};
#define PAGE_BYTES 4096U
#define TABLE_BYTES 32768U
#define GFP_KERNEL 0
#define DMA_BIT_MASK(n) 0xffffffffU
#define DIV_ROUND_UP(n,d) (((n)+(d)-1)/(d))
#define PAGE_ALIGN(n) (((n)+4095U)&~4095U)
#define cpu_to_le32(n) (n)
#define dma_wmb() ((void)0)
static unsigned probe_mode=2,gpu_frame_capacity_bytes=332800;
static bool gpu_frame_contiguous,gpu_frame_streaming;
#define DMA_BIDIRECTIONAL 0
#define virt_to_page(p) (p)
static unsigned streaming_maps;
static unsigned map_calls,map_fail_at;
static bool map_fail,map_move;
static unsigned display_base=0x87100000,display_bytes=770048;
static unsigned calls,fail_at,overlap_at,live;
static dma_addr_t next_address;
static struct {dma_addr_t address;size_t bytes;bool active;} mappings[512];
struct allocation {void *ptr;size_t bytes;dma_addr_t address,mapped_address;bool mapped;} owned[256];
static int dma_set_mask_and_coherent(struct device *d,unsigned mask){return 0;}
static struct device *get_device(struct device *d){++d->refs;return d;}
static void put_device(struct device *d){assert(d->refs);--d->refs;}
static void *dma_alloc_coherent(struct device *d,size_t n,dma_addr_t *addr,int flags){
 ++calls;if(calls==fail_at)return NULL;
 void *p=NULL;assert(!posix_memalign(&p,16384,n));next_address=(next_address+16383)&~16383ULL;*addr=calls==overlap_at?display_base-4096:next_address;
 next_address+=PAGE_ALIGN(n)+4096;owned[calls]=(struct allocation){p,n,*addr};++live;return p;
}
static void dma_free_coherent(struct device *d,size_t n,void *p,dma_addr_t addr){
 for(unsigned i=1;i<=calls;++i)if(owned[i].ptr==p){
  assert(owned[i].bytes==n && owned[i].address==addr);free(p);owned[i].ptr=NULL;--live;return;
 }
 assert(!"double free or freeing a sub-page of the owning block");
}
static void *alloc_pages_exact(size_t n,int flags){dma_addr_t address;return dma_alloc_coherent(NULL,n,&address,flags);}
static void free_pages_exact(void *p,size_t n){assert(!streaming_maps);for(unsigned i=1;i<=calls;++i)if(owned[i].ptr==p){dma_free_coherent(NULL,n,p,owned[i].address);return;}assert(0);}
static dma_addr_t dma_map_page_attrs(struct device *d,void *p,unsigned off,size_t n,int direction,unsigned attrs){
 assert(!off&&!attrs);if(map_fail||++map_calls==map_fail_at)return 0xffffffffU;
 for(unsigned i=1;i<=calls;++i)if(owned[i].ptr&&(uintptr_t)p>=(uintptr_t)owned[i].ptr && (uintptr_t)p+n<=(uintptr_t)owned[i].ptr+owned[i].bytes){
  dma_addr_t a=owned[i].address+((uintptr_t)p-(uintptr_t)owned[i].ptr)+(map_move?4096:0);
  for(unsigned j=0;j<512;++j)if(!mappings[j].active){mappings[j].active=true;mappings[j].address=a;mappings[j].bytes=n;++streaming_maps;return a;}
 }assert(0);return 0;
}
static void dma_unmap_page_attrs(struct device *d,dma_addr_t address,size_t n,int direction,unsigned attrs){
 for(unsigned i=0;i<512;++i)if(mappings[i].active&&mappings[i].address==address){assert(mappings[i].bytes==n);mappings[i].active=false;--streaming_maps;return;}assert(0);
}
static bool dma_mapping_error(struct device *d,dma_addr_t address){return address==0xffffffffU;}
static void mbx_background32(void *p,unsigned words){}
static void mbx_tile_headers(void *p,unsigned words,unsigned a,unsigned b,unsigned c,unsigned d){}
'''
main=r'''
static void reset(unsigned fail,unsigned overlap){assert(!live);memset(owned,0,sizeof owned);calls=0;map_calls=map_fail_at=0;fail_at=fail;overlap_at=overlap;next_address=0x90000000;}
int main(void){
 struct device d={0};unsigned checked=0;
 for(unsigned contiguous=0;contiguous<4;++contiguous){
  gpu_frame_contiguous=contiguous==1||contiguous==2;gpu_frame_streaming=contiguous>=2;unsigned expected=gpu_frame_contiguous?7:contiguous==3?27:88;
  for(unsigned fail=1;fail<=expected+1;++fail){
   reset(fail,0);struct mbx_dma_memory m={0};int e=mbx_dma_allocate(&d,&m);
   if(contiguous==2&&fail==7){assert(!e&&!m.frame_block&&m.frame_page_count==82&&streaming_maps==82);assert(!mbx_dma_release(&m));assert(!live&&!d.refs);continue;}
   if(fail<=expected){assert(e==-ENOMEM);assert(!d.refs&&!live);}
   else{
    assert(!e&&m.frame_page_count==82);
    if(m.frame_streaming&&!m.frame_block)for(unsigned j=0;j<82;++j)assert(((uintptr_t)m.frame_pages[j]&16383)==((j*4096)&16383));
    for(unsigned i=0;i<82;++i)assert(((__le32 *)m.tables)[MBX_FRAME_VA/4096+i]==m.frame_dma[i]);
    assert(((__le32 *)m.tables)[MBX_FRAME_VA/4096+82]==m.guard_dma);
    if(gpu_frame_contiguous)for(unsigned i=0;i<82;++i)assert(m.frame_pages[i]==(u8 *)m.frame_block+i*4096);
    m.stage=MBX_DMA_SUBMITTED;assert(mbx_dma_release(&m)==-EBUSY);assert(live==expected);
    m.stage=MBX_DMA_QUIESCED;assert(!mbx_dma_release(&m));assert(!live&&!d.refs);
   }
   ++checked;
  }
 }
 gpu_frame_streaming=false;gpu_frame_contiguous=true;reset(0,7);struct mbx_dma_memory m={0};
 assert(mbx_dma_allocate(&d,&m)==-ERANGE);assert(!live&&!d.refs);
 gpu_frame_streaming=true;reset(0,0);map_fail=true;
 assert(mbx_dma_allocate(&d,&m)==-ENOMEM);assert(!live&&!streaming_maps&&!d.refs);map_fail=false;
 reset(0,7);assert(mbx_dma_allocate(&d,&m)==-ERANGE);assert(!live&&!streaming_maps&&!d.refs);
 reset(0,0);assert(!mbx_dma_allocate(&d,&m));assert(m.frame_device_owned&&streaming_maps==1);
 m.stage=MBX_DMA_SUBMITTED;mbx_dma_frame_for_cpu(&m);assert(!m.frame_device_owned&&!streaming_maps);
 mbx_dma_frame_for_cpu(&m);assert(!streaming_maps);
 assert(!mbx_dma_frame_for_device(&m));assert(m.frame_device_owned&&streaming_maps==1);
 assert(!mbx_dma_frame_for_device(&m));assert(streaming_maps==1);
 mbx_dma_frame_for_cpu(&m);map_move=true;
 assert(mbx_dma_frame_for_device(&m)==-ERANGE);assert(!m.frame_device_owned&&!streaming_maps);map_move=false;
 map_fail=true;assert(mbx_dma_frame_for_device(&m)==-ENOMEM);assert(!streaming_maps);map_fail=false;
 assert(mbx_dma_release(&m)==-EBUSY);m.stage=MBX_DMA_QUIESCED;
 assert(!mbx_dma_release(&m));assert(!live&&!d.refs&&!streaming_maps);
 /* Scatter remap must unwind every mapped prefix without changing PTEs. */
 gpu_frame_contiguous=false;gpu_frame_streaming=true;
 for(unsigned fail=1;fail<=82;++fail){
  reset(0,0);map_fail_at=fail;assert(mbx_dma_allocate(&d,&m)==-ENOMEM);assert(!live&&!streaming_maps&&!d.refs);
  reset(0,0);assert(!mbx_dma_allocate(&d,&m));assert(streaming_maps==82&&!m.frame_block);
  mbx_dma_frame_for_cpu(&m);map_calls=0;map_fail_at=fail;
  assert(mbx_dma_frame_for_device(&m)==-ENOMEM);assert(!streaming_maps&&!m.frame_device_owned);
  map_fail_at=0;assert(!mbx_dma_frame_for_device(&m));assert(streaming_maps==82);
  assert(!mbx_dma_release(&m));assert(!live&&!streaming_maps&&!d.refs);
 }
 gpu_frame_streaming=false;
 for(unsigned n=0;n<2;++n){reset(0,0);gpu_frame_capacity_bytes=n?524289:0;assert(mbx_dma_allocate(&d,&m)==-EINVAL);assert(!calls&&!live&&!d.refs);}
 printf("PASS: %u allocation failure/success cases, active-DMA release refusal, display overlap rejection, capacity bounds, exact owning-block release, streaming ownership and DMA remap failure/movement\n",checked);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(prefix+header+"\n"+source+main)
 subprocess.run(['cc','-O1','-g','-fsanitize=address,undefined','-o',str(p/'test'),str(p/'test.c')],check=True)
 subprocess.run([str(p/'test')],check=True)
