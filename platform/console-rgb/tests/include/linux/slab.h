#include <stdlib.h>
#include <stdint.h>
#define GFP_KERNEL 0
static inline void *kmalloc_array(size_t n,size_t size,int flags) {
 (void)flags;
 return size && n<=SIZE_MAX/size ? malloc(n*size) : NULL;
}
