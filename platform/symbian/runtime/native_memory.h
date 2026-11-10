#ifndef N810_SYMBIAN_NATIVE_MEMORY_H
#define N810_SYMBIAN_NATIVE_MEMORY_H
#include <stddef.h>
#include <stdint.h>
/* One shared backing store supports different virtual addresses in the host
 * service process and each native Symbian process. Offsets never alias until
 * the arena is destroyed; a stale process cannot acquire a new allocation. */
struct native_arena;
struct native_region {
 void *host;
 size_t size;
 uint64_t file_offset;
};
struct native_arena *native_arena_create(void);
int native_runtime_enabled(void);
struct native_arena *native_runtime_arena(void);
void *native_host_allocate(size_t size,uintptr_t guest_address);
void *native_host_map_file(const char *path,size_t size,uintptr_t guest_address);
int native_host_release(void *host);
void native_arena_destroy(struct native_arena *arena);
int native_arena_fd(const struct native_arena *arena);
int native_arena_allocate(struct native_arena *arena,size_t size,int protection,struct native_region *region);
int native_arena_release(struct native_arena *arena,const struct native_region *region);
int native_arena_resolve(struct native_arena *arena,const void *host,size_t size,uint64_t *file_offset);
/* Call in the guest worker only. Refuses to replace any existing mapping. */
void *native_region_map_guest(const struct native_arena *arena,const struct native_region *region,uintptr_t guest_address,int protection);
#endif
