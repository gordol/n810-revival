"""Inject corruption at every protected word into actual production checks."""
from pathlib import Path
import tempfile,subprocess
root=Path(__file__).resolve().parents[1]
header='\n'.join(l for l in (root/'kernel/mbx_dma.h').read_text().splitlines() if not l.startswith('#include'))
s=(root/'kernel/mbx_dma.c').read_text();s=s[s.index('/* Check every word,'):]
prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;typedef uint32_t __le32;typedef uint8_t u8;typedef uint64_t dma_addr_t;
#define TABLE_BYTES 32768
#define PAGE_BYTES 4096
#define le32_to_cpu(x) (x)
#define dma_rmb() ((void)0)
'''
main=r'''
int main(void){
 struct mbx_dma_memory m={0};m.stage=MBX_DMA_QUIESCED;
 m.tables=malloc(TABLE_BYTES);m.guard=malloc(4096);m.target=malloc(4096);m.ta=malloc(36864);
 m.guard_dma=0x90000000;m.target_dma=0x90001000;m.parameters_dma=0x90002000;m.tiles_dma=0x90012000;m.ta_dma=0x90020000;
 memset(m.guard,0xa5,4096);memset(m.target,0x3c,4096);memset((u8 *)m.ta+32768,0x5a,4096);
 unsigned tests=0;
 for(unsigned pages=0;pages<=128;pages+=1){
  m.frame_page_count=pages;for(unsigned i=0;i<pages;++i)m.frame_dma[i]=0x91000000+i*8192;
  u32 *t=m.tables;
  /* Independent specification of the original page-table mapping. */
  for(unsigned i=0;i<8192;++i)t[i]=i==1?m.target_dma:i>=16&&i<32?m.parameters_dma+4096*(i-16):
   i>=32&&i<36?m.tiles_dma+4096*(i-32):i>=256&&i<256+pages?m.frame_dma[i-256]:
   i>=128&&i<132?m.ta_dma+4096*(i-128):i==144?m.ta_dma+16384:i==146?m.ta_dma+20480:
   i==148?m.ta_dma+24576:i==152?m.ta_dma+28672:m.guard_dma;
  assert(!mbx_dma_verify_bounds(&m));
  for(unsigned i=0;i<8192;++i){t[i]^=1;assert(mbx_dma_verify_bounds(&m)==-EOVERFLOW);t[i]^=1;++tests;}
 }
 void *buffers[]={m.guard,(u8 *)m.target+2048,(u8 *)m.ta+32768};unsigned words[]={1024,512,1024};
 for(unsigned b=0;b<3;++b)for(unsigned i=0;i<words[b];++i){
  u32 *v=buffers[b];v[i]^=1;assert(mbx_dma_verify_bounds(&m)==(b==1?-EILSEQ:-EOVERFLOW));v[i]^=1;++tests;
 }
 assert(!mbx_dma_verify_bounds(&m));m.stage=MBX_DMA_EMPTY;assert(mbx_dma_verify_bounds(&m)==-EBUSY);
 free(m.tables);free(m.guard);free(m.target);free(m.ta);
 printf("PASS %u independent per-word corruption injections; all 0..128 frame mappings\n",tests);
}
'''
with tempfile.TemporaryDirectory(prefix='mbx-verify-') as d:
 c=Path(d)/'test.c';c.write_text(prefix+header+s+main);exe=Path(d)/'test'
 subprocess.run(['cc','-std=gnu11','-O2','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
