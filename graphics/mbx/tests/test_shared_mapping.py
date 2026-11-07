"""Compile actual mmap gate and reject invalid/protected mapping requests."""
from pathlib import Path
import tempfile,subprocess
s=(Path(__file__).resolve().parents[1]/'kernel/mbx_render_service.h').read_text();s=s[s.index('static int gpu_service_mmap('):s.index('static const struct file_operations gpu_service_ops=')]
prefix=r'''
#include <stdbool.h>
#include <assert.h>
#include <stdio.h>
#include <errno.h>
#define PAGE_SIZE 4096
typedef unsigned char u8;
#define virt_to_page(p) (p)
#define VM_SHARED 1
#define VM_WRITE 2
#define VM_MAYWRITE 4
#define VM_DONTEXPAND 8
#define VM_DONTDUMP 16
struct file {int unused;};
struct vm_area_struct {unsigned long vm_pgoff,vm_flags,vm_start,vm_end;};
static int gpu_service_mutex;
static bool gpu_frame_shared=true,gpu_service_active=true,gpu_service_failed;
static struct {void *device,*frame_block;unsigned frame_block_dma,frame_block_bytes;bool frame_streaming;void *frame_pages[128];unsigned frame_page_count;} gpu_memory={(void*)1,(void*)2,0x90000000,335872};
static unsigned calls,inserts,fail_insert;
static int vm_insert_page(struct vm_area_struct *v,unsigned long address,void *page){
 assert(address>=v->vm_start&&address<v->vm_end);assert(page==gpu_memory.frame_pages[(address-v->vm_start)/PAGE_SIZE]);
 assert(!(v->vm_flags&(VM_WRITE|VM_MAYWRITE)));++inserts;return inserts==fail_insert?-ENOMEM:0;
}
static void mutex_lock(int *p){assert(!*p);*p=1;}
static void mutex_unlock(int *p){assert(*p);*p=0;}
static int dma_mmap_attrs(void *d,struct vm_area_struct *v,void *p,unsigned dma,unsigned bytes,unsigned attrs){
 assert(gpu_service_mutex&&d==(void*)1&&p==(void*)2&&dma==0x90000000&&bytes==335872&&!attrs);
 assert(!(v->vm_flags&(VM_WRITE|VM_MAYWRITE))&&(v->vm_flags&(VM_DONTEXPAND|VM_DONTDUMP))==(VM_DONTEXPAND|VM_DONTDUMP));
 ++calls;return 0;
}
'''
main=r'''
int main(void){
 struct file f={0};unsigned tests=0;
 gpu_memory.frame_page_count=82;for(unsigned i=0;i<82;++i)gpu_memory.frame_pages[i]=(void *)(unsigned long)(0x80000000+i*8192);
 for(unsigned flags=0;flags<32;++flags)for(unsigned off=0;off<2;++off)for(unsigned length=0;length<3;++length){
  struct vm_area_struct v={off,flags,0x10000000,0x10000000+335872+(length==0?0:length==1?4096:-4096)};
  unsigned before=calls;bool valid=!off&&length==0&&(flags&VM_SHARED)&&!(flags&VM_WRITE);
  assert(gpu_service_mmap(&f,&v)==(valid?0:-EINVAL));assert(calls==before+valid);assert(!gpu_service_mutex);++tests;
 }
 struct vm_area_struct v={0,VM_SHARED,0,335872};
 gpu_frame_shared=false;assert(gpu_service_mmap(&f,&v)==-ENODEV);gpu_frame_shared=true;
 gpu_service_active=false;assert(gpu_service_mmap(&f,&v)==-ENODEV);gpu_service_active=true;
 gpu_service_failed=true;assert(gpu_service_mmap(&f,&v)==-ENODEV);gpu_service_failed=false;
 gpu_memory.frame_streaming=true;inserts=0;assert(!gpu_service_mmap(&f,&v));assert(inserts==82);
 inserts=0;fail_insert=11;assert(gpu_service_mmap(&f,&v)==-ENOMEM);assert(inserts==11);
 gpu_memory.frame_block=0;inserts=fail_insert=0;assert(!gpu_service_mmap(&f,&v));assert(inserts==82);
 v.vm_flags|=VM_WRITE;assert(gpu_service_mmap(&f,&v)==-EINVAL);v.vm_flags&=~VM_WRITE;
 gpu_memory.frame_page_count=0;assert(gpu_service_mmap(&f,&v)==-ENODEV);
 printf("PASS %u mapping shapes/permissions plus unavailable-owner rejection\n",tests);
}
'''
with tempfile.TemporaryDirectory(prefix='mbx-mmap-') as d:
 c=Path(d)/'test.c';c.write_text(prefix+s+main);exe=Path(d)/'test'
 subprocess.run(['cc','-O2','-fsanitize=address,undefined',str(c),'-o',str(exe)],check=True);subprocess.run([str(exe)],check=True)
