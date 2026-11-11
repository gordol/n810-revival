/* SPDX-License-Identifier: MIT */
/* Compile the actual service-open function with allocator fault injection. */
#include "mbx_vgp_wire.h"
#include "mbx_command_cache.h"
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct inode { unsigned size; };
struct file { struct inode inode; void *private_data; };
static unsigned allocations,live,fail_at;
static void *vmalloc(size_t bytes){
 void *p;if(++allocations==fail_at)return NULL;
 p=malloc(bytes);assert(p);++live;return p;
}
static void vfree(void *p){if(p){assert(live);--live;free(p);}}
static unsigned gpu_service_mutex,gpu_resident_session,gpu_resident_slots;
static unsigned gpu_service_shader_cache,gpu_resident_result,gpu_surface_lease;
static unsigned gpu_surface_session,gpu_surface_generation,gpu_template_serial;
static unsigned gpu_wire_replay_hits,gpu_wire_replay_misses;
static struct mbx_command_cache *gpu_service_command_cache;
static bool gpu_command_reuse,gpu_service_command_cache_unavailable;
static unsigned gpu_command_cache_hits,gpu_command_cache_misses,gpu_command_cache_bypasses;
static unsigned gpu_template_generation,gpu_template_uploads,gpu_template_updates;
static unsigned gpu_template_upload_bytes,gpu_template_update_bytes;
static unsigned gpu_template_copy_ns,gpu_template_encode_ns,gpu_full_copy_ns,gpu_full_encode_ns;
static unsigned gpu_frame_selected;
static bool gpu_service_active=true,gpu_service_failed,gpu_service_opened;
static bool gpu_resident_surfaces,gpu_frame_shared,gpu_resident_bound,gpu_merge_bound;
#include "../common/mbx_texture_resident.h"
static struct mbx_texture_resident gpu_texture_resident;
static struct mbx_window_state gpu_windows;
static struct mbx_window_token gpu_window_result;
static bool gpu_window_bound;
static void *gpu_texture_resident_wire;
static bool gpu_prepared_commands,gpu_wire_replay=true,gpu_window_native;
static struct { unsigned frame_images,frame_active,frame_block_bytes;void *linear; } gpu_memory;
typedef unsigned char u8;
static unsigned gpu_verification_mode,gpu_verification_checks,gpu_verification_jobs;
static int gpu_error,guard_error,gpu_bounds_verified;
static bool gpu_last_guard_checked;
static void mbx_dma_sink_release_channel(void){}
static int mbx_dma_verify_bounds(void *p){(void)p;return guard_error;}
static int mbx_texture_equal(const void *a,const void *b,unsigned n){return !memcmp(a,b,n);}
static void *gpu_service_wire;
static struct mbx_command *gpu_service_commands;
static struct mbx_vgp_prepared gpu_prepared_slots[MBX_VGP_PREPARED_SLOTS];
static struct mbx_command *gpu_prepared_storage[MBX_VGP_PREPARED_SLOTS];
static unsigned gpu_prepared_slot,gpu_prepared_next;
#define gpu_service_prepared (gpu_prepared_slots[gpu_prepared_slot])
#define gpu_service_replay_cache (gpu_service_prepared.cache)
#define mutex_lock(p) ((void)(p))
#define mutex_unlock(p) ((void)(p))
#define mbx_surface_slots_open(p,s) (*(p)=(s))
#define mbx_surface_slots_invalidate(p) (*(p)=0)
#define file_inode(p) (&(p)->inode)
#define i_size_write(p,s) ((p)->size=(s))
struct kernel_param { void *arg; };
static int param_set_bool(const char *text,const struct kernel_param *p){
 if(strcmp(text,"0")&&strcmp(text,"1"))return -EINVAL;
 *(bool*)p->arg=text[0]=='1';return 0;
}
static const struct {int (*set)(const char*,const struct kernel_param*);} param_ops_bool={param_set_bool};
#include "command_reuse_set.inc"
/* Generated verbatim from kernel/mbx_render_service.h by check_prepared.py. */
#include "service_open.inc"
#include "service_retire.inc"
static void clear_allocations(void){
 vfree(gpu_service_wire);
 if(gpu_prepared_commands){
  for(unsigned i=0;i<MBX_VGP_PREPARED_SLOTS;++i){vfree(gpu_prepared_storage[i]);gpu_prepared_storage[i]=NULL;vfree(gpu_prepared_slots[i].cache.snapshot);}
 }else{vfree(gpu_service_commands);vfree(gpu_service_replay_cache.snapshot);}
 gpu_service_wire=NULL;gpu_service_commands=NULL;
 memset(gpu_prepared_slots,0,sizeof gpu_prepared_slots);gpu_service_opened=false;gpu_service_failed=false;
 assert(!live);allocations=fail_at=0;
}
static void command_cache_release(void){
 struct kernel_param p={&gpu_command_reuse};
 gpu_service_opened=true;
 assert(gpu_command_reuse_set("1",&p)==-EBUSY&&!gpu_command_reuse);
 gpu_service_opened=false;
 assert(gpu_command_reuse_set("bad",&p)==-EINVAL&&!gpu_command_reuse);
 assert(!gpu_command_reuse_set("1",&p)&&gpu_command_reuse);
 assert(!gpu_command_reuse_set("0",&p)&&!gpu_command_reuse);
 gpu_command_reuse=true;fail_at=allocations+1;
 gpu_service_init_command_cache();assert(!gpu_service_command_cache&&gpu_service_command_cache_unavailable);
 unsigned attempted=allocations;gpu_service_init_command_cache();assert(allocations==attempted);
 fail_at=0;gpu_service_command_cache_unavailable=false;gpu_service_init_command_cache();
 assert(gpu_service_command_cache&&live==1);
 gpu_service_free_storage();assert(!gpu_service_command_cache&&!live);
 allocations=fail_at=0;gpu_command_reuse=false;
}
static void selection_guards(void){
 struct mbx_vgp_prepared *o=gpu_prepared_slots+2;
 gpu_prepared_next=2;gpu_template_serial=50;o->generation=9;
 o->busy=1;assert(gpu_service_select_prepared(1024)==-EBUSY);o->busy=0;
 assert(o->generation==9&&gpu_prepared_next==2&&gpu_prepared_slot==0&&gpu_service_commands==gpu_prepared_storage[0]);
 o->exports=1;assert(gpu_service_select_prepared(1024)==-EBUSY);o->exports=0;
 assert(o->generation==9&&gpu_prepared_next==2&&gpu_prepared_slot==0&&gpu_service_commands==gpu_prepared_storage[0]);
 o->fault=1;assert(gpu_service_select_prepared(1024)==-EIO);o->fault=0;
 assert(o->generation==9&&gpu_prepared_next==2&&gpu_prepared_slot==0&&gpu_service_commands==gpu_prepared_storage[0]);
 gpu_template_serial=~0U;assert(gpu_service_select_prepared(1024)==-EOVERFLOW);
 assert(o->generation==9&&gpu_prepared_next==2&&gpu_prepared_slot==0&&gpu_service_commands==gpu_prepared_storage[0]);
 gpu_template_serial=50;fail_at=allocations+1;
 assert(gpu_service_select_prepared(1024)==-ENOMEM);
 assert(o->generation==9&&gpu_prepared_next==2&&gpu_prepared_slot==0&&!o->cache.snapshot);
 fail_at=0;assert(!gpu_service_select_prepared(1024));
 assert(o->cache.snapshot_capacity==1024);
 void *saved=o->cache.snapshot;memset(saved,0xa5,1024);
 gpu_prepared_next=2;fail_at=allocations+1;
 assert(gpu_service_select_prepared(2048)==-ENOMEM);
 assert(o->cache.snapshot==saved&&o->cache.snapshot_capacity==1024&&((unsigned char*)saved)[1023]==0xa5);
 assert(gpu_prepared_next==2&&o->generation==50);
 fail_at=0;unsigned before=allocations;
 assert(!gpu_service_select_prepared(512));assert(allocations==before&&o->cache.snapshot==saved);
 gpu_prepared_next=2;
 assert(gpu_service_select_prepared(MBX_VGP_WIRE_MAX_BYTES+1)==-EINVAL);
 assert(allocations==before&&o->cache.snapshot==saved&&gpu_prepared_next==2);
 assert(!gpu_service_select_prepared(2048));
 assert(o->cache.snapshot_capacity==2048&&o->cache.snapshot!=saved);


 assert(o->generation==50&&gpu_prepared_next==3&&gpu_prepared_slot==2&&gpu_service_commands==gpu_prepared_storage[2]);
 puts("service selection: rejected replacements preserve generation, selected storage and replacement cursor");
}
int main(void){
 command_cache_release();
 struct file file={0};unsigned session;
 gpu_prepared_commands=true;
 for(unsigned failure=1;failure<=1+MBX_VGP_PREPARED_SLOTS;++failure){
  clear_allocations();fail_at=failure;session=gpu_surface_session;
  assert(gpu_service_open(NULL,&file)==-ENOMEM);
  assert(!gpu_service_opened&&!live&&!gpu_service_wire&&!gpu_service_commands);
  assert(gpu_surface_session==session);
 }
 clear_allocations();assert(!gpu_service_open(NULL,&file));
 assert(gpu_service_opened&&live==1+MBX_VGP_PREPARED_SLOTS&&!gpu_service_replay_cache.snapshot);
 assert(!gpu_service_replay_cache.snapshot_capacity);
 selection_guards();
 for(unsigned i=0;i<MBX_VGP_PREPARED_SLOTS;i++){
  gpu_prepared_slots[i].valid=1;gpu_prepared_slots[i].session=gpu_surface_session;
  gpu_prepared_slots[i].generation=i+1;gpu_prepared_slots[i].cache.owner=gpu_prepared_storage[i];
 }
 gpu_prepared_slots[2].busy=1;
 assert(!gpu_service_close(NULL,&file));assert(!gpu_service_opened&&gpu_service_failed&&live==6);
 assert(gpu_service_retire_prepared(0,0,1)==-EINVAL);assert(live==6&&gpu_prepared_slots[2].busy);
 gpu_prepared_slots[1].exports=1;
 assert(gpu_service_retire_prepared(1,0,1)==-EINVAL);assert(live==6&&gpu_prepared_slots[0].valid);
 gpu_prepared_slots[1].exports=0;
 assert(!gpu_service_retire_prepared(1,0,1));assert(!live&&!gpu_service_wire&&!gpu_service_commands);
 clear_allocations();assert(!gpu_service_open(NULL,&file));
 gpu_prepared_slots[1].valid=1;gpu_prepared_slots[1].session=gpu_surface_session;
 gpu_prepared_slots[1].generation=1;gpu_prepared_slots[1].exports=1;
 assert(!gpu_service_close(NULL,&file));assert(!gpu_service_opened&&gpu_service_failed&&live==5);
 assert(gpu_service_retire_prepared(1,0,1)==-EINVAL);assert(live==5);
 gpu_prepared_slots[1].exports=0;
 assert(!gpu_service_retire_prepared(1,0,1));assert(!live&&!gpu_service_wire&&!gpu_service_commands);
 puts("service close: an exported idle slot retains storage until release and verified retirement");
 clear_allocations();assert(!gpu_service_open(NULL,&file));
 session=gpu_surface_session;assert(gpu_service_open(NULL,&file)==-EBUSY);
 assert(gpu_surface_session==session&&live==1+MBX_VGP_PREPARED_SLOTS);clear_allocations();
 gpu_prepared_commands=false;fail_at=3;
 assert(!gpu_service_open(NULL,&file));
 assert(gpu_service_opened&&live==2&&!gpu_service_replay_cache.snapshot);
 clear_allocations();gpu_wire_replay=false;
 assert(!gpu_service_open(NULL,&file));assert(allocations==2&&live==2);
 gpu_texture_resident_wire=vmalloc(MBX_VGP_WIRE_MAX_BYTES);assert(gpu_texture_resident_wire);gpu_texture_resident.data=(unsigned char*)gpu_texture_resident_wire+80;gpu_texture_resident.valid=1;
 assert(!gpu_service_close(NULL,&file));assert(!live&&!gpu_texture_resident_wire&&!gpu_texture_resident.data);
 clear_allocations();gpu_service_failed=false;gpu_verification_mode=1;guard_error=-EILSEQ;
 assert(!gpu_service_open(NULL,&file));assert(!gpu_service_close(NULL,&file));
 assert(gpu_service_failed&&gpu_error==-EILSEQ&&live==2);
 guard_error=0;gpu_service_failed=false;assert(!gpu_service_close(NULL,&file));assert(!live);
 gpu_verification_mode=0;
 clear_allocations();puts("normal verification: failed close checkpoint retains storage; clean retry releases");
 puts("service open: required allocation failures return ENOMEM without leaks; default cache remains optional");
 return 0;
}
