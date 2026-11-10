#define _GNU_SOURCE
#define _FILE_OFFSET_BITS 64
#include "native_memory.h"
#include <sys/mman.h>
#include <sys/shm.h>
#include <unistd.h>
#include <errno.h>
#include <stdlib.h>
#include <pthread.h>
#include <string.h>
#include <limits.h>
#include <fcntl.h>
#include <linux/falloc.h>
#ifndef MAP_FIXED_NOREPLACE
#define MAP_FIXED_NOREPLACE 0x100000
#endif
struct allocation {struct native_region region;unsigned char *lazy_pages;struct allocation *next;};
struct native_arena {int fd;size_t page;uint64_t end;pthread_mutex_t lock;struct allocation *allocations;};
struct native_arena *native_arena_create(void){
 struct native_arena*a=calloc(1,sizeof *a);if(!a)return 0;
 a->page=sysconf(_SC_PAGESIZE);a->fd=memfd_create("symbian-native-memory",MFD_CLOEXEC);
 if(a->fd<0){free(a);return 0;}int e=pthread_mutex_init(&a->lock,0);if(e){close(a->fd);free(a);errno=e;return 0;}return a;
}
int native_arena_fd(const struct native_arena*a){return a->fd;}
static int allocate_colored(struct native_arena*a,size_t size,int protection,uintptr_t color,struct native_region*out){
 if(!size || size>SIZE_MAX-(a->page-1)){errno=EINVAL;return -1;}
 size=(size+a->page-1)&~(a->page-1);struct allocation*n=calloc(1,sizeof *n);if(!n)return -1;
 pthread_mutex_lock(&a->lock);uint64_t offset=(a->end+SHMLBA-1)&~(uint64_t)(SHMLBA-1);offset+=color&(SHMLBA-1);uint64_t end=offset+size;
 if(end>UINT64_C(8)*1024*1024*1024 || ftruncate(a->fd,(off_t)end)){pthread_mutex_unlock(&a->lock);free(n);errno=ENOMEM;return -1;}
 void*p=mmap(0,size,protection,MAP_SHARED,a->fd,(off_t)offset);
 if(p==MAP_FAILED){pthread_mutex_unlock(&a->lock);free(n);return -1;}
 n->region=(struct native_region){p,size,offset};a->end=end;n->next=a->allocations;a->allocations=n;*out=n->region;
 pthread_mutex_unlock(&a->lock);return 0;
}
int native_arena_resolve(struct native_arena*a,const void*host,size_t size,uint64_t*out){
 uintptr_t p=(uintptr_t)host;int found=0;pthread_mutex_lock(&a->lock);
 for(struct allocation*n=a->allocations;n;n=n->next){uintptr_t base=(uintptr_t)n->region.host;
  if(p>=base && p-base<n->region.size && size<=n->region.size-(p-base)){if(n->lazy_pages && size){
   size_t first=(p-base)/a->page,last=(p-base+size-1)/a->page;
   for(size_t page=first;page<=last;++page)if(!n->lazy_pages[page]){
    char *target=(char*)n->region.host+page*a->page;off_t offset=(off_t)(n->region.file_offset+page*a->page);
    ssize_t copied;do{copied=pwrite(a->fd,target,a->page,offset);}while(copied<0&&errno==EINTR);
    if(copied!=(ssize_t)a->page){pthread_mutex_unlock(&a->lock);return -1;}
    void *mapped=mmap(target,a->page,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_FIXED,a->fd,offset);
    if(mapped!=target){pthread_mutex_unlock(&a->lock);return -1;}
    n->lazy_pages[page]=1;
   }
  }
  *out=n->region.file_offset+(p-base);found=1;break;}}
 pthread_mutex_unlock(&a->lock);if(!found){errno=EFAULT;return -1;}return 0;
}
int native_arena_release(struct native_arena*a,const struct native_region*r){
 pthread_mutex_lock(&a->lock);struct allocation**link=&a->allocations;
 while(*link && ((*link)->region.host!=r->host || (*link)->region.file_offset!=r->file_offset || (*link)->region.size!=r->size))link=&(*link)->next;
 if(!*link){pthread_mutex_unlock(&a->lock);errno=EINVAL;return -1;}
 struct allocation*n=*link;if(fallocate(a->fd,FALLOC_FL_PUNCH_HOLE|FALLOC_FL_KEEP_SIZE,(off_t)n->region.file_offset,(off_t)n->region.size)){pthread_mutex_unlock(&a->lock);return -1;}if(munmap(n->region.host,n->region.size)){pthread_mutex_unlock(&a->lock);return -1;}
 *link=n->next;pthread_mutex_unlock(&a->lock);free(n->lazy_pages);free(n);return 0;
}
void *native_region_map_guest(const struct native_arena*a,const struct native_region*r,uintptr_t address,int protection){
 if(address<0x10000 || address>=0xb0000000 || r->size>0xb0000000-address || address%a->page || r->file_offset%a->page){errno=EINVAL;return MAP_FAILED;}
 void*p=mmap((void*)address,r->size,protection,MAP_SHARED|MAP_FIXED_NOREPLACE,a->fd,(off_t)r->file_offset);
 if(p!=MAP_FAILED && p!=(void*)address){munmap(p,r->size);errno=EEXIST;return MAP_FAILED;}return p;
}
void native_arena_destroy(struct native_arena*a){if(!a)return;struct allocation*n=a->allocations;while(n){struct allocation*next=n->next;munmap(n->region.host,n->region.size);free(n->lazy_pages);free(n);n=next;}close(a->fd);pthread_mutex_destroy(&a->lock);free(a);}

int native_arena_allocate(struct native_arena*a,size_t size,int protection,struct native_region*out){return allocate_colored(a,size,protection,0,out);}
static pthread_once_t runtime_once=PTHREAD_ONCE_INIT;
static struct native_arena *runtime_arena;
static void init_runtime_arena(void){runtime_arena=native_arena_create();}
int native_runtime_enabled(void){const char*p=getenv("N810_SYMBIAN_CPU");return p&&!strcmp(p,"native");}
struct native_arena *native_runtime_arena(void){pthread_once(&runtime_once,init_runtime_arena);return runtime_arena;}
void *native_host_allocate(size_t size,uintptr_t guest_address){struct native_region r;struct native_arena*a=native_runtime_arena();if(!a||allocate_colored(a,size,PROT_NONE,guest_address,&r))return 0;return r.host;}
int native_host_release(void *host){struct native_arena*a=native_runtime_arena();if(!a)return -1;struct native_region r={0};pthread_mutex_lock(&a->lock);for(struct allocation*n=a->allocations;n;n=n->next)if(n->region.host==host){r=n->region;break;}pthread_mutex_unlock(&a->lock);if(!r.host)return 0;return native_arena_release(a,&r)?-1:1;}

/* Original file stays MAP_PRIVATE. Promote a page into shared backing only
 * when a native worker needs it; prior host patches are copied with that page.
 * Callers serialize guest memory mutations through the runtime kernel lock. */
void *native_host_map_file(const char *path,size_t size,uintptr_t guest_address){
 struct native_arena*a=native_runtime_arena();struct native_region r;
 if(!a || !size || size%a->page){errno=EINVAL;return 0;}
 int fd=open(path,O_RDONLY|O_CLOEXEC);if(fd<0)return 0;
 if(allocate_colored(a,size,PROT_NONE,guest_address,&r)){close(fd);return 0;}
 unsigned char *pages=calloc(size/a->page,1);
 void *mapped=pages?mmap(r.host,size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_FIXED,fd,0):MAP_FAILED;close(fd);
 if(mapped!=r.host){free(pages);native_arena_release(a,&r);return 0;}
 pthread_mutex_lock(&a->lock);for(struct allocation*n=a->allocations;n;n=n->next)if(n->region.host==r.host){n->lazy_pages=pages;break;}pthread_mutex_unlock(&a->lock);
 return r.host;
}
