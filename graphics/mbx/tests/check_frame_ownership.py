"""Exercise actual frame map/unmap functions with a checked DMA ownership model."""
from pathlib import Path
import subprocess,tempfile
r=Path(__file__).resolve().parents[1];s=(r/'kernel/mbx_dma.c').read_text();code=s[s.index('int mbx_dma_frame_for_device('):s.index('int mbx_dma_release(')]
pre=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <errno.h>
typedef uint64_t u64;typedef uintptr_t dma_addr_t;
#define PAGE_BYTES 4096U
#define DMA_ATTR_SKIP_CPU_SYNC 1
#define DMA_BIDIRECTIONAL 0
static u64 gpu_frame_device_ns,gpu_frame_cpu_ns,gpu_frame_clean_skipped_bytes;
static unsigned cleans,invalidates,maps,unmaps,syncs;static int fail_at;
static u64 ktime_get_ns(void){static u64 t;return ++t;}
static void *virt_to_page(void *p){return p;}
static dma_addr_t dma_map_page_attrs(void *d,void *p,unsigned offset,unsigned bytes,int dir,unsigned long attrs){(void)d;(void)offset;(void)bytes;(void)dir;if(!(attrs&1))cleans++;if((int)++maps==fail_at)return 0;return (uintptr_t)p;}
static int dma_mapping_error(void *d,dma_addr_t a){(void)d;return !a;}
static void dma_unmap_page_attrs(void *d,dma_addr_t a,unsigned bytes,int dir,unsigned long attrs){(void)d;(void)a;(void)bytes;(void)dir;unmaps++;if(!(attrs&1))invalidates++;}
struct mbx_dma_memory {void *device,*frame_block,*frame_pages[4];dma_addr_t frame_dma[4],frame_block_dma;unsigned frame_map_first,frame_active,frame_image_pages,frame_page_count,frame_mapped_pages,frame_block_bytes;bool frame_sample_other,frame_streaming,frame_device_owned,frame_cpu_reads_only;unsigned long frame_map_attrs;};
void mbx_dma_frame_for_cpu(struct mbx_dma_memory *m);
'''
post=r'''
int main(void){
 struct mbx_dma_memory m={.frame_streaming=1,.frame_image_pages=4,.frame_page_count=4};
 for(unsigned i=0;i<4;i++)m.frame_dma[i]=(uintptr_t)(m.frame_pages[i]=(void *)(uintptr_t)(4096*(i+1)));
 assert(!mbx_dma_frame_for_device(&m));assert(cleans==4&&maps==4&&m.frame_device_owned);
 mbx_dma_frame_for_cpu(&m);assert(invalidates==4&&unmaps==4&&!m.frame_device_owned);
 m.frame_cpu_reads_only=true;
 for(unsigned i=0;i<1000;i++){assert(!mbx_dma_frame_for_device(&m));mbx_dma_frame_for_cpu(&m);}
 assert(cleans==4&&invalidates==4004&&syncs==0&&maps==unmaps&&gpu_frame_clean_skipped_bytes==16384000);
 fail_at=maps+3;assert(mbx_dma_frame_for_device(&m)==-ENOMEM);assert(!m.frame_device_owned&&!m.frame_mapped_pages&&maps==unmaps+1);
 puts("frame ownership: 1000 read-only cycles retain all completion invalidations; partial map failure drains safely");
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(pre+code+post)
 subprocess.run(['cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
