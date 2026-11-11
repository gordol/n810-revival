// SPDX-License-Identifier: MIT
#pragma once
#include "mask_batch_plan.h"
#include "sprite_region_bounds.h"
#include <array>
namespace {
using mask_page_fn=int(*)(unsigned,const mbx_window_channel_item*,unsigned,mbx_window_view*);
struct mask_page_state {
 OSMesaContext owner=nullptr;unsigned texture=0,count=0,width=0,height=0;
 bool composed=false,failed=false;sg::mask_shelf shelf;
 std::array<mbx_window_channel_item,64> items{};
 std::array<std::array<unsigned long long,4>,64> identities{};
 unsigned long long pages=0,sprites=0;
 void reset(){count=width=height=0;composed=false;shelf.reset();}
};
thread_local mask_page_state mask_page_;
mask_page_fn mask_page_api(){static auto fn=reinterpret_cast<mask_page_fn>(dlsym(RTLD_DEFAULT,"n810_mbx_window_channels_batch"));return fn;}
bool mask_page_references(unsigned long long id){auto &s=mask_page_;if(!id||s.composed)return false;for(unsigned i=0;i<s.count;i++)if(s.identities[i][0]==id||s.identities[i][2]==id)return true;return false;}
int mask_page_prepare(){
 auto &s=mask_page_;if(s.failed)return -1;if(!s.count||s.composed)return 0;
 // Region rejection can leave descriptors with no sprite consumer at all.
 // Discard that input-only page instead of submitting invisible GPU work.
 if(!sg_sprite_batch_pending()){s.reset();return 0;}
 if(s.owner!=OSMesaGetCurrentContext()||!mask_page_api())return -1;
 // Pending sprite consumers are still queued in the runtime. Finish only the
 // previous GL work before rewriting this page; never recurse into its queue.
 glFinish();mbx_window_view view{};
 int error=mask_page_api()(s.texture,s.items.data(),s.count,&view);
 if(error||view.width!=s.width||view.height!=s.height||view.storage_width!=128||view.storage_height!=128){s.failed=true;return -1;}
 s.composed=true;++s.pages;return 0;
}
int mask_page_draw(const sg_sprite &sprite,const sg_mask_source &source,const sg_mask_source &mask,unsigned flags,int(*draw)(const sg_sprite*,void*),void *opaque){
 const char *enabled=std::getenv("N810_SYMBIAN_MASK_BATCH"),*merge=std::getenv("N810_MBX_CHANNEL_UPLOAD_MERGE");
 if(!enabled||std::strcmp(enabled,"1")||!merge||std::strcmp(merge,"1")||!sg_sprite_batch_active()||!mask_page_api()||!source.tracked||!mask.tracked||!source.lifetime||!mask.lifetime||!source.generation||!mask.generation)return 0;
 GLint viewport[4];glGetIntegerv(GL_VIEWPORT,viewport);sg::box bounds;sg::mask_crop crop;
 if(!sg::unit_sprite_bounds(sprite,viewport,sprite.projection[5]<0,bounds)||!sg::mask_batch_crop(sprite,source.width,source.height,crop))return 0;
 auto &s=mask_page_;if(s.failed)throw std::runtime_error("Mask page previously failed");
 if(!s.texture){
  mask_finish();mask_cache_state_.cache->clear(mask_release);
  s.owner=OSMesaGetCurrentContext();s.texture=sg_gpu_mask_allocate().texture;
 }
 if(s.owner!=OSMesaGetCurrentContext())throw std::runtime_error("Mask page context mismatch");
 const std::array<unsigned long long,4> identity={source.lifetime,source.generation,mask.lifetime,mask.generation};
 const unsigned mode=flags&8U?MBX_WINDOW_BINARY_RED_ALPHA:MBX_WINDOW_RED_ALPHA;
 sg::mask_placement placement{};bool found=false;
 for(unsigned i=0;i<s.count;i++){
  const auto &q=s.items[i];if(s.identities[i]==identity&&q.source==source.name&&q.mask==mask.name&&q.sx==crop.x&&q.sy==crop.y&&q.width==crop.width&&q.height==crop.height&&q.mode==mode){placement={q.dx,q.dy};found=true;break;}
 }
 if(!found){
  // A completed page is immutable while consumers may still reference it.
  // Exact retained hits can reuse it across state/list barriers without work.
  if(s.composed){mask_finish();s.reset();}
  if(s.count==s.items.size()||!s.shelf.place(crop.width,crop.height,placement)){
   mask_finish();s.reset();if(!s.shelf.place(crop.width,crop.height,placement))throw std::runtime_error("Mask page placement rejected");
  }
  s.items[s.count]={source.name,mask.name,crop.x,crop.y,crop.width,crop.height,placement.x,placement.y,mode};s.identities[s.count++]=identity;
  s.width=std::max(s.width,placement.x+crop.width);s.height=std::max(s.height,placement.y+crop.height);
 }
 auto mapped=sg::mask_batch_sprite(sprite,source.width,source.height,crop,placement,s.texture);
 if(draw(&mapped,opaque))throw std::runtime_error("Mask page consumer rejected");++s.sprites;return 1;
}
void mask_page_close(){
 auto &s=mask_page_;if(s.texture&&s.owner==OSMesaGetCurrentContext()){mask_finish();glDeleteTextures(1,&s.texture);}
 if(n810_runtime_debug()&&s.pages)std::fprintf(stderr,"GPU_MASK_PAGES pages=%llu sprites=%llu\n",s.pages,s.sprites);
 s.texture=0;s.owner=nullptr;s.failed=false;s.pages=s.sprites=0;s.reset();
}
}
extern "C" int sg_mask_batch_prepare(){return mask_page_prepare();}
