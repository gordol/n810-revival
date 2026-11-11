/* SPDX-License-Identifier: MIT */
#include "mbx_vgp_wire.h"
#include "mbx_vgp_transform.h"
#include "mbx_wire_resources.h"
#ifdef __KERNEL__
#include <linux/string.h>
#else
#include <string.h>
#endif
_Static_assert(sizeof(struct mbx_vgp_wire_frame)==48,"wire frame layout");
_Static_assert(sizeof(struct mbx_vgp_wire_draw)==64,"wire draw layout");
unsigned mbx_vgp_wire_draw_bytes(const struct mbx_vgp_draw *d)
{
 if(!d||!d->instructions||d->instructions>128||d->uniform_count>83||d->immediate_count>6||
    (d->input_count!=1&&d->input_count!=2&&d->input_count!=3)||!d->vertex_count||d->vertex_count>4096||
    !d->triangle_count||d->triangle_count>256)return 0;
 return 64+8*d->instructions+16*(d->uniform_count+d->immediate_count+d->input_count*d->vertex_count)+
        ((6*d->triangle_count+3)&~3U);
}
static unsigned mbx_half_extent(unsigned n)
{
 unsigned exponent=0,m=n;
 while(m>>=1)++exponent;
 return ((exponent+126)<<23)|((n<<(23-exponent))&0x7fffff);
}
/* N95 glScissor export115 -> 804a74dc -> 804a713c. Original encoder:
 * raw screen-space mask geometry, not app vertex transforms or CPU pixels.
 * All coordinates are bounded integers; no user GPU addresses or MMIO. */
static unsigned mask_float(unsigned n)
{
 unsigned e=0,m=n;if(!n)return 0;while(m>>=1)++e;
 return ((e+127)<<23)|((n<<(23-e))&0x7fffff);
}
static int mask_emit(struct mbx_command *c,unsigned capacity,unsigned *written,
                     unsigned width,unsigned height,const unsigned *clip,unsigned operation)
{
 unsigned program[16],uniform[20]={0x3f800000,0,0,0,0,0x3f800000,0,0,
  0,0,0x3f800000,0,0,0,0,0x3f800000,0x3f800000,0x3f800000,0x3f800000,0x3f800000};
 unsigned vertices[16],i,xy[4][2]={{0,0},{2*width,0},{0,2*height},{0,0}};
 static const unsigned short indices[6]={0,1,2,1,3,2};
 if(clip){xy[0][0]=xy[1][0]=clip[0];xy[2][0]=xy[3][0]=clip[2];
  xy[0][1]=xy[2][1]=clip[1];xy[1][1]=xy[3][1]=clip[3];}
 for(i=0;i<4;++i){vertices[4*i]=mask_float(xy[i][0]);vertices[4*i+1]=mask_float(xy[i][1]);vertices[4*i+2]=vertices[4*i+3]=0x44800000;}
 struct mbx_vgp_draw d={.program=program,.uniforms=uniform,.vertices=vertices,.indices=indices,
  .instructions=8,.uniform_count=5,.input_count=1,.vertex_count=clip?4:3,.triangle_count=clip?2:1,
  .mask_operation=operation,.viewport={0,0x44800000,0,0x44800000,0,0x3f800000}};
 if(mbx_vgp_transform(0,4,112,program,16)!=8)return -22;
 return mbx_vgp_draw_encode(&d,c,capacity,written);
}
static int wire_encode(const void *data,unsigned bytes,struct mbx_command *commands,
                        unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *cache,
                        struct mbx_vgp_wire_replay_cache *replay)
{
 const struct mbx_vgp_wire_frame *f=data;
 const unsigned char *raw=data;
 unsigned offset=48,at=0,n,i,total=0;int error;
 unsigned full_clip[4],active_clip[4];
 if(!data||((unsigned long)data&3)||!commands||!written||bytes<48||bytes>MBX_VGP_WIRE_MAX_BYTES||
    f->magic!=MBX_VGP_WIRE_MAGIC||(f->version!=1&&f->version!=2&&f->version!=3&&f->version!=4&&f->version!=5&&f->version!=6&&f->version!=9&&f->version!=10)||f->bytes!=bytes||f->draws>MBX_VGP_WIRE_MAX_DRAWS||
    !f->width||!f->height||((f->width>512||f->height>512)&&!(f->version==9&&f->width==800&&f->height==480))||(f->width&1)||
    f->clear_color[3]>0x3f800000U||f->clear_depth!=0x3f800000U||(f->clear_buffers!=5&&!(f->version==10&&f->clear_buffers==0&&((f->width==240&&f->height==320)||(!f->draws&&f->width>=16&&f->width<=320&&f->height>=16&&f->height<=192&&!(f->width&15)&&!(f->height&15))))))return -22;
 /* Version9 accepts finite normalized clear RGB. Older versions retain the
  * original black-only contract. Reject before any hardware submission. */
 for(i=0;i<3;++i){
  unsigned value=f->clear_color[i];
  if(f->version>=9){if((value&0x7fffffff)>0x3f800000U||((value>>31)&&(value&0x7fffffff)))return -22;}
  else if(value&0x7fffffff)return -22;
 }
 if(replay&&!f->clear_buffers)return -22; /* external surface dependencies are not retained */
 struct mbx_wire_resources resources;if(mbx_wire_resources_parse(data,bytes,&resources))return -22;offset=resources.draw_offset;
 if(!f->clear_buffers&&(!resources.count||(resources.item[0].version!=7&&resources.item[0].version!=10&&!(resources.count==1&&(resources.item[0].version==9||resources.item[0].version==11)))||resources.bytes>MBX_WIRE_LINEAR_PAYLOAD))return -22;
 error=mbx_vgp_frame_begin(commands,capacity,&n);if(error)return error;at+=n;
 full_clip[0]=full_clip[1]=0;full_clip[2]=f->width;full_clip[3]=f->height;
 /* Only the target rectangle can produce stored pixels. Do not activate
  * out-of-target tile groups with an oversized initialization triangle. */
 error=mask_emit(commands+at,capacity-at,&n,f->width,f->height,full_clip,1);if(error)return error;at+=n;
 error=mask_emit(commands+at,capacity-at,&n,f->width,f->height,full_clip,2);if(error)return error;at+=n;
 memcpy(active_clip,full_clip,sizeof active_clip);
 if(f->clear_buffers){
  unsigned program[16];
  unsigned uniform[20]={0x3f800000,0,0,0,0,0x3f800000,0,0,
    0,0,0x3f800000,0,0,0,0,0x3f800000,0,0,0,0x3f800000};
  static const unsigned vertices[16]={0xbf800000,0xbf800000,0x3f800000,0x3f800000,
    0x3f800000,0xbf800000,0x3f800000,0x3f800000,0xbf800000,0x3f800000,0x3f800000,0x3f800000,
    0x3f800000,0x3f800000,0x3f800000,0x3f800000};
  static const unsigned short indices[6]={0,1,2,1,3,2};
  struct mbx_vgp_draw clear={.program=program,.uniforms=uniform,.vertices=vertices,.indices=indices,
    .instructions=8,.uniform_count=5,.input_count=1,.vertex_count=4,.triangle_count=2,.depth_always=1};
  /* The existing GPU clear shader reads its color from uniform4. Preserve
   * opaque clear depth and RGB565 alpha semantics; no CPU pixel generation. */
  if(f->version>=9)for(n=0;n<3;++n)uniform[16+n]=f->clear_color[n]&0x7fffffff;
  if(f->version==10)uniform[19]=f->clear_color[3];
  clear.viewport[0]=clear.viewport[1]=mbx_half_extent(f->width);
  clear.viewport[2]=mbx_half_extent(f->height);clear.viewport[3]=clear.viewport[2]|0x80000000;
  clear.viewport[4]=clear.viewport[5]=0x3f000000;
  if(mbx_vgp_transform(0,4,112,program,16)!=8)return -22;
  error=mbx_vgp_draw_encode_cached(&clear,commands+at,capacity-at,&n,cache);if(error)return error;at+=n;
 }
 for(i=0;i<f->draws;++i){
  const struct mbx_vgp_wire_draw *h;
  const unsigned *p;
  struct mbx_vgp_draw d={0};unsigned record,j,padding;
  if(bytes-offset<64)return -22;
  h=(const void *)(raw+offset);
  d.instructions=h->instructions;d.uniform_count=h->uniforms;d.immediate_count=h->immediates;
  d.color_input=(h->reserved>>17)&1;
  if(d.color_input&&f->version<9)return -22;
  d.texture_modulate=(h->reserved>>16)&1;
  if(d.texture_modulate&&(f->version<9||!(h->reserved&4)))return -22;
  d.input_count=h->inputs;d.vertex_count=h->vertices;d.triangle_count=h->triangles;
  d.smooth=h->smooth;d.cull_mode=h->cull_mode;d.blend_mode=f->version>=2?(h->reserved&3):0;d.texture_enabled=f->version>=3?((h->reserved>>2)&1):0;d.texture_input=f->version>=3?((h->reserved>>3)&1):0;d.texture_128=f->version==4&&d.texture_enabled;d.texture_native32=f->version==5&&d.texture_enabled;
  if(f->version==6||f->version>=9){
   unsigned resource=mbx_resource_index_decode(h->reserved);
   if(f->version>=9)d.depth_disabled=(h->reserved>>6)&1;
   if((!d.texture_enabled&&resource)||(d.texture_enabled&&resource>=resources.count))return -22;
   if(d.texture_enabled){if(resources.item[resource].version==10)return -22;d.texture_128=resources.item[resource].version==4||resources.item[resource].version==12;d.texture_native32=resources.item[resource].version==5||resources.item[resource].version==8||resources.item[resource].version==13||resources.item[resource].version==14;
    if(resources.item[resource].version==13||resources.item[resource].version==14){d.texture_window=resources.item[resource].offset+1;d.texture_window_native=resources.item[resource].version==14;}
    else if(resources.item[resource].version==8){d.texture_linear_width=resources.item[resource].reserved>>16;d.texture_linear_height=resources.item[resource].reserved&65535U;d.texture_linear_offset=resources.item[resource].offset;}
    else if(resources.item[resource].version==12){d.texture_arena=1;d.texture_linear_offset=resources.item[resource].offset;}
    else{d.texture_page=mbx_wire_resource_page(&resources,resource);if(!d.texture_page)return -22;}}
  }
  if(h->reserved&16384U){
   if(f->version!=10||!d.depth_disabled||d.texture_enabled||(h->reserved&15U))return -22;
   d.blend_mode=4;
  }
  for(j=0;j<6;++j)d.viewport[j]=h->viewport[j];
  record=mbx_vgp_wire_draw_bytes(&d);
  if(!record||h->bytes!=record||record>bytes-offset||(f->version==1?h->reserved:(h->reserved&~(f->version==10?(24319U|65536U|131072U):f->version==9?(24319U|65536U|131072U):f->version==6?63U:f->version>=3?15U:3U)))||total+d.triangle_count>2048)return -22;
  total+=d.triangle_count;p=(const void *)(h+1);
  d.program=p;p+=2*d.instructions;d.uniforms=p;p+=4*d.uniform_count;
  d.immediates=p;p+=4*d.immediate_count;d.vertices=p;p+=4*d.input_count*d.vertex_count;
  d.indices=(const void *)p;
  padding=(4-(6*d.triangle_count&3))&3;
  for(j=0;j<padding;++j)if(raw[offset+record-1-j])return -22;
  const unsigned *desired_clip=full_clip;
  if(h->reserved&128){
   if(!d.uniform_count)return -22;
   desired_clip=d.uniforms+4*(d.uniform_count-1);
   if(f->version<9||desired_clip[0]>=desired_clip[2]||desired_clip[1]>=desired_clip[3]||desired_clip[2]>f->width||desired_clip[3]>f->height)return -22;
  }
  /* Normal color/depth primitives do not change the persistent tile mask.
   * Re-emit only a changed rectangle, resetting the mask before a narrow
   * replacement. Only active_clip can contain set bits, so clear that
   * rectangle instead of inserting another target-wide mask primitive into
   * every tile list. Initial full mask is explicitly seeded for every frame. */
  if(memcmp(active_clip,desired_clip,sizeof active_clip)){
   if(memcmp(desired_clip,full_clip,sizeof full_clip)){
    error=mask_emit(commands+at,capacity-at,&n,f->width,f->height,active_clip,1);if(error)return error;at+=n;
   }
   error=mask_emit(commands+at,capacity-at,&n,f->width,f->height,desired_clip,2);if(error)return error;at+=n;
   memcpy(active_clip,desired_clip,sizeof active_clip);
  }
  struct mbx_vgp_draw_patches patches;
  error=mbx_vgp_draw_encode_patches(&d,commands+at,capacity-at,&n,cache,&patches);if(error)return error;
  if(replay)replay->record[i]=(struct mbx_vgp_wire_replay_record){
   .wire_offset=offset,.bytes=record,.uniform_offset=64+8*d.instructions,
   .uniform_words=4*d.uniform_count,.uniform_command=at+patches.uniform_command,
   .viewport_command=at+patches.viewport_command,.scissor_words=(h->reserved&128U)?4:0};
  at+=n;
  offset+=record;
 }
 if(offset!=bytes)return -22;
 error=mbx_vgp_frame_end(commands+at,capacity-at,&n);if(error)return error;at+=n;
 *written=at;return 0;
}
int mbx_vgp_wire_encode_cached(const void *data,unsigned bytes,struct mbx_command *commands,
                        unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *cache)
{return wire_encode(data,bytes,commands,capacity,written,cache,0);}

int mbx_vgp_wire_compile_records(const void *data,unsigned bytes,struct mbx_command *commands,
 unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *shader,
 struct mbx_vgp_wire_replay_cache *records)
{return wire_encode(data,bytes,commands,capacity,written,shader,records);}

int mbx_vgp_wire_encode_replay(const void *data,unsigned bytes,struct mbx_command *commands,
                        unsigned capacity,unsigned *written,struct mbx_vgp_shader_cache *shader,
                        struct mbx_vgp_wire_replay_cache *cache)
{
 const struct mbx_vgp_wire_frame *f=data;int error;
 if(cache){cache->bytes=cache->draws=cache->written=0;cache->owner=0;}
 /* Restore the exclusive-file legacy client contract. Versions1..6 contain
  * their complete immutable inputs; window/resident dependencies in newer
  * versions still require the explicit prepared-object lifetime path.
  * The service owns/serializes command and snapshot storage until clean close.
  * Ineligible or oversized frames retain full encoding, not a stale template. */
 if(!cache||!cache->snapshot||!data||((unsigned long)data&3)||bytes<48||
    bytes>cache->snapshot_capacity||f->version<1||f->version>6||f->clear_buffers!=5)
  return wire_encode(data,bytes,commands,capacity,written,shader,0);
 error=wire_encode(data,bytes,commands,capacity,written,shader,cache);
 if(error)return error;
 memmove(cache->snapshot,data,bytes);
 cache->bytes=bytes;cache->draws=f->draws;cache->written=*written;cache->owner=commands;
 return 0;
}
int mbx_vgp_wire_encode(const void *data,unsigned bytes,struct mbx_command *commands,unsigned capacity,unsigned *written)
{return mbx_vgp_wire_encode_cached(data,bytes,commands,capacity,written,0);}

int mbx_vgp_wire_apply_update(const void *data,unsigned bytes,unsigned generation,
 struct mbx_command *commands,unsigned capacity,unsigned *written,
 const struct mbx_vgp_wire_replay_cache *cache)
{
 const struct mbx_vgp_wire_update *h=data;const unsigned *p;
 unsigned expected=32,i,j;
 _Static_assert(sizeof(*h)==32,"template update ABI");
 if(!data||((unsigned long)data&3)||bytes<32||bytes>MBX_VGP_UPDATE_MAX_BYTES||
    !commands||!written||!cache||!cache->snapshot||cache->bytes<48||cache->draws>MBX_VGP_WIRE_MAX_DRAWS||
    cache->owner!=commands||cache->written>capacity||!generation||
    h->magic!=MBX_VGP_UPDATE_MAGIC||h->version!=1||h->bytes!=bytes||
    h->draws!=cache->draws||h->generation!=generation||
    h->reserved[0]||h->reserved[1]||h->reserved[2])return -22;
 for(i=0;i<cache->draws;++i){
  const struct mbx_vgp_wire_replay_record *r=cache->record+i;
  if(r->uniform_words>83*4||r->viewport_command>cache->written||
     cache->written-r->viewport_command<6||r->uniform_command>cache->written||
     r->uniform_words>cache->written-r->uniform_command)return -22;
  expected+=24+4*r->uniform_words;
 }
 if(bytes!=expected)return -22;
 p=(const void *)(h+1);
 /* Masks are immutable command geometry. Any scissor change requires a full
  * replacement; reject it before patching even an earlier draw. */
 for(i=0;i<cache->draws;++i){
  const struct mbx_vgp_wire_replay_record *r=cache->record+i;
  if(r->scissor_words){
   if(r->scissor_words!=4||r->uniform_words<4||r->wire_offset>cache->bytes||
      r->uniform_offset>cache->bytes-r->wire_offset||
      4*r->uniform_words>cache->bytes-r->wire_offset-r->uniform_offset)return -22;
   if(memcmp(p+6+r->uniform_words-4,cache->snapshot+r->wire_offset+r->uniform_offset+4*(r->uniform_words-4),16))return -22;
  }
  p+=6+r->uniform_words;
 }
 p=(const void *)(h+1);
 /* Validate the complete update before changing any command. */
 for(i=0;i<(bytes-32)/4;++i)if((p[i]&0x7f800000U)==0x7f800000U)return -22;
 for(i=0;i<cache->draws;++i){
  const struct mbx_vgp_wire_replay_record *r=cache->record+i;
  for(j=0;j<6;++j)commands[r->viewport_command+j].value=*p++;
  for(j=0;j<r->uniform_words;++j)commands[r->uniform_command+j].value=*p++;
 }
 *written=cache->written;return 0;
}

/* Local prepared-object API. The service must serialize these operations and
 * keep caller-owned storage alive until close succeeds. It does not submit
 * hardware or replace the service's per-job memory/guard verification. */
int mbx_vgp_prepared_create(struct mbx_vgp_prepared *o,unsigned session,
 const void *data,unsigned bytes,struct mbx_command *commands,unsigned capacity,
 unsigned char *storage,unsigned storage_bytes,struct mbx_vgp_shader_cache *shader,
 struct mbx_vgp_prepared_handle *handle)
{
 unsigned written;int error;
 if(!o||!handle||!session||!storage||!commands||bytes>storage_bytes||
    bytes>MBX_VGP_WIRE_MAX_BYTES||o->busy||o->exports||o->fault||
    (o->session&&o->session!=session)||o->generation==~0U)return -22;
 /* Failed replacement invalidates the old object before encoding can write. */
 ++o->generation;o->valid=0;o->ready=0;o->session=session;
 memset(&o->cache,0,sizeof o->cache);
 o->cache.snapshot=storage;o->cache.snapshot_capacity=storage_bytes;
 error=wire_encode(data,bytes,commands,capacity,&written,shader,&o->cache);
 if(error)return error;
 memcpy(storage,data,bytes);
 o->cache.bytes=bytes;o->cache.draws=((const struct mbx_vgp_wire_frame *)data)->draws;
 o->cache.written=written;o->cache.owner=commands;o->capacity=capacity;o->valid=1;
 *handle=(struct mbx_vgp_prepared_handle){session,o->generation};return 0;
}
static int prepared_matches(const struct mbx_vgp_prepared *o,struct mbx_vgp_prepared_handle h)
{return o&&o->valid&&h.session&&h.session==o->session&&h.generation==o->generation;}
int mbx_vgp_prepared_begin(struct mbx_vgp_prepared *o,struct mbx_vgp_prepared_handle h,
 const void *update,unsigned bytes,unsigned *written)
{
 int error;
 if(!prepared_matches(o,h)||!written||o->busy||o->exports||o->fault||(!bytes&&update))return -22;
 if(bytes){
  error=mbx_vgp_wire_apply_update(update,bytes,o->generation,o->cache.owner,o->capacity,written,&o->cache);
  if(error)return error;
 }else *written=o->cache.written;
 o->busy=1;o->ready=0;return 0;
}
int mbx_vgp_prepared_complete(struct mbx_vgp_prepared *o,struct mbx_vgp_prepared_handle h,int success)
{
 if(!prepared_matches(o,h)||!o->busy||(success!=0&&success!=1))return -22;
 o->busy=0;o->ready=success;o->fault=!success;return 0;
}
int mbx_vgp_prepared_export(struct mbx_vgp_prepared *o,struct mbx_vgp_prepared_handle h)
{
 if(!prepared_matches(o,h)||!o->ready||o->busy||o->fault||o->exports==~0U)return -22;
 ++o->exports;return 0;
}
int mbx_vgp_prepared_release(struct mbx_vgp_prepared *o,struct mbx_vgp_prepared_handle h)
{
 if(!prepared_matches(o,h)||!o->exports)return -22;
 --o->exports;return 0;
}
int mbx_vgp_prepared_close(struct mbx_vgp_prepared *o)
{
 if(!o||o->busy||o->exports)return -22;
 o->valid=o->ready=o->fault=o->session=0;
 memset(&o->cache,0,sizeof o->cache);return 0;
}

int mbx_vgp_prepared_dispatch(struct mbx_vgp_prepared *o,unsigned session,
 const void *data,unsigned bytes,struct mbx_command *commands,unsigned capacity,
 unsigned char *storage,unsigned storage_bytes,struct mbx_vgp_shader_cache *shader,
 struct mbx_vgp_prepared_handle *handle,unsigned *written)
{
 unsigned magic;int error;
 if(!o||!handle||!written||!data||bytes<4||((unsigned long)data&3))return -22;
 memcpy(&magic,data,4);
 if(magic==MBX_VGP_UPDATE_MAGIC){
  struct mbx_vgp_prepared_handle active_handle={session,o->generation};
  if(commands!=o->cache.owner||capacity!=o->capacity||storage!=o->cache.snapshot)return -22;
  error=mbx_vgp_prepared_begin(o,active_handle,data,bytes,written);
  if(!error)*handle=active_handle;
  return error;
 }
 if(magic!=MBX_VGP_WIRE_MAGIC)return -22;
 error=mbx_vgp_prepared_create(o,session,data,bytes,commands,capacity,storage,storage_bytes,shader,handle);
 if(error)return error;
 return mbx_vgp_prepared_begin(o,*handle,0,0,written);
}

int mbx_vgp_prepared_retire_after_reset(struct mbx_vgp_prepared *o,
 unsigned reset_complete,unsigned mmu_control,unsigned tables_cleared)
{
 if(!o||reset_complete!=1||tables_cleared!=1||mmu_control==~0U||
    (mmu_control&0x01010101U)||o->exports)return -22;
 if(o->busy){
  struct mbx_vgp_prepared_handle handle={o->session,o->generation};
  int error=mbx_vgp_prepared_complete(o,handle,0);if(error)return error;
 }
 return mbx_vgp_prepared_close(o);
}

int mbx_vgp_prepared_find(const struct mbx_vgp_prepared *objects,unsigned count,
 unsigned session,unsigned generation)
{
 unsigned i;
 if(!objects||!count||count>MBX_VGP_PREPARED_SLOTS||!session||!generation)return -22;
 for(i=0;i<count;++i)if(objects[i].valid&&objects[i].session==session&&objects[i].generation==generation)return (int)i;
 return -22;
}
