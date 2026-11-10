#include "runtime_debug.h"
/* SPDX-License-Identifier: MIT. Cache only verified GPU-produced mask images. */
#pragma once
#include "mask_cache.h"
#include <GL/osmesa.h>
#include <memory>
namespace {
struct mask_cache_state {
 std::unique_ptr<mbx_mask::cache> cache;
 OSMesaContext owner=nullptr;
 bool invalidate_pending=false;
 unsigned long long hits=0,misses=0,bypasses=0;
};
thread_local mask_cache_state mask_cache_state_;
void mask_release(unsigned name){glDeleteTextures(1,&name);}
void mask_cache_drain(){auto &s=mask_cache_state_;if(s.cache&&s.owner==OSMesaGetCurrentContext()&&s.invalidate_pending){s.cache->clear(mask_release);s.invalidate_pending=false;}}
mbx_mask::source mask_describe(const sg_mask_source &input){
 mbx_mask::source out;out.lifetime=input.lifetime;out.generation=input.generation;out.name=input.name;out.width=input.width;out.height=input.height;out.tracked=input.tracked!=0;
 glBindTexture(GL_TEXTURE_2D,input.name);
 const GLenum sampler[]={GL_TEXTURE_MIN_FILTER,GL_TEXTURE_MAG_FILTER,GL_TEXTURE_WRAP_S,GL_TEXTURE_WRAP_T};
 const GLenum swizzle[]={GL_TEXTURE_SWIZZLE_R,GL_TEXTURE_SWIZZLE_G,GL_TEXTURE_SWIZZLE_B,GL_TEXTURE_SWIZZLE_A};
 for(unsigned i=0;i<4;++i){glGetTexParameteriv(GL_TEXTURE_2D,sampler[i],&out.sampler[i]);glGetTexParameteriv(GL_TEXTURE_2D,swizzle[i],&out.swizzle[i]);}
 return out;
}
}
extern "C" void sg_mask_source_retire(unsigned long long lifetime){
 auto &s=mask_cache_state_;if(!s.cache||!lifetime)return;
 if(s.owner!=OSMesaGetCurrentContext()){s.invalidate_pending=true;return;}
 mask_cache_drain();s.cache->invalidate(lifetime,mask_release);
}
extern "C" void sg_mask_cache_close(){
 auto &s=mask_cache_state_;if(!s.cache)return;
 if(s.owner!=OSMesaGetCurrentContext()) {
  // Never delete GL names in another context or throw from driver teardown.
  // Drop metadata now; the owning context reclaims its textures on destruction.
  std::fprintf(stderr,"GPU_MASK_CACHE teardown_context_mismatch context_owned_handles=%zu\n",s.cache->size());
 } else s.cache->close(mask_release);
 s.cache.reset();s.owner=nullptr;
 if(n810_runtime_debug()) std::fprintf(stderr,"GPU_MASK_CACHE hits=%llu misses=%llu bypasses=%llu retained_bytes=0\n",s.hits,s.misses,s.bypasses);
 s.hits=s.misses=s.bypasses=0;s.invalidate_pending=false;
}
/* Texture-preserving fast lookup for a pending sprite batch. No allocation,
 * eviction, retirement, GPU rendering or synchronization is permitted here.
 * GL bindings are restored; a miss keeps the existing flush-before-create path. */
extern "C" unsigned sg_mask_texture_try_cached(const sg_mask_source *source,const sg_mask_source *mask,unsigned flags){
 auto &s=mask_cache_state_;
 if(!source||!mask||!std::getenv("N810_SYMBIAN_MASK_CACHE")||!s.cache||s.invalidate_pending||
    !source->tracked||!mask->tracked||!source->lifetime||!mask->lifetime||
    s.owner!=OSMesaGetCurrentContext())return 0;
 GLint active,binding;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 mbx_mask::key key;key.context=reinterpret_cast<uintptr_t>(s.owner);key.image=mask_describe(*source);key.mask=mask_describe(*mask);key.flags=flags;
 glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);
 auto hit=s.cache->find(key);if(hit)++s.hits;return hit;
}
extern "C" unsigned sg_mask_texture_cached(const sg_mask_source *source,const sg_mask_source *mask,unsigned flags,int *borrowed){
 n810_command_profile::scope mask_profile(83);
 *borrowed=0;auto &s=mask_cache_state_;
 if(!std::getenv("N810_SYMBIAN_MASK_CACHE")||!source->tracked||!mask->tracked||!source->lifetime||!mask->lifetime){++s.bypasses;return sg_gpu_mask_texture(source->name,mask->name,flags);}
 auto context=OSMesaGetCurrentContext();
 if(!context||(s.cache&&s.owner!=context)){++s.bypasses;return sg_gpu_mask_texture(source->name,mask->name,flags);}
 if(!s.cache){s.owner=context;s.cache=std::make_unique<mbx_mask::cache>(reinterpret_cast<uintptr_t>(context),1024*1024,64);}
 mask_cache_drain();
 GLint active,binding;glGetIntegerv(GL_ACTIVE_TEXTURE,&active);glActiveTexture(GL_TEXTURE0);glGetIntegerv(GL_TEXTURE_BINDING_2D,&binding);
 mbx_mask::key key;key.context=reinterpret_cast<uintptr_t>(context);key.image=mask_describe(*source);key.mask=mask_describe(*mask);key.flags=flags;
 glBindTexture(GL_TEXTURE_2D,binding);glActiveTexture(active);
 if(!s.cache->accepts(key)){++s.bypasses;return sg_gpu_mask_texture(source->name,mask->name,flags);}
 if(auto hit=s.cache->find(key)){++s.hits;*borrowed=1;return hit;}
 ++s.misses;auto result=sg_gpu_mask_texture(source->name,mask->name,flags);
 // Conservative bound: full RGBA mip chain plus allocation/texture overhead.
 // Current helper creates only level zero with nearest minification.
 const uint64_t charge=uint64_t(source->width)*source->height*8+8192;
 if(s.cache->insert(key,result,charge,mask_release))*borrowed=1;
 return result;
}
