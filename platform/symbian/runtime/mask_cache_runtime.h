/* SPDX-License-Identifier: MIT. Bounded cache of resident GPU mask outputs. */
#pragma once
#include "runtime_debug.h"
#include "mask_cache.h"
#include "mask_tiles.h"
#include <GL/osmesa.h>
#include <memory>
namespace {
constexpr uint64_t mask_charge=128U*128U*8U+4096U;
struct mask_cache_state {
 std::unique_ptr<mbx_mask::cache> cache;OSMesaContext owner=nullptr;
 bool invalidate_pending=false;unsigned cached_limit=0;
 unsigned long long hits=0,misses=0,bypasses=0;
};
thread_local mask_cache_state mask_cache_state_;
void mask_release(unsigned name){glDeleteTextures(1,&name);}
void mask_finish(){if(sg_sprite_batch_flush())throw std::runtime_error("Mask consumer flush failed");glFinish();}
void mask_cache_drain(){auto &s=mask_cache_state_;if(s.cache&&s.invalidate_pending){mask_finish();s.cache->clear(mask_release);s.invalidate_pending=false;}}
void mask_cache_init(){
 auto &s=mask_cache_state_;auto ctx=OSMesaGetCurrentContext();
 if(!ctx||(s.owner&&s.owner!=ctx))throw std::runtime_error("Resident mask context mismatch");
 if(s.owner)return;
 using query_fn=int(*)(mbx_window_layout*);auto query=reinterpret_cast<query_fn>(dlsym(RTLD_DEFAULT,"n810_mbx_window_get_layout"));
 mbx_window_layout layout{};if(!query||query(&layout)||!mbx_window_layout_valid(&layout))throw std::runtime_error("Resident mask layout unavailable");
 const char *f=std::getenv("N810_MBX_WINDOW_FIRST"),*n=std::getenv("N810_MBX_WINDOW_COUNT");
 unsigned first=f?unsigned(std::strtoul(f,nullptr,10)):0,count=n?unsigned(std::strtoul(n,nullptr,10)):14;
 if(!mbx_window_range_valid(first,count))throw std::runtime_error("Resident mask partition invalid");
 unsigned slots=0;for(unsigned i=first;i<first+count;i++)if((layout.client_mask&(1U<<i))&&!(layout.native_mask&(1U<<i)))++slots;
 if(!slots)throw std::runtime_error("No small resident mask slot in partition");
 s.owner=ctx;s.cached_limit=std::min(3U,slots-1);
 s.cache=std::make_unique<mbx_mask::cache>(reinterpret_cast<uintptr_t>(ctx),s.cached_limit*mask_charge,s.cached_limit);
}
mbx_mask::source mask_describe(const sg_mask_source &input){
 mbx_mask::source out;out.lifetime=input.lifetime;out.generation=input.generation;out.name=input.name;out.width=input.width;out.height=input.height;out.tracked=input.tracked!=0;
 glBindTexture(GL_TEXTURE_2D,input.name);
 const GLenum sampler[]={GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER,GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T};
 const GLenum swizzle[]={GL_TEXTURE_SWIZZLE_R,GL_TEXTURE_SWIZZLE_G,GL_TEXTURE_SWIZZLE_B,GL_TEXTURE_SWIZZLE_A};
 for(unsigned i=0;i<4;i++){glGetTexParameteriv(GL_TEXTURE_2D,sampler[i],&out.sampler[i]);glGetTexParameteriv(GL_TEXTURE_2D,swizzle[i],&out.swizzle[i]);}
 return out;
}
mbx_mask::key mask_key(const sg_mask_source &source,const sg_mask_source &mask,unsigned flags){
 GLint active=0,binding=0;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 mbx_mask::key key;key.context=reinterpret_cast<uintptr_t>(OSMesaGetCurrentContext());key.image=mask_describe(source);key.mask=mask_describe(mask);key.flags=flags;
 glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);return key;
}
sg_mask_image mask_create(const sg_mask_source &source,const sg_mask_source &mask,unsigned flags,const sg::mask_tile &tile,unsigned reusable=0){
 auto &s=mask_cache_state_;
 sg_mask_image image=reusable?sg_mask_image{reusable,{}}:sg_gpu_mask_allocate();
 for(;;){
  int error=sg_gpu_mask_region(source.name,mask.name,image.texture,flags,tile.x,tile.y,tile.width,tile.height,&image.view);
  if(!error)break;
  if(error==-ENOSPC&&s.cache->evict_oldest(mask_release))continue;
  if(!reusable)glDeleteTextures(1,&image.texture);
  throw std::runtime_error("Resident GPU mask rejected: "+std::to_string(error));
 }
 if(image.view.width!=tile.width||image.view.height!=tile.height||image.view.storage_width!=128||image.view.storage_height!=128){if(!reusable)glDeleteTextures(1,&image.texture);throw std::runtime_error("Resident mask view mismatch");}
 return image;
}
}
#include "mask_batch_runtime.h"
extern "C" void sg_mask_source_retire(unsigned long long lifetime){
 if(mask_page_references(lifetime)){mask_finish();mask_page_.reset();}
 auto &s=mask_cache_state_;if(!s.cache||!lifetime||!s.cache->references(lifetime))return;
 if(s.owner!=OSMesaGetCurrentContext()){s.invalidate_pending=true;return;}
 mask_finish();mask_cache_drain();s.cache->invalidate(lifetime,mask_release);
}
extern "C" void sg_mask_cache_close(){
 mask_page_close();auto &s=mask_cache_state_;if(!s.cache)return;
 if(s.owner==OSMesaGetCurrentContext()){mask_finish();s.cache->close(mask_release);}
 s.cache.reset();s.owner=nullptr;s.invalidate_pending=false;
 if(n810_runtime_debug())std::fprintf(stderr,"GPU_MASK_CACHE hits=%llu misses=%llu streamed=%llu retained_bytes=0\n",s.hits,s.misses,s.bypasses);
 s.hits=s.misses=s.bypasses=0;
}
extern "C" int sg_mask_sprite_draw(const sg_sprite *sprite,const sg_mask_source *source,const sg_mask_source *mask,unsigned flags,
 int (*draw)(const sg_sprite *,void *),void *opaque){
 if(!sprite||!source||!mask||!draw||source->width!=mask->width||source->height!=mask->height||(flags&~12U))return -1;
 n810_command_profile::scope profile(83);mask_cache_init();mask_cache_drain();auto &s=mask_cache_state_;
 if(mask_page_draw(*sprite,*source,*mask,flags,draw,opaque))return 0;
 const bool small=source->width<=128&&source->height<=128;
 sg::mask_tile single{};unsigned tile_count=0;
 if(!small)sg::mask_tiles(*sprite,source->width,source->height,[&](const sg::mask_tile &tile){if(!tile_count)single=tile;++tile_count;});
 auto key=mask_key(*source,*mask,flags);
 if(!small&&tile_count==1){key.x=single.x;key.y=single.y;key.width=single.width;key.height=single.height;}
 // Cache one atlas tile when a crop fits it. Multi-tile images keep the one
 // streaming allocation, avoiding allocation churn for images larger than LRU.
 const bool cacheable=(small||tile_count==1)&&s.cached_limit&&std::getenv("N810_SYMBIAN_MASK_CACHE")&&s.cache->accepts(key);
 unsigned temporary=0;
 auto consume=[&](sg::mask_tile tile){
  unsigned result=cacheable?s.cache->find(key):0;bool borrowed=result!=0;
  if(borrowed)++s.hits;
  else {
   mask_finish();
   if(cacheable)while(s.cache->size()>=s.cached_limit)s.cache->evict_oldest(mask_release);
   auto image=mask_create(*source,*mask,flags,tile,cacheable?0:temporary);result=image.texture;
   if(cacheable){++s.misses;borrowed=s.cache->insert(key,result,mask_charge,mask_release);}
   else ++s.bypasses;
  }
  if(!borrowed)temporary=result;
  tile.sprite.texture=result;
  if(draw(&tile.sprite,opaque))throw std::runtime_error("Resident mask sprite failed");
 };
 try {
 if(!small&&tile_count==1)consume(single);
 else sg::mask_tiles(*sprite,source->width,source->height,consume);
 if(temporary){mask_finish();glDeleteTextures(1,&temporary);temporary=0;}
 }catch(...){
  // On a failed GPU flush, keep the texture owned by its context until teardown.
  if(temporary){try{mask_finish();glDeleteTextures(1,&temporary);}catch(...){}}
  throw;
 }
 return 0;
}
