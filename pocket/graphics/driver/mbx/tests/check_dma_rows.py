"""Check the actual contiguous DMA-span helper against fragmented mappings."""
from pathlib import Path
import subprocess,tempfile
root=Path(__file__).resolve().parents[1]
s=(root/'kernel/mbx_dma_sink.h').read_text()
fn=s[s.index('static size_t mbx_dma_span('):s.index('static struct page *mbx_cpu_page(')]
code=r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#define PAGE_SIZE 4096
#define min_t(type,a,b) ((type)(a)<(type)(b)?(type)(a):(type)(b))
struct mbx_dma_page { uintptr_t address; };
'''+fn+r'''
int main(void){
 struct mbx_dma_page src[128],dst[256];unsigned cases=0;
 for(unsigned gap=1;gap<=128;gap*=2){
  for(unsigned i=0;i<128;i++)src[i].address=0x100000+i*4096+(i/gap)*8192;
  for(unsigned i=0;i<256;i++)dst[i].address=0x400000+i*4096+(i/(gap+1))*4096;
  for(unsigned y=0;y<16;y++)for(unsigned x=0;x<16;x++){
   unsigned width=400-x,height=256-y,sp=800,dp=1600,row=0;
   while(row<height){
    size_t so=(y+row)*sp+x*2,to=(y+row)*dp+x*2,left=width*2;
    size_t sn=mbx_dma_span(src,128,so,(height-1-row)*sp+left);
    size_t dn=mbx_dma_span(dst,256,to,(height-1-row)*dp+left);
    unsigned rows=min_t(size_t,sn<left?0:1+(sn-left)/sp,dn<left?0:1+(dn-left)/dp);
    if(rows>1){
     for(unsigned k=0;k<rows;k++)for(unsigned b=0;b<left;b++){
      size_t a=so+k*sp+b,d=to+k*dp+b;
      assert(src[a/4096].address+a%4096==src[so/4096].address+so%4096+k*sp+b);
      assert(dst[d/4096].address+d%4096==dst[to/4096].address+to%4096+k*dp+b);
     }
     row+=rows;
    }else row++;
   }
   cases++;
  }
 }
 printf("DMA grouped rows: %u fragmented/aligned rectangle cases preserve byte addresses\n",cases);
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d);(p/'test.c').write_text(code)
 subprocess.run(['cc','-O2','-fsanitize=address,undefined',str(p/'test.c'),'-o',str(p/'test')],check=True)
 subprocess.run([str(p/'test')],check=True)
