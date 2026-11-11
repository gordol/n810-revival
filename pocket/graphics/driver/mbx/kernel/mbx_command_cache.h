/* SPDX-License-Identifier: MIT */
#ifndef MBX_COMMAND_CACHE_H
#define MBX_COMMAND_CACHE_H
#include "mbx_vgp_wire.h"
#include "mbx_wire_resources.h"
/* CPU command compilation only, not surface ownership or GPU residency.
 * The service must still validate current window tokens/bindings, upload current
 * texture pixels, and run its ordinary admission/synchronization/guard checks.
 * Store a private command copy: channel jobs patch their output after encoding.
 * Exact keys include all shader, geometry and scissor bytes. Uniforms and
 * viewport may change after complete finite-value validation, as with the
 * existing compact-update path; only their recorded command words are patched.
 * Texture payload does not affect compilation. Window session/generation do not
 * affect the encoded slot address, and are checked anew by the service per job.
 * No hashing or caller pointers establish equality. Oversize jobs fall back.
 */
#define MBX_COMMAND_CACHE_SLOTS 4U
#define MBX_COMMAND_CACHE_KEY_BYTES 32768U
#define MBX_COMMAND_CACHE_COMMANDS 32768U
struct mbx_command_cache_entry {
 unsigned key_bytes,header_bytes,commands;
 struct mbx_vgp_wire_replay_cache patches;
 unsigned char key[MBX_COMMAND_CACHE_KEY_BYTES];
 struct mbx_command command[MBX_COMMAND_CACHE_COMMANDS];
};
struct mbx_command_cache {
 unsigned next,hits,misses,bypasses;
 struct mbx_command_cache_entry entry[MBX_COMMAND_CACHE_SLOTS];
};
static inline int mbx_command_cache_header_equal(const struct mbx_command_cache_entry *e,
 const unsigned char *raw,const struct mbx_wire_resources *r)
{
 unsigned i;
 if(memcmp(e->key,raw,64))return 0;
 for(i=0;i<r->count;++i){
  const unsigned char *a=raw+64+16*i,*b=e->key+64+16*i;
  /* The parser checked the complete descriptor and current nonzero token.
   * Only slot/layout participate in code generation for window images. */
  if(r->item[i].version==13||r->item[i].version==14){
   if(memcmp(a,b,4)||memcmp(a+8,b+8,4))return 0;
  }else if(memcmp(a,b,16))return 0;
 }
 return 1;
}
static inline int mbx_command_cache_draws_equal(const struct mbx_command_cache_entry *e,
 const unsigned char *raw,unsigned bytes,const struct mbx_wire_resources *r)
{
 const struct mbx_vgp_wire_frame *f=(const void*)raw;
 unsigned at=r->draw_offset,old=e->header_bytes,i,j;
 if(!f->clear_buffers)return !memcmp(e->key+old,raw+at,bytes-at);
 for(i=0;i<f->draws;++i){
  const struct mbx_vgp_wire_replay_record *p=e->patches.record+i;
  const struct mbx_vgp_wire_draw *d=(const void*)(raw+at);
  unsigned tail=p->uniform_offset+4*p->uniform_words;
  if(memcmp(raw+at,e->key+old,36)||d->reserved!=((const struct mbx_vgp_wire_draw*)(e->key+old))->reserved||
     memcmp(raw+at+64,e->key+old+64,p->uniform_offset-64)||
     memcmp(raw+at+tail,e->key+old+tail,p->bytes-tail))return 0;
  const unsigned *u=(const void*)(raw+at+p->uniform_offset);
  for(j=0;j<6;++j)if((d->viewport[j]&0x7f800000U)==0x7f800000U)return 0;
  for(j=0;j<p->uniform_words;++j)if((u[j]&0x7f800000U)==0x7f800000U)return 0;
  if(p->scissor_words&&memcmp(raw+at+tail-16,e->key+old+tail-16,16))return 0;
  at+=p->bytes;old+=p->bytes;
 }
 return at==bytes;
}
static inline void mbx_command_cache_patch(const struct mbx_command_cache_entry *e,
 const unsigned char *raw,unsigned draw_offset,struct mbx_command *commands)
{
 const struct mbx_vgp_wire_frame *f=(const void*)raw;unsigned at=draw_offset,i,j;
 if(!f->clear_buffers)return;
 for(i=0;i<f->draws;++i){
  const struct mbx_vgp_wire_replay_record *p=e->patches.record+i;
  const struct mbx_vgp_wire_draw *d=(const void*)(raw+at);
  const unsigned *u=(const void*)(raw+at+p->uniform_offset);
  for(j=0;j<6;++j)commands[p->viewport_command+j].value=d->viewport[j];
  for(j=0;j<p->uniform_words;++j)commands[p->uniform_command+j].value=u[j];
  at+=p->bytes;
 }
}
/* Internal service variant: r describes this immutable, already parsed frame.
 * Reusing that parse avoids another large ARM kernel-stack scratch table. */
static inline int mbx_command_cache_encode_parsed(struct mbx_command_cache *cache,
 const void *data,unsigned bytes,struct mbx_command *commands,unsigned capacity,
 unsigned *written,struct mbx_vgp_shader_cache *shader,const struct mbx_wire_resources *r)
{
 const struct mbx_vgp_wire_frame *f=data;const unsigned char *raw=data;
 unsigned key_bytes,i;int error;
 if(!cache||!data||((unsigned long)data&3)||bytes<64||!commands||!written||
    (f->version!=9&&f->version!=10))
  return mbx_vgp_wire_encode_cached(data,bytes,commands,capacity,written,shader);
 key_bytes=r->data_offset+bytes-r->draw_offset;
 if(key_bytes>MBX_COMMAND_CACHE_KEY_BYTES){++cache->bypasses;
  return mbx_vgp_wire_encode_cached(data,bytes,commands,capacity,written,shader);}
 for(i=0;i<MBX_COMMAND_CACHE_SLOTS;++i){
  const struct mbx_command_cache_entry *e=cache->entry+i;
  if(e->key_bytes!=key_bytes||e->header_bytes!=r->data_offset||
     !mbx_command_cache_header_equal(e,raw,r)||
     !mbx_command_cache_draws_equal(e,raw,bytes,r))continue;
  if(e->commands>capacity)return -22;
  memcpy(commands,e->command,e->commands*sizeof(*commands));
  mbx_command_cache_patch(e,raw,r->draw_offset,commands);
  *written=e->commands;++cache->hits;return 0;
 }
 ++cache->misses;
 struct mbx_command_cache_entry *e=cache->entry+(cache->next++%MBX_COMMAND_CACHE_SLOTS);
 e->key_bytes=0;
 error=mbx_vgp_wire_compile_records(data,bytes,commands,capacity,written,shader,
                                  f->clear_buffers?&e->patches:0);
 if(error)return error;
 if(*written>MBX_COMMAND_CACHE_COMMANDS){++cache->bypasses;return 0;}
 memcpy(e->key,raw,r->data_offset);
 memcpy(e->key+r->data_offset,raw+r->draw_offset,bytes-r->draw_offset);
 memcpy(e->command,commands,*written*sizeof(*commands));
 e->header_bytes=r->data_offset;e->commands=*written;e->key_bytes=key_bytes;
 return 0;
}
static inline int mbx_command_cache_encode(struct mbx_command_cache *cache,
 const void *data,unsigned bytes,struct mbx_command *commands,unsigned capacity,
 unsigned *written,struct mbx_vgp_shader_cache *shader)
{
 struct mbx_wire_resources r;int error;
 if(!data||((unsigned long)data&3)||bytes<64||bytes>MBX_VGP_WIRE_MAX_BYTES)
  return mbx_vgp_wire_encode_cached(data,bytes,commands,capacity,written,shader);
 error=mbx_wire_resources_parse(data,bytes,&r);if(error)return error;
 return mbx_command_cache_encode_parsed(cache,data,bytes,commands,capacity,written,shader,&r);
}
#endif
